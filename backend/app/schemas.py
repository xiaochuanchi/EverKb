"""Pydantic 请求/响应模型（Plan 1 Task 3 起；admin/open 两侧共用本模块）。"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class KBCreate(BaseModel):
    """POST /kbs 请求体。"""

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)


class KBPatch(BaseModel):
    """PATCH /kbs/{id} 请求体：字段可选，未给的（None）不改。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    status: Literal[0, 1] | None = None  # 域对齐 models.KBStatus：越域 422，不静默落库


class KBOut(BaseModel):
    """知识库响应体（对齐 models.KnowledgeBase 列）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    status: int
    created_at: datetime


# ── 文档（Task 11）───────────────────────────────────────────────


class DocumentOut(BaseModel):
    """文档响应体（对齐 models.Document 列；oss_key 是存储内路径，属管线内部细节不外发）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    name: str
    source_type: int
    source_url: str | None = None
    file_type: str
    file_size: int
    status: int
    status_reason: str | None = None
    version: int
    enabled: bool
    chunk_count: int
    edited: bool
    uploaded_by: str
    created_at: datetime
    updated_at: datetime


class WebDocCreate(BaseModel):
    """POST /kbs/{kb_id}/documents/web 请求体：批量网页 ≤50 条/请求（Global Constraints）。"""

    urls: list[Annotated[str, StringConstraints(max_length=1024)]] = Field(
        min_length=1, max_length=50
    )


class DocumentEnabledPatch(BaseModel):
    """PATCH /documents/{id}/enabled 请求体。"""

    enabled: bool


class DocumentPageOut(BaseModel):
    """GET /kbs/{kb_id}/documents 分页响应体。"""

    total: int
    page: int
    size: int
    items: list[DocumentOut]
