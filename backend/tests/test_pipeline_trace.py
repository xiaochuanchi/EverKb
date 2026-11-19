"""解析管线 Trace 观测（Task 29）：管线各阶段埋 span，观测失败不打断入库。

红线 3：不触网——FakeEmbedder/FakeVector + Tracer 内存 span 收集，落库到 SQLite。

Review Focus 锁定（计划文档 §Review Focus 5/6）：
- 文档入库产生 parse/chunking/embedding/vector_insert 四类 span，trace_id 关联本次入库；
- 观测写库失败不打断管线，文档仍正常完成。
"""
from app.models import DocumentStatus, TraceSpan
from app.services.trace import Tracer
from tests.conftest import make_docx_bytes


def test_pipeline_spans_recorded(pipeline_env, make_document, seed_source):
    """文档入库产生四类 span，trace_id = -(doc_id)，落库到 trace_span 可查。"""
    doc = make_document()
    seed_source(doc, make_docx_bytes([
        ("第一条", ["数据处理活动应当遵循安全与发展的原则。"]),
        ("第二条", ["个人信息处理应当遵循合法正当必要原则。"]),
    ]))

    tracer = Tracer()
    # 直接调 process_document（带 tracer），复用 pipeline_env 的依赖
    from app.services.pipeline import process_document
    process_document(
        pipeline_env.session, doc.id,
        storage=pipeline_env.storage, embedder=pipeline_env.embedder,
        vector=pipeline_env.vector, settings=pipeline_env.settings,
        tracer=tracer,
    )

    assert doc.status == DocumentStatus.COMPLETED
    # span 已 flush 到 trace_span，trace_id = -doc_id
    spans = (
        pipeline_env.session.query(TraceSpan)
        .filter(TraceSpan.trace_id == -doc.id)
        .order_by(TraceSpan.id)
        .all()
    )
    span_types = {s.span_type for s in spans}
    assert {"parse", "chunking", "embedding", "vector_insert"} <= span_types
    # 四个 span 均关联本次入库 trace_id（负数命名空间，与 qa_record.id 隔离）
    assert all(s.trace_id == -doc.id for s in spans)


def test_pipeline_observe_failure_does_not_break(pipeline_env, make_document, seed_source):
    """观测 flush 失败（session 抛异常）不打断入库，文档仍 status=6。"""
    doc = make_document()
    seed_source(doc, make_docx_bytes([("标题", ["正文内容用于切块入库。"] * 3)]))

    from app.services.pipeline import process_document

    class _BoomTracer(Tracer):
        """flush 时抛异常，模拟观测落库故障。"""

        def flush(self, session):
            raise RuntimeError("trace 落库故障（模拟）")

    tracer = _BoomTracer()
    # 观测失败必须被吞掉，文档仍正常完成（红线：观测失败绝不打断入库）
    process_document(
        pipeline_env.session, doc.id,
        storage=pipeline_env.storage, embedder=pipeline_env.embedder,
        vector=pipeline_env.vector, settings=pipeline_env.settings,
        tracer=tracer,
    )
    assert doc.status == DocumentStatus.COMPLETED


def test_pipeline_no_tracer_still_completes(pipeline_env, make_document, seed_source, process_doc):
    """不传 tracer（tracer=None）时管线行为不变，不产生管线 span。"""
    doc = make_document()
    seed_source(doc, make_docx_bytes([("标题", ["正文内容。"] * 2)]))
    process_doc(doc.id)
    assert doc.status == DocumentStatus.COMPLETED
    # 无 tracer → 无管线 span 落库
    spans = (
        pipeline_env.session.query(TraceSpan)
        .filter(TraceSpan.trace_id == -doc.id)
        .all()
    )
    assert spans == []
