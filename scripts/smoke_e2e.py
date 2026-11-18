"""端到端冒烟（Plan 1 Task 15）：对真实后端跑通全链路，验证真实 MySQL/Milvus/embedding。

前置（手动）：
  1. docker compose up -d（MySQL + Milvus + Redis）
  2. 起后端：uvicorn app.main:app --reload --app-dir backend（真实 embedder/vector 在 lifespan 补齐）
  3. 确保有 admin 账号（scripts/seed_admin.py 已跑过）
  4. （可选）scripts/verify_embedding.py / verify_milvus.py 已绿

执行：
  python3 scripts/smoke_e2e.py
  # 覆盖默认：python3 scripts/smoke_e2e.py --base-url http://192.168.1.249:8000 --username ops --password 'S3cret!xx'

流程：登录 → 建库 → 内存构造 docx 上传 → 轮询到 status==6 → 列 chunks 断言 >0
      → 校验 Milvus 侧 count_by_doc == 库中 chunk 数 → 对账无该 doc 异常 → 打印 PASS。

说明：脚本只做 HTTP 调用 + 直连 Milvus 校验，不 import app 包（避免与后端进程争 .env）。
清理：验证完删除该测试文档与知识库（避免污染真实数据），失败也尽力清理。
"""
import argparse
import io
import sys
import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def _build_docx() -> bytes:
    """内存构造一个可切块的 docx（两个 Heading + 若干正文段，保证 >0 chunk）。"""
    from docx import Document

    doc = Document()
    doc.add_heading("EverKB 冒烟测试文档", level=1)
    doc.add_paragraph("这是一段用于端到端冒烟的正文内容，用来验证解析、切块与向量化链路是否打通。")
    doc.add_paragraph("第二段正文，包含足够多的文字以确保切块器能产出至少一个 chunk。")
    doc.add_heading("第二节", level=1)
    doc.add_paragraph("这一节验证多标题切块与 chunk_index 顺序。")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _login(client: httpx.Client, base: str, username: str, password: str) -> str:
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


def _main() -> int:
    parser = argparse.ArgumentParser(description="EverKB 端到端冒烟")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True, help="admin 账号密码")
    parser.add_argument("--timeout", type=float, default=120.0, help="轮询 status==6 的超时秒数")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    kb_id = doc_id = None
    try:
        with httpx.Client(timeout=30.0) as client:
            headers = _login(client, base, args.username, args.password)
            print(f"✓ 登录成功（{args.username}）")

            # 1) 建库
            kb = _post_json(client, base, headers, "/api/v1/admin/kbs",
                            {"name": f"冒烟-{int(time.time())}", "description": "e2e smoke 临时库"})
            kb_id = kb["id"]
            print(f"✓ 建库 id={kb_id}")

            # 2) 上传 docx
            files = {"file": ("smoke.docx", _build_docx(),
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

            # 4) 列 chunks 断言 >0
            chunks = _get_json(client, base, headers, f"/api/v1/admin/documents/{doc_id}/chunks",
                               params={"page": 1, "size": 100})
            assert chunks["total"] > 0, "chunk 数为 0"
            assert all(c["vectorized"] for c in chunks["items"]), "存在未向量化 chunk"
            print(f"✓ chunks 共 {chunks['total']} 条，全部 vectorized")

            # 5) 校验 Milvus 侧计数一致
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
            from app.core.config import get_settings
            from app.services.vector import create_vector

            vector = create_vector(get_settings())
            vector_count = vector.count_by_doc(doc_id)
            assert vector_count == chunks["total"], \
                f"Milvus 计数 {vector_count} != MySQL chunk 数 {chunks['total']}"
            print(f"✓ Milvus count_by_doc == {vector_count}")

            # 6) 对账无该 doc 异常
            recon = _get_json(client, base, headers, "/api/v1/admin/reconciliation")
            assert not any(it["doc_id"] == doc_id for it in recon), "对账检出该文档漂移"
            print("✓ 对账无漂移")

        print("PASS")
        return 0
    finally:
        # 清理（尽力而为，失败也执行）
        if kb_id is not None:
            try:
                with httpx.Client(timeout=30.0) as client:
                    headers = _login(client, base, args.username, args.password)
                    if doc_id is not None:
                        client.delete(f"{base}/api/v1/admin/documents/{doc_id}", headers=headers)
                    client.delete(f"{base}/api/v1/admin/kbs/{kb_id}", headers=headers)
                    print("✓ 已清理冒烟数据")
            except Exception as e:  # noqa: BLE001
                print(f"⚠ 清理失败（忽略）：{e}")


if __name__ == "__main__":
    sys.exit(_main())
