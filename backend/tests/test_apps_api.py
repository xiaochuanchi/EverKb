"""应用管理 API（Task 18）。

路由落在 /api/v1/admin/apps。锁定点：
- 创建 201 且返回明文 api_key（sk- 前缀，仅此一次明文）；
- app.name 唯一（重名 409）；
- GET 详情 api_key 与 model_params 内 api_key 均脱敏（sk-***）；
- reset-key 返回新明文且旧 key 失效；
- DELETE 成功后 404。
"""
from app.models import App

BASE = "/api/v1/admin/apps"


def _create(client, name: str, **extra):
    return client.post(BASE, json={"name": name, **extra})


def _mask_key(key: str) -> str:
    """对齐技术决策记录 §7 Plan 2 备忘：脱敏形如 sk-***。"""
    return "sk-***"


def test_create_app_returns_201_with_plaintext_key(client):
    r = _create(client, "客服机器人", kb_ids=[1, 2])
    assert r.status_code == 201
    body = r.json()["data"]
    assert body["id"] > 0
    assert body["name"] == "客服机器人"
    assert body["kb_ids"] == [1, 2]
    # 创建时唯一一次明文返回 api_key
    key = body["api_key"]
    assert key.startswith("sk-") and len(key) > len("sk-")
    assert key != _mask_key(key)


def test_create_app_duplicate_name_409(client):
    _create(client, "重名应用")
    assert _create(client, "重名应用").status_code == 409


def test_list_apps_masks_key(client):
    _create(client, "应用A")
    _create(client, "应用B")
    r = client.get(BASE)
    assert r.status_code == 200
    data = r.json()["data"]
    assert [a["name"] for a in data] == ["应用A", "应用B"]
    for a in data:
        assert a["api_key"] == _mask_key(a["api_key"])


def test_get_app_detail_masks_key_and_model_params(client):
    app_id = _create(
        client,
        "详情应用",
        model_params={"base_url": "https://x", "api_key": "sk-secret123", "model": "m"},
    ).json()["data"]["id"]
    r = client.get(f"{BASE}/{app_id}")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["api_key"] == "sk-***"
    assert body["model_params"]["api_key"] == "sk-***"
    # 非敏感字段原样保留
    assert body["model_params"]["base_url"] == "https://x"
    assert body["model_params"]["model"] == "m"


def test_patch_app_updates_fields(client):
    app_id = _create(client, "可改应用").json()["data"]["id"]
    r = client.patch(
        f"{BASE}/{app_id}",
        json={"name": "改名应用", "top_k": 8, "enabled": False, "score_threshold": 0.6},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["name"] == "改名应用"
    assert body["top_k"] == 8
    assert body["enabled"] is False
    assert body["score_threshold"] == 0.6


def test_reset_key_returns_new_plaintext_and_invalidates_old(client):
    app_id = _create(client, "重置应用").json()["data"]["id"]
    old_key = client.get(f"{BASE}/{app_id}").json()["data"]["api_key"]  # 脱敏，仅占位
    # 直接从库读旧明文，供后续比对
    session = client.app.state.session_factory()
    old_plain = session.get(App, app_id).api_key
    session.close()

    r = client.post(f"{BASE}/{app_id}/reset-key")
    assert r.status_code == 200
    new_key = r.json()["data"]["api_key"]
    assert new_key.startswith("sk-") and new_key != "sk-***"
    assert new_key != old_plain  # 新 key 不同于旧 key

    # 旧 key 失效：库中 api_key 已替换为新明文
    session = client.app.state.session_factory()
    stored = session.get(App, app_id).api_key
    session.close()
    assert stored == new_key
    assert stored != old_plain


def test_delete_app(client):
    app_id = _create(client, "待删应用").json()["data"]["id"]
    r = client.delete(f"{BASE}/{app_id}")
    assert r.status_code == 200
    assert client.get(f"{BASE}/{app_id}").status_code == 404


def test_app_not_found_404(client):
    assert client.get(f"{BASE}/999").status_code == 404
    assert client.patch(f"{BASE}/999", json={"name": "x"}).status_code == 404
    assert client.post(f"{BASE}/999/reset-key").status_code == 404
    assert client.delete(f"{BASE}/999").status_code == 404


def test_create_app_defaults(client):
    """未提供时：kb_ids 空列表、top_k=5、enabled=True、score_threshold=None。"""
    body = _create(client, "默认应用").json()["data"]
    assert body["kb_ids"] == []
    assert body["top_k"] == 5
    assert body["enabled"] is True
    assert body["score_threshold"] is None
    assert body["prompt_template"] is None
    assert body["model_params"] == {}
    assert body["retrieval_mode"] == "dense"  # 默认纯向量


def test_create_app_retrieval_mode_hybrid(client):
    """显式指定 hybrid：创建后 retrieval_mode 正确回显。"""
    body = _create(client, "混合应用", retrieval_mode="hybrid").json()["data"]
    assert body["retrieval_mode"] == "hybrid"


def test_create_app_rejects_invalid_retrieval_mode(client):
    """非法检索模式：422 拒绝。"""
    assert _create(client, "非法模式", retrieval_mode="bm25").status_code == 422


def test_patch_app_retrieval_mode(client):
    """PATCH 切换检索模式：dense → hybrid。"""
    app_id = _create(client, "切换模式").json()["data"]["id"]
    r = client.patch(f"{BASE}/{app_id}", json={"retrieval_mode": "hybrid"})
    assert r.status_code == 200
    assert r.json()["data"]["retrieval_mode"] == "hybrid"


def test_create_app_accepts_valid_prompt_template(client):
    """合法模板（含 {question} 与 {context}）：创建成功。"""
    tmpl = "参考资料：\n{context}\n\n问题：{question}"
    body = _create(client, "合法模板", prompt_template=tmpl).json()["data"]
    assert body["prompt_template"] == tmpl


def test_create_app_rejects_prompt_template_without_question(client):
    """缺 {question} 占位符的模板：422 拒绝，防止问题无法注入。"""
    assert _create(client, "坏模板", prompt_template="回答用户的问题").status_code == 422


def test_patch_app_rejects_prompt_template_without_question(client):
    """PATCH 写坏模板（缺 {question}）：422 拒绝。"""
    app_id = _create(client, "改坏模板").json()["data"]["id"]
    r = client.patch(f"{BASE}/{app_id}", json={"prompt_template": "回答用户的问题"})
    assert r.status_code == 422
