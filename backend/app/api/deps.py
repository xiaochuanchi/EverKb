"""open 侧依赖（Task 19）：X-API-Key 鉴权 + chat 限流。

两套鉴权语义（技术决策记录 §2.2）：
- admin 侧 JWT = "人"的身份（api/auth.require_admin）；
- open 侧 X-API-Key = "应用"的身份（本模块 require_api_key）。

鉴权失败措辞：
- 缺头 / 头格式错 / key 不匹配 → 401（不泄露"是否存在"）；
- 应用存在但 enabled=False → 403（key 对，但入口已停用）。

限流：chat 端点挂 require_api_key 时顺带 check_rate_limit（429 超限），
限流器从 app.state.rate_limiter 取（未注入时缺省 Noop，放行）。
"""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import App, Enterprise, EnterpriseStatus

_API_KEY_HEADER = "X-API-Key"


def _unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail="无效的 API Key")


def _get_app_by_key(db: Session, api_key: str | None) -> App | None:
    if not api_key:
        return None
    from sqlalchemy import select

    return db.scalar(select(App).where(App.api_key == api_key))


def require_api_key(
    request: Request,
    db: Session = Depends(get_db),
) -> App:
    """X-API-Key 鉴权依赖：读头 → 查 app.api_key → 401/403 → 返回 App。

    key 不存在或为空一律 401（不泄露应用是否存在）；应用停用 403。

    M2 商业化多租户：open 侧是真实计费入口（方案 §6），查 app 时须一并校验
    所属企业状态——冻结（FROZEN）/ 已清理（PURGED）企业的 app 一律 403，
    否则 API Key 是无限费洞口。enterprise_id=NULL 视为平台资产（存量/平台
    自建应用），不冻结，计费时跳过。
    """
    api_key = request.headers.get(_API_KEY_HEADER)
    app = _get_app_by_key(db, api_key)
    if app is None:
        raise _unauthorized()
    if not app.enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="应用已停用")
    if app.enterprise_id is not None:
        ent = db.get(Enterprise, app.enterprise_id)
        if ent is not None and ent.status in {EnterpriseStatus.FROZEN, EnterpriseStatus.PURGED}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="企业已冻结，服务不可用")
    return app


def check_rate_limit(
    request: Request,
    app: App = Depends(require_api_key),
) -> App:
    """鉴权 + 限流复合依赖：chat 端点使用。超限 429。"""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is not None and not limiter.allow(app.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="请求过于频繁，请稍后再试")
    return app
