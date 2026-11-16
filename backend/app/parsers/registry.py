"""解析器注册表：文件类型 → Parser 分派（docx/pdf/xlsx 已接入）。"""
from app.parsers.base import Parser
from app.parsers.docx_parser import DocxParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.xlsx_parser import XlsxParser

# 上传文件类型白名单（计划接口锁定三种；网页抓取 source_type=webpage 不在此列）
SUPPORTED_FILE_TYPES = {"docx", "pdf", "xlsx"}

_PARSERS: dict[str, type] = {
    "docx": DocxParser,
    "pdf": PdfParser,
    "xlsx": XlsxParser,
}


def get_parser(file_type: str) -> Parser:
    ft = file_type.rsplit(".", 1)[-1].lower()
    if ft not in SUPPORTED_FILE_TYPES:
        raise ValueError(f"不支持的文件类型：{file_type}（支持：{sorted(SUPPORTED_FILE_TYPES)}）")
    return _PARSERS[ft]()
