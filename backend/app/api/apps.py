"""应用管理 API（Task 18，挂载于 /api/v1/admin/apps）。

app 是产品侧问答入口（挂知识库 + 检索参数 + 模型配置），X-API-Key 鉴权落点：
- 创建时服务端生成 api_key（sk- 前缀），仅此一次明文返回（AppCreateOut）；
- 其余读取（列表/详情）api_key 与 model_params.api_key 一律脱敏为 sk-***；
- reset-key 重置并返回新明文，旧 key 即刻失效（库中已替换）。
"""
from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.models import App
from app.schemas import AppCreate, AppCreateOut, AppKeyOut, AppOut, AppPatch

router = APIRouter(prefix="/apps", tags=["应用管理"], route_class=EnvelopeRoute)

_API_KEY_PREFIX = "sk-"
_MASKED_KEY = "sk-***"


def _generate_api_key() -> str:
    """生成 X-API-Key：sk- + 48 位十六进制随机（VARCHAR(64) 内，唯一约束兜底）。"""
    import secrets

    return f"{_API_KEY_PREFIX}{secrets.token_hex(24)}"


def _mask(value: str) -> str:
    """密钥脱敏：任何非空明文密钥 → sk-***（对齐技术决策记录 §7 备忘）。"""
    return _MASKED_KEY if value else value


def _mask_model_params(model_params: dict | None) -> dict:
    """深拷贝 model_params，掩掉其中的 api_key 字段，其余原样。"""
    if not model_params:
        return {}
    masked = deepcopy(model_params)
    if "api_key" in masked and masked["api_key"]:
        masked["api_key"] = _MASKED_KEY
    return masked


def _commit_or_409(db: Session, detail: str = "应用名已存在") -> None:
    """check-then-write 窗口的并发同名/同 key 由唯一约束兜底（IntegrityError → 409）。"""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=detail) from None


def _get_or_404(db: Session, app_id: int) -> App:
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="应用不存在")
    return app


def _name_taken(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
    stmt = select(func.count()).select_from(App).where(App.name == name)
    if exclude_id is not None:
        stmt = stmt.where(App.id != exclude_id)
    return bool(db.scalar(stmt))


def _to_out(app: App) -> AppOut:
    """ORM → 脱敏 AppOut：api_key 与 model_params.api_key 掩掉。"""
    return AppOut(
        id=app.id,
        name=app.name,
        kb_ids=app.kb_ids,
        api_key=_mask(app.api_key),
        enabled=app.enabled,
        top_k=app.top_k,
        retrieval_mode=app.retrieval_mode,
        score_threshold=app.score_threshold,
        prompt_template=app.prompt_template,
        model_params=_mask_model_params(app.model_params),
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AppCreateOut)
def create_app(payload: AppCreate, db: Session = Depends(get_db)) -> App:
    """创建应用（生成 api_key，唯一一次明文返回；重名 409）。"""
    if _name_taken(db, payload.name):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="应用名已存在")
    app = App(
        name=payload.name,
        kb_ids=payload.kb_ids,
        api_key=_generate_api_key(),
        enabled=True,
        top_k=payload.top_k,
        retrieval_mode=payload.retrieval_mode,
        score_threshold=payload.score_threshold,
        prompt_template=payload.prompt_template,
        model_params=payload.model_params,
    )
    db.add(app)
    _commit_or_409(db)
    db.refresh(app)
    return app


@router.get("", response_model=list[AppOut])
def list_apps(db: Session = Depends(get_db)) -> list[AppOut]:
    """应用列表（按 id 升序；api_key 脱敏）。"""
    apps = db.scalars(select(App).order_by(App.id)).all()
    return [_to_out(a) for a in apps]


@router.get("/{app_id}", response_model=AppOut)
def get_app(app_id: int, db: Session = Depends(get_db)) -> AppOut:
    """应用详情（api_key 与 model_params.api_key 脱敏）。"""
    return _to_out(_get_or_404(db, app_id))


@router.patch("/{app_id}", response_model=AppOut)
def patch_app(app_id: int, payload: AppPatch, db: Session = Depends(get_db)) -> AppOut:
    """局部更新（name/kb_ids/top_k/score_threshold/prompt_template/model_params/enabled）。"""
    app = _get_or_404(db, app_id)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in data and data["name"] != app.name and _name_taken(db, data["name"], exclude_id=app_id):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="应用名已存在")
    for field, value in data.items():
        setattr(app, field, value)
    _commit_or_409(db)
    db.refresh(app)
    return _to_out(app)


@router.post("/{app_id}/reset-key", response_model=AppKeyOut)
def reset_key(app_id: int, db: Session = Depends(get_db)) -> AppKeyOut:
    """重置 api_key，返回新明文；旧 key 即刻失效（库中已替换）。"""
    app = _get_or_404(db, app_id)
    app.api_key = _generate_api_key()
    _commit_or_409(db, detail="密钥重置失败")
    db.refresh(app)
    return AppKeyOut(api_key=app.api_key)


@router.delete("/{app_id}")
def delete_app(app_id: int, db: Session = Depends(get_db)) -> None:
    """删除应用。"""
    app = _get_or_404(db, app_id)
    db.delete(app)
    db.commit()
