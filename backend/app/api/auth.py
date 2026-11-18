"""管理后台鉴权 API（Task 14，挂载于 /api/v1/admin/auth）。

2026-11-17 拍板的三项决策：
1. 账号存 DB（models.AdminUser），首账号用 scripts/seed_admin.py 创建——
   Settings.admin_username / admin_password_hash 两个遗留字段已回收删除；
2. 单 access JWT（HS256，默认 24h），无 refresh——运营工具场景链路最短，
   前端 art-design-pro 登录页/路由守卫/401 拦截直接对接；
3. 密码哈希 pbkdf2 格式串（core/security.py）。

已知取舍：Redis（I5）未落地前无黑名单——改密后旧 token 仍有效至过期；
require_admin 每请求查库 is_active，禁用账号即时生效。登录失败限次随
Redis 接入补（技术决策记录 §3 接入点 A）。
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.envelope import EnvelopeRoute
from app.core.db import get_db
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models import AdminUser
from app.schemas import AdminUserOut, LoginRequest, PasswordChangeRequest, TokenOut

bearer_scheme = HTTPBearer(auto_error=False)  # 缺头/格式错返回 None，401 细节由 require_admin 统一给

router = APIRouter(prefix="/auth", tags=["鉴权"], route_class=EnvelopeRoute)


def _unauthorized(detail: str = "未登录或凭证无效") -> HTTPException:
    """401 统一出口：带 WWW-Authenticate 头（信封透传该头，见 test_envelope）。"""
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def require_admin(
    request: Request,
    credentials=Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    """admin 路由整包鉴权依赖：Bearer → 验签 → 查库 → is_active。

    每请求回表而非纯无状态：token 只证明"曾经登录过"，账号删除/禁用要
    即时生效。失败一律 401 同款措辞，不泄露具体原因。
    """
    if credentials is None:
        raise _unauthorized()
    settings = request.app.state.settings
    try:
        payload = decode_access_token(credentials.credentials, settings)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise _unauthorized() from None
    user = db.get(AdminUser, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    """账密登录 → JWT。用户不存在/密码错误共用同一措辞，防账号枚举。"""
    user = db.scalar(select(AdminUser).where(AdminUser.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="账号已禁用")
    settings = request.app.state.settings
    return TokenOut(access_token=create_access_token(user.id, settings))


@router.get("/me", response_model=AdminUserOut)
def me(user: AdminUser = Depends(require_admin)) -> AdminUser:
    """当前登录账号信息（前端登录后展示用户名用）。"""
    return user


@router.put("/password", status_code=status.HTTP_200_OK)
def change_password(
    payload: PasswordChangeRequest,
    user: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """改密码（user-center）。原密码不符 400；新密码至少 8 位（schema 校验）。

    无黑名单期旧 token 有效至过期（模块 docstring 取舍），过期后用新密码重登。
    """
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="原密码不正确")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
