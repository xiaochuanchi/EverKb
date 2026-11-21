"""文档生命周期 API（挂载于 /api/v1/admin）。

上传/网页批量添加/查询/替换重传/重试/启停/删除。API 只落库翻状态，
实际处理由 worker 轮询 status==1 完成（app.workers → run_pending）。
删除顺序红线 3：Milvus 先行 → MySQL（chunk 行 → doc 行）→ 存储对象最后。

多租户（M1/M5）：所有端点 require_enterprise + ensure_owned，按 enterprise_id
隔离；kb 与 doc 的归属都校验（跨企业访问统一 404，不泄露存在性）。
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.authz import ensure_owned, require_enterprise
from app.api.envelope import EnvelopeRoute
from app.core.config import Settings
from app.core.db import get_db
from app.core.storage import StorageClient
from app.models import AdminUser, Chunk, Document, DocumentStatus, KnowledgeBase, SourceType
from app.parsers import SUPPORTED_FILE_TYPES
from app.schemas import (
    MAX_BATCH_ITEMS,
    ContentOut,
    ContentUpdate,
    DocumentEnabledPatch,
    DocumentOut,
    DocumentPageOut,
    WebDocCreate,
)
from app.services.pipeline import content_key_for
from app.services.vector import VectorClient

router = APIRouter(tags=["文档"], route_class=EnvelopeRoute)

# 处理中的状态（2–5）不可替换：与 worker 竞争写入同一文档会互相覆盖状态
_PROCESSING_STATUSES = frozenset({
    DocumentStatus.PARSING,
    DocumentStatus.EXTRACTED,
    DocumentStatus.CHUNKED,
    DocumentStatus.VECTORIZING,
})


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _storage(request: Request) -> StorageClient:
    return request.app.state.storage


def _vector(request: Request) -> VectorClient:
    return request.app.state.vector


def _bm25(request: Request):
    """二期混合检索 BM25 索引管理器；未注入时返回 None（停用混合检索不报错）。"""
    return getattr(request.app.state, "bm25", None)


def _get_owned_kb_or_404(db: Session, kb_id: int, ent_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    ensure_owned(db, kb, ent_id)
    return kb


def _get_owned_doc_or_404(db: Session, doc_id: int, ent_id: int) -> Document:
    doc = db.get(Document, doc_id)
    ensure_owned(db, doc, ent_id)
    return doc


def _check_extension(filename: str) -> str:
    """扩展名白名单（Global Constraints：docx/pdf/xlsx）；非法 400。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_FILE_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型，白名单：{'/'.join(sorted(SUPPORTED_FILE_TYPES))}",
        )
    return ext


def _check_size(data: bytes, settings: Settings) -> None:
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件超过大小上限")


@router.post(
    "/kbs/{kb_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentOut,
)
def upload_document(
    kb_id: int,
    file: UploadFile,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
    settings: Settings = Depends(_settings),
    storage: StorageClient = Depends(_storage),
) -> Document:
    """上传文件建文档：先落行拿 id 定 oss_key，再写对象，处理交给 worker。"""
    _get_owned_kb_or_404(db, kb_id, user.enterprise_id)
    ext = _check_extension(file.filename or "")
    data = file.file.read()
    _check_size(data, settings)
    doc = Document(
        kb_id=kb_id,
        name=file.filename,
        source_type=SourceType.UPLOAD,
        file_type=ext,
        file_size=len(data),
        status=DocumentStatus.UPLOADED,
        enterprise_id=user.enterprise_id,
    )
    db.add(doc)
    db.flush()  # 回填 id 构造对象路径
    doc.oss_key = f"kb/{kb_id}/doc/{doc.id}/source.{ext}"
    storage.put_bytes(doc.oss_key, data)
    db.commit()
    db.refresh(doc)
    return doc


@router.post(
    "/kbs/{kb_id}/documents/batch",
    status_code=status.HTTP_201_CREATED,
    response_model=list[DocumentOut],
)
def upload_documents_batch(
    kb_id: int,
    files: list[UploadFile] = File(..., alias="file"),  # multipart 字段名与单文件接口一致
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
    settings: Settings = Depends(_settings),
    storage: StorageClient = Depends(_storage),
) -> list[Document]:
    """批量上传文件建文档（≤MAX_BATCH_ITEMS/请求）。

    全部文件先校验（扩展名→大小）再落库落存储：任一文件非法则整体
    400/413，不产生半批状态；处理交给 worker。
    """
    if not 1 <= len(files) <= MAX_BATCH_ITEMS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"单次上传文件数须在 1–{MAX_BATCH_ITEMS} 之间",
        )
    _get_owned_kb_or_404(db, kb_id, user.enterprise_id)
    exts = [_check_extension(f.filename or "") for f in files]
    payloads = []
    for f in files:
        data = f.file.read()
        _check_size(data, settings)
        payloads.append((f.filename, data))
    docs = []
    for (name, data), ext in zip(payloads, exts):
        doc = Document(
            kb_id=kb_id,
            name=name,
            source_type=SourceType.UPLOAD,
            file_type=ext,
            file_size=len(data),
            status=DocumentStatus.UPLOADED,
            enterprise_id=user.enterprise_id,
        )
        db.add(doc)
        db.flush()  # 回填 id 构造对象路径
        doc.oss_key = f"kb/{kb_id}/doc/{doc.id}/source.{ext}"
        storage.put_bytes(doc.oss_key, data)
        docs.append(doc)
    db.commit()
    for doc in docs:
        db.refresh(doc)
    return docs


@router.post(
    "/kbs/{kb_id}/documents/web",
    status_code=status.HTTP_201_CREATED,
    response_model=list[DocumentOut],
)
def create_web_documents(
    kb_id: int,
    payload: WebDocCreate,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> list[Document]:
    """批量添加网页文档（≤50/请求，超限由 schema 422）；html 快照由管线抓取时落存储。"""
    _get_owned_kb_or_404(db, kb_id, user.enterprise_id)
    docs = []
    for url in payload.urls:
        doc = Document(
            kb_id=kb_id,
            name=url[:256],  # 显示名截断到列宽，source_url 保留完整
            source_type=SourceType.WEBPAGE,
            file_type="html",
            oss_key="",
            source_url=url,
            status=DocumentStatus.UPLOADED,
            enterprise_id=user.enterprise_id,
        )
        db.add(doc)
        db.flush()
        doc.oss_key = f"kb/{kb_id}/doc/{doc.id}/source.html"
        docs.append(doc)
    db.commit()
    return docs


@router.get("/kbs/{kb_id}/documents", response_model=DocumentPageOut)
def list_documents(
    kb_id: int,
    status_filter: int | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> dict:
    """库内文档分页列表（按 id 升序），可按 status 过滤。"""
    _get_owned_kb_or_404(db, kb_id, user.enterprise_id)
    conditions = [Document.kb_id == kb_id]
    if status_filter is not None:
        conditions.append(Document.status == status_filter)
    total = db.scalar(select(func.count()).select_from(Document).where(*conditions))
    items = db.scalars(
        select(Document)
        .where(*conditions)
        .order_by(Document.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return {"total": total, "page": page, "size": size, "items": list(items)}


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(
    doc_id: int,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> Document:
    """文档详情。"""
    return _get_owned_doc_or_404(db, doc_id, user.enterprise_id)


@router.put("/documents/{doc_id}/file", response_model=DocumentOut)
def replace_document_file(
    doc_id: int,
    file: UploadFile,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
    settings: Settings = Depends(_settings),
    storage: StorageClient = Depends(_storage),
) -> Document:
    """替换重传：覆盖 source 对象、version+1、status 置回 1。

    worker 按替换分支处理（version>1）：处理期间旧版向量持续供检索，
    新版本成功后才按旧 ids 精准清理（spec §6.2）。处理中（2–5）不可替换：
    与 worker 竞争写入同一文档会互相覆盖状态；网页文档无文件可替换。
    """
    doc = _get_owned_doc_or_404(db, doc_id, user.enterprise_id)
    if doc.source_type != SourceType.UPLOAD:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="网页文档无可替换文件")
    if doc.status in _PROCESSING_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="文档处理中，不可替换")
    ext = _check_extension(file.filename or "")
    data = file.file.read()
    _check_size(data, settings)
    # oss_key 不变（同路径覆盖），content.md 目录随之稳定；扩展名变化只更新 file_type
    storage.put_bytes(doc.oss_key, data)
    doc.file_type = ext
    doc.file_size = len(data)
    doc.version += 1
    doc.status = DocumentStatus.UPLOADED
    doc.status_reason = None
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/documents/{doc_id}/content", response_model=ContentOut)
def get_document_content(
    doc_id: int,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
    storage: StorageClient = Depends(_storage),
) -> ContentOut:
    """读 content.md（md 编辑器）。未生成（status<3）409；存储缺对象 404。"""
    doc = _get_owned_doc_or_404(db, doc_id, user.enterprise_id)
    if doc.status < DocumentStatus.EXTRACTED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="文档尚未生成 markdown，暂不可编辑")
    try:
        data = storage.get_bytes(content_key_for(doc.oss_key))
    except FileNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="markdown 内容对象不存在（管线异常，请重试）"
        ) from None
    return ContentOut(document_id=doc_id, content=data.decode("utf-8"))


@router.put("/documents/{doc_id}/content", response_model=DocumentOut)
def put_document_content(
    doc_id: int,
    payload: ContentUpdate,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
    storage: StorageClient = Depends(_storage),
) -> Document:
    """保存编辑后的 content.md：覆盖对象、edited=True、status 置回 3。

    worker 领 status==3 任务从切块阶段续跑（process_document 编辑分支）；
    chunk 已存在（编辑完成态文档）走替换语义，旧版向量处理期间持续供检索。
    处理中（2/4/5）拒绝写入：与 worker 竞争会互相覆盖状态。
    """
    doc = _get_owned_doc_or_404(db, doc_id, user.enterprise_id)
    if doc.status in _PROCESSING_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="文档处理中，不可编辑")
    if doc.status not in (DocumentStatus.EXTRACTED, DocumentStatus.COMPLETED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="仅已生成 markdown（状态 3）或已完成（状态 6）的文档可编辑保存",
        )
    storage.put_bytes(content_key_for(doc.oss_key), payload.content.encode("utf-8"))
    doc.edited = True
    doc.status = DocumentStatus.EXTRACTED
    doc.status_reason = None
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/documents/{doc_id}/retry", response_model=DocumentOut)
def retry_document(
    doc_id: int,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
) -> Document:
    """重试失败文档（仅 status==7，其余 409）：置回 1，残留清理由管线开头负责（红线 4）。"""
    doc = _get_owned_doc_or_404(db, doc_id, user.enterprise_id)
    if doc.status != DocumentStatus.FAILED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="仅失败文档可重试")
    doc.status = DocumentStatus.UPLOADED
    doc.status_reason = None
    db.commit()
    db.refresh(doc)
    return doc


@router.patch("/documents/{doc_id}/enabled", response_model=DocumentOut)
def patch_document_enabled(
    doc_id: int,
    payload: DocumentEnabledPatch,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
    vector: VectorClient = Depends(_vector),
    bm25=Depends(_bm25),
) -> Document:
    """启停文档：MySQL 翻标志 + Milvus 行同步翻。

    Milvus 先行（与删除同序）：若先翻库后 Milvus 失败，会留下
    「库侧停用、向量仍可检索」的脏窗。
    """
    doc = _get_owned_doc_or_404(db, doc_id, user.enterprise_id)
    if doc.status in _PROCESSING_STATUSES:
        # set_doc_enabled 对无行文档是空操作，处理中翻标志会被 worker 过期值覆盖（终审 Important #2）
        raise HTTPException(status.HTTP_409_CONFLICT, detail="文档处理中，不可启停")
    vector.set_doc_enabled(doc_id, payload.enabled)
    if bm25 is not None:
        bm25.set_doc_enabled(doc_id, payload.enabled)
    doc.enabled = payload.enabled
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: int,
    user: AdminUser = Depends(require_enterprise),
    db: Session = Depends(get_db),
    vector: VectorClient = Depends(_vector),
    storage: StorageClient = Depends(_storage),
    bm25=Depends(_bm25),
) -> None:
    """删除文档（红线 3 顺序钉死）：Milvus → chunk 行 → doc 行（同事务提交）
    → 存储对象最后（source 与 content.md；提交后删，失败只留无害孤儿对象）。"""
    doc = _get_owned_doc_or_404(db, doc_id, user.enterprise_id)
    if doc.status in _PROCESSING_STATUSES:
        # DELETE 与 worker 竞争会产生孤儿可搜向量（终审 Critical #1 API 侧闸）
        raise HTTPException(status.HTTP_409_CONFLICT, detail="文档处理中，暂不可删除")
    oss_key = doc.oss_key
    vector.delete_by_doc(doc_id)
    if bm25 is not None:
        bm25.delete_by_doc(doc_id)
    db.query(Chunk).filter(Chunk.document_id == doc_id).delete(synchronize_session=False)
    db.delete(doc)
    db.commit()
    storage.delete(oss_key)
    storage.delete(content_key_for(oss_key))
