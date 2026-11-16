"""Pydantic 请求/响应模型（Plan 1 Task 3 起；admin/open 两侧共用本模块）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KBCreate(BaseModel):
    """POST /kbs 请求体。"""

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)


class KBPatch(BaseModel):
    """PATCH /kbs/{id} 请求体：字段可选，未给的（None）不改。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    status: int | None = None


class KBOut(BaseModel):
    """知识库响应体（对齐 models.KnowledgeBase 列）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    status: int
    created_at: datetime
