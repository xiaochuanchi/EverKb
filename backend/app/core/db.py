"""SQLAlchemy 基础设施：Base / engine 工厂 / 会话工厂 / 依赖与建表。

对应 Plan 1 Task 1 Step 6。SQLite 内存库用 StaticPool 保证同库连接
（否则 create_all 与业务会话各拿一个独立的 :memory: 库）。
"""
from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """全部 ORM 模型的公共基类（models.py 于 Task 2 挂载表定义）。"""


def make_engine(mysql_url: str):
    """按 URL 构造 engine；SQLite 内存库特殊处理，供测试注入。"""
    kwargs: dict = {}
    if mysql_url.startswith("sqlite"):
        kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(mysql_url, pool_pre_ping=True, **kwargs)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db(engine) -> None:
    """建表。Task 2 引入 models.py 后，本函数自动建出全部表
    （import models 触发表定义注册到 Base.metadata）。"""
    try:  # noqa: 模型模块 Task 2 才创建；存在即注册
        from app import models  # noqa: F401
    except ImportError:
        pass
    Base.metadata.create_all(bind=engine)


def get_db(request: Request) -> Generator[Session, None, None]:
    """FastAPI 依赖：从 app.state 取会话工厂，yield 一个会话。"""
    factory: sessionmaker[Session] = request.app.state.session_factory
    db = factory()
    try:
        yield db
    finally:
        db.close()
