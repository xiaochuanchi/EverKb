"""通知中心 API。

锁定点：
- 列表按 id 倒序，返回 total + unread + items；
- unread_only 过滤未读；
- 标记单条已读 / 全部已读后 unread 归零；
- 文档处理完成/失败会落通知（经管线埋点）。
"""
from app.models import Notification, NotificationType

BASE = "/api/v1/admin/notifications"


def _seed_notification(session, *, type=NotificationType.DOC_COMPLETED, title="t",
                       content="c", is_read=False, resource_id=1) -> Notification:
    n = Notification(type=type, title=title, content=content,
                     resource_type="document", resource_id=resource_id, is_read=is_read,
                     enterprise_id=1)
    session.add(n)
    session.commit()
    session.refresh(n)
    return n


def test_list_notifications_returns_total_and_unread(client):
    session = client.app.state.session_factory()
    _seed_notification(session, title="完成1", is_read=False)
    _seed_notification(session, title="完成2", is_read=False)
    _seed_notification(session, title="完成3", is_read=True)
    session.close()

    r = client.get(BASE)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["total"] == 3
    assert body["unread"] == 2
    assert len(body["items"]) == 3
    # 按 id 倒序：最新在前
    assert body["items"][0]["title"] == "完成3"


def test_list_notifications_unread_only(client):
    session = client.app.state.session_factory()
    _seed_notification(session, title="未读", is_read=False)
    _seed_notification(session, title="已读", is_read=True)
    session.close()

    r = client.get(BASE, params={"unread_only": "true"})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["title"] == "未读"


def test_unread_count(client):
    session = client.app.state.session_factory()
    _seed_notification(session, title="a", is_read=False)
    _seed_notification(session, title="b", is_read=False)
    session.close()

    r = client.get(f"{BASE}/unread-count")
    assert r.status_code == 200
    assert r.json()["data"]["unread"] == 2


def test_mark_read(client):
    session = client.app.state.session_factory()
    n = _seed_notification(session, title="待读", is_read=False)
    session.close()

    r = client.post(f"{BASE}/{n.id}/read")
    assert r.status_code == 200
    assert r.json()["data"]["is_read"] is True

    session = client.app.state.session_factory()
    assert session.get(Notification, n.id).is_read is True
    session.close()


def test_mark_read_404(client):
    assert client.post(f"{BASE}/999/read").status_code == 404


def test_mark_all_read(client):
    session = client.app.state.session_factory()
    _seed_notification(session, title="a", is_read=False)
    _seed_notification(session, title="b", is_read=False)
    _seed_notification(session, title="c", is_read=True)
    session.close()

    r = client.post(f"{BASE}/read-all")
    assert r.status_code == 200

    assert client.get(f"{BASE}/unread-count").json()["data"]["unread"] == 0


def test_pipeline_emits_notification_on_complete(pipeline_env, make_document, seed_source, process_doc):
    """文档处理完成 → 落一条 doc_completed 通知。"""
    from tests.conftest import make_docx_bytes

    doc = make_document()
    seed_source(doc, make_docx_bytes([("标题", ["正文内容用于切块。"])]))

    process_doc(doc.id)

    session = pipeline_env.session
    notes = session.query(Notification).filter_by(resource_id=doc.id).all()
    assert len(notes) == 1
    assert notes[0].type == NotificationType.DOC_COMPLETED
    assert notes[0].is_read is False
    assert doc.name in notes[0].title


def test_pipeline_emits_notification_on_fail(pipeline_env, make_document, seed_source, process_doc):
    """文档处理失败 → 落一条 doc_failed 通知，含失败原因。"""
    from app.models import DocumentStatus

    doc = make_document(file_type="pdf")
    seed_source(doc, b"")  # 空内容 → 解析失败

    process_doc(doc.id)

    assert doc.status == DocumentStatus.FAILED
    session = pipeline_env.session
    notes = session.query(Notification).filter_by(resource_id=doc.id).all()
    assert len(notes) == 1
    assert notes[0].type == NotificationType.DOC_FAILED
    assert doc.name in notes[0].title
