"""手工模拟 Task 10 管线（管线本体尚未实现，本脚本用已有零件串一遍全流程）：

上传源文件 → 存 OSS → 读回 → 解析成 Markdown → 存 OSS → 读回验证。

对象路径遵守管线约定：kb/{kb_id}/doc/{doc_id}/source.{ext} 与 content.md。
对象保留在桶里（可去阿里云控制台查看），重复执行覆盖同一 demo 路径。
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from docx import Document as build_docx

from app.core.config import get_settings
from app.core.storage import OssStorage, create_storage
from app.parsers import get_parser

KB_ID, DOC_ID = "demo", "demo-20261116"
SOURCE_KEY = f"kb/{KB_ID}/doc/{DOC_ID}/source.docx"
CONTENT_KEY = f"kb/{KB_ID}/doc/{DOC_ID}/content.md"


def make_docx() -> bytes:
    """模拟用户上传的真实 docx（标题 + 正文 + 列表 + 表格）。"""
    doc = build_docx()
    doc.add_heading("EverKB 验证文档", level=1)
    doc.add_paragraph("这份文档由 demo_pipeline.py 现场生成，用于验证上传-解析-落盘全链路。")
    doc.add_paragraph("第一步：源文件写入对象存储。")
    doc.add_paragraph("第二步：解析为 Markdown 并写回对象存储。", style="List Bullet")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "步骤"
    table.rows[0].cells[1].text = "结果"
    table.rows[1].cells[0].text = "put_bytes"
    table.rows[1].cells[1].text = "200 OK"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def main() -> int:
    settings = get_settings()
    if not settings.oss_bucket:
        print("缺少 OSS 配置（.env 的 OSS_* 四项）")
        return 1

    if settings.storage_backend != "oss":
        print(f"提示：storage_backend={settings.storage_backend}，本脚本强制走 OSS 实验证据")
    storage = OssStorage(settings)  # 明确走 OSS，不依赖 .env 的 backend 开关
    print(f"[0] OSS 客户端就绪：bucket={settings.oss_bucket} @ {settings.oss_endpoint}")

    # ── 模拟 Task 11 上传 API 收到文件后的动作 ──────────────────
    data = make_docx()
    storage.put_bytes(SOURCE_KEY, data)
    print(f"[1] 源文件已上传：{SOURCE_KEY} ({len(data)} bytes)")

    back = storage.get_bytes(SOURCE_KEY)
    assert back == data, "源文件回读不一致"
    print(f"[2] 源文件回读一致：{len(back)} bytes")

    # ── 模拟 Task 10 管线的解析步骤 ─────────────────────────────
    result = get_parser("docx").parse(back, "demo.docx")
    if not result.ok:
        print(f"解析失败：{result.reason}")
        return 1
    print(f"[3] 解析成功，Markdown {len(result.markdown)} 字符，预览：")
    print("    " + result.markdown.replace("\n", "\n    ")[:300])

    storage.put_bytes(CONTENT_KEY, result.markdown.encode("utf-8"))
    print(f"[4] Markdown 已上传：{CONTENT_KEY} ({len(result.markdown.encode('utf-8'))} bytes)")

    md_back = storage.get_bytes(CONTENT_KEY).decode("utf-8")
    assert md_back == result.markdown, "Markdown 回读不一致"
    print(f"[5] Markdown 回读一致，全链路 OK")

    print()
    print("下载链接（1 小时有效，浏览器可直接打开）：")
    print(f"  source.docx : {storage.presign(SOURCE_KEY)}")
    print(f"  content.md  : {storage.presign(CONTENT_KEY)}")
    print()
    print("控制台查看路径：OSS 控制台 → 桶 everkb → 文件列表 → kb/demo/doc/demo-20261116/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
