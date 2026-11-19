"""检索评测 API（二期 Task 28 可视化，挂载于 /api/v1/admin/evals）。

数据源：`data/legal/ablation_result.json`（scripts/run_ablation.py 落的结构化消融结果，
与同脚本产出的检索评测报告同源）。admin「检索评测」页面读它渲染三路对比。

无数据库依赖——消融结果是离线实验产物，重跑一次评测脚本即更新。
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.api.envelope import EnvelopeRoute
from app.schemas import AblationResultOut

router = APIRouter(prefix="/evals", tags=["检索评测"], route_class=EnvelopeRoute)

# 项目根 = backend/ 的上级；消融结果随仓库走
_ABLATION_RESULT = (
    Path(__file__).resolve().parents[3] / "data" / "legal" / "ablation_result.json"
)


@router.get("/ablation", response_model=AblationResultOut)
def ablation_result() -> dict:
    """返回三路消融指标（纯向量 / 纯 BM25 / RRF 混合）与实验元信息。

    文件缺失时 404（提示先跑 scripts/run_ablation.py 生成结构化结果）。
    """
    if not _ABLATION_RESULT.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="消融结果缺失：请先运行 scripts/run_ablation.py 生成",
        )
    try:
        return json.loads(_ABLATION_RESULT.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"消融结果读取失败：{e}"
        ) from e
