"""解析器包：ParseResult/Parser 契约 + get_parser 分派（docx/pdf/xlsx + webpage 抓取）。"""
from app.parsers.base import ParseError, ParseResult, Parser
from app.parsers.registry import SUPPORTED_FILE_TYPES, get_parser

__all__ = ["SUPPORTED_FILE_TYPES", "ParseError", "ParseResult", "Parser", "get_parser"]
