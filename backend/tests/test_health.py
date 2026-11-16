"""/health 冒烟测试（Plan 1 Task 1 Step 7）。"""


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
