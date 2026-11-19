"""应用配置：全字段集中于 Settings，来源优先级 环境变量 > .env > 默认值。

对应 Plan 1 Task 1 Step 5。字段分组与 `.env.example` 一一对应。

.env 路径锚定仓库根（backend/app/core/config.py → parents[3]），
不随启动时的工作目录变化——PyCharm 直接运行脚本也能读到配置。
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # ── 数据库 / 中间件 ──────────────────────────────────────────
    mysql_url: str = "mysql+pymysql://root:password@127.0.0.1:3307/everkb?charset=utf8mb4"
    milvus_uri: str = "http://127.0.0.1:19530"
    collection_name: str = "rag_chunk"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # ── 存储（local | oss，可插拔抽象见 storage.py）──────────────
    storage_backend: str = "local"
    storage_root: str = "./data/storage"
    oss_endpoint: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_bucket: str = ""

    # ── Embedding（OpenAI 兼容协议；预置 DashScope 兼容模式）──────
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_dim: int = 1024
    embedding_batch_size: int = 10

    # ── LLM（OpenAI 兼容协议；预置火山方舟豆包，答案生成）────────
    # .env 沿用排期 ARK_ 命名（.env.example 已含），故经 alias 读取；
    # 未填 ARK_API_KEY 时回落 llm_* 缺省，问答链路走 FakeLLM（测试/无 key 环境）。
    llm_base_url: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3", validation_alias="ARK_BASE_URL"
    )
    llm_api_key: str = Field(default="", validation_alias="ARK_API_KEY")
    llm_model: str = Field(default="doubao-seed-2-0-lite-260428", validation_alias="ARK_MODEL")
    llm_temperature: float = 0.3
    chat_rate_limit_per_min: int = 60

    # ── 鉴权（管理端 JWT；账号存 admin_user 表，首账号用 scripts/seed_admin.py
    #    创建——2026-11-17 Task 14 回收 admin_username/admin_password_hash 遗留字段）──
    jwt_secret: str = "change-me"
    jwt_expire_hours: int = 24

    # ── 切块 / 上传限制（设计文档 §6.1）──────────────────────────
    chunk_target_chars: int = 300
    chunk_overlap_chars: int = 30
    upload_max_bytes: int = 209_715_200  # 200MB
    web_doc_max_urls: int = 50

    # ── Worker（进程内线程，轮询任务表）──────────────────────────
    worker_enabled: bool = True
    worker_interval_sec: int = 5

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """全局单例入口；测试中请直接构造 Settings(...) 而非走缓存。"""
    return Settings()
