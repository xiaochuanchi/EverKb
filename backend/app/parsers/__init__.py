"""解析器包：ParseResult/Parser 契约 + get_parser 分派（Task 5 docx；Task 6 pdf/xlsx/html）。"""
from app.parsers.base import ParseResult, Parser
from app.parsers.registry import SUPPORTED_FILE_TYPES, get_parser

__all__ = ["SUPPORTED_FILE_TYPES", "ParseResult", "Parser", "get_parser"]
