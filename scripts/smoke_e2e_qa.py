"""端到端问答冒烟（Plan 2 Task 23）：对真实后端跑通完整问答链路。

前置（手动）：
  1. docker compose up -d（MySQL + Milvus + Redis）
  2. 起后端：uvicorn app.main:app --reload --app-dir backend
  3. 确保有 admin 账号（scripts/seed_admin.py 已跑过）
  4. 确保 LLM 可用：scripts/verify_llm.py 已 PASS（.env 里 ARK_API_KEY 已填且模型已开通）

执行：
  python3 scripts/smoke_e2e_qa.py --password '你的admin密码'
  # 覆盖默认：python3 scripts/smoke_e2e_qa.py --base-url http://127.0.0.1:8000 --password 'xxx'

流程：登录 → 建库 → 内存构造 docx 上传 → 轮询到 status==6 → 建应用挂库（拿明文 api_key）
      → X-API-Key 发 SSE 问答 → 断言流式 delta + 收尾 citations 非空 → 查 qa_record 落库
      → 查 trace_span 成树（四类 span）→ 打印 PASS。

说明：脚本只做 HTTP 调用，不 import app 包（避免与后端进程争 .env）。
清理：验证完删除该应用 / 文档 / 知识库（避免污染真实数据），失败也尽力清理。
"""
import argparse
import io
import json
import sys
import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _build_docx() -> bytes:
    """内存构造一个可切块的 docx，正文含可检索的关键信息。"""
    from docx import Document

    doc = Document()
    doc.add_heading("EverKB 问答冒烟文档", level=1)
    doc.add_paragraph("EverKB 是一个 RAG 知识库管理平台，支持文档上传、切块、向量化与检索增强问答。")
    doc.add_paragraph("平台的默认管理员账号是 admin，问答链路通过 X-API-Key 进行应用级鉴权。")
    doc.add_heading("检索原理", level=1)
    doc.add_paragraph("系统将问题向量化后在 Milvus 中检索相似 chunk，再把命中的文本片段拼入提示词交给大模型生成回答。")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _login(client: httpx.Client, base: str, username: str, password: str) -> dict:
    resp = client.post(f"{base}/api/v1/admin/auth/login", json={
        "username": username, "password": password,
    })
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"登录失败：{body.get('message')}")
    token = body["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _post_json(client, base, headers, path, payload):
    resp = client.post(f"{base}{path}", json=payload, headers=headers)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"{path} 失败：{body.get('message')}")
    return body["data"]


def _get_json(client, base, headers, path, params=None):
    resp = client.get(f"{base}{path}", params=params, headers=headers)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"{path} 失败：{body.get('message')}")
    return body["data"]


def _parse_sse(text: str) -> list[dict]:
    """解析 SSE 响应体，返回所有 data: 帧解码后的 dict 列表。"""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload and payload != "[DONE]":
                events.append(json.loads(payload))
    return events


def _main() -> int:
    parser = argparse.ArgumentParser(description="EverKB 问答链路端到端冒烟")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True, help="admin 账号密码")
    parser.add_argument("--timeout", type=float, default=120.0, help="轮询 status==6 的超时秒数")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    kb_id = doc_id = app_id = None
    try:
        with httpx.Client(timeout=60.0) as client:
            headers = _login(client, base, args.username, args.password)
            print(f"✓ 登录成功（{args.username}）")

            # 1) 建库
            kb = _post_json(client, base, headers, "/api/v1/admin/kbs",
                            {"name": f"冒烟问答-{int(time.time())}", "description": "qa smoke 临时库"})
            kb_id = kb["id"]
            print(f"✓ 建库 id={kb_id}")

            # 2) 上传 docx
            files = {"file": ("smoke_qa.docx", _build_docx(),
                             "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
            resp = client.post(f"{base}/api/v1/admin/kbs/{kb_id}/documents",
                               files=files, headers=headers)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 0:
                raise RuntimeError(f"上传失败：{body.get('message')}")
            doc_id = body["data"]["id"]
            print(f"✓ 上传 docx id={doc_id}")

            # 3) 轮询到完成
            deadline = time.time() + args.timeout
            status = None
            while time.time() < deadline:
                doc = _get_json(client, base, headers, f"/api/v1/admin/documents/{doc_id}")
                status = doc["status"]
                if status == 6:
                    break
                if status == 7:
                    raise RuntimeError(f"文档处理失败：{doc.get('status_reason')}")
                time.sleep(1)
            if status != 6:
                raise RuntimeError(f"超时未完成，status={status}")
            print(f"✓ 处理完成，chunk_count={doc['chunk_count']}")

            # 4) 建应用挂库，拿明文 api_key
            app = _post_json(client, base, headers, "/api/v1/admin/apps",
                             {"name": f"冒烟应用-{int(time.time())}", "kb_ids": [kb_id], "top_k": 5})
            app_id = app["id"]
            api_key = app["api_key"]
            print(f"✓ 建应用 id={app_id}，api_key={api_key[:6]}...")

            # 5) X-API-Key 发 SSE 问答
            question = "EverKB 是什么？"
            open_headers = {"X-API-Key": api_key}
            with client.stream(
                "POST",
                f"{base}/api/v1/apps/{app_id}/chat",
                json={"question": question, "user_key": "smoke-user"},
                headers=open_headers,
            ) as r:
                r.raise_for_status()
                raw = "".join(r.iter_text())
            events = _parse_sse(raw)

            deltas = [e["delta"] for e in events if "delta" in e]
            finishers = [e for e in events if "citations" in e]
            assert deltas, "未收到任何流式 delta"
            assert finishers, "未收到收尾事件（citations）"
            answer = "".join(deltas)
            citations = finishers[-1].get("citations", [])
            grounded = finishers[-1].get("grounded", False)
            print(f"✓ 流式回答 {len(deltas)} 个片段，共 {len(answer)} 字")
            print(f"✓ grounded={grounded}，citations={len(citations)} 条")
            assert grounded, "期望 grounded=True（文档已入库可命中）"
            assert citations, "期望 citations 非空"

            # 6) 查 qa_record 落库
            records = _get_json(client, base, headers, "/api/v1/admin/records",
                                params={"app_id": app_id, "size": 10})
            assert records["total"] >= 1, "qa_record 未落库"
            rec = records["items"][0]
            assert rec["answer"], "qa_record.answer 为空"
            assert rec["question"] == question, "qa_record.question 不匹配"
            print(f"✓ qa_record id={rec['id']} 落库（answer {len(rec['answer'])} 字）")

            # 7) 查 trace_span 成树（四类 span）
            tree = _get_json(client, base, headers, f"/api/v1/admin/traces/{rec['id']}")
            span_types = set()
            for root in tree["spans"]:
                span_types |= _collect_span_types(root)
            expected = {"embedding", "retrieval", "db", "llm"}
            assert expected.issubset(span_types), f"span 类型不全：{span_types}"
            print(f"✓ trace_span 落库 {len(span_types)} 类：{sorted(span_types)}")

        print("PASS")
        return 0
    finally:
        # 清理（尽力而为，失败也执行）
        if any(x is not None for x in (kb_id, doc_id, app_id)):
            try:
                with httpx.Client(timeout=30.0) as client:
                    headers = _login(client, base, args.username, args.password)
                    if app_id is not None:
                        client.delete(f"{base}/api/v1/admin/apps/{app_id}", headers=headers)
                    if doc_id is not None:
                        client.delete(f"{base}/api/v1/admin/documents/{doc_id}", headers=headers)
                    if kb_id is not None:
                        client.delete(f"{base}/api/v1/admin/kbs/{kb_id}", headers=headers)
                    print("✓ 已清理冒烟数据")
            except Exception as e:  # noqa: BLE001
                print(f"⚠ 清理失败（忽略）：{e}")


def _collect_span_types(node) -> set:
    """递归收集 span 树里所有 span_type。"""
    types = {node.get("span_type")}
    for child in node.get("children", []) or []:
        types |= _collect_span_types(child)
    return types


if __name__ == "__main__":
    sys.exit(_main())
