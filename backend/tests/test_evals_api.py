"""检索评测 API（二期 Task 28 可视化）。挂载 /api/v1/admin/evals。

锁定点：GET /evals/ablation 读 data/legal/ablation_result.json，返回三路指标 + 元信息。
"""
from pathlib import Path

BASE = "/api/v1/admin/evals"

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RESULT = _PROJECT_ROOT / "data" / "legal" / "ablation_result.json"


def test_ablation_result(client):
    """读取消融结果：三路 results + 元信息完整。"""
    assert _RESULT.exists(), "ablation_result.json 应随仓库落盘"

    r = client.get(f"{BASE}/ablation")
    assert r.status_code == 200
    body = r.json()["data"]

    # 元信息
    assert body["top_k"] == 5
    assert body["n_items"] == 90
    assert body["n_chunks"] == 233
    assert body["rrf_k"] == 60
    assert body["eval_kb"] == "kb-eval-legal"

    # 三路结果齐全，指标落在 [0,1]
    results = {item["key"]: item for item in body["results"]}
    assert set(results) == {"dense", "sparse", "hybrid"}
    for item in results.values():
        assert 0.0 <= item["recall_at_k"] <= 1.0
        assert 0.0 <= item["mrr"] <= 1.0
        assert 0.0 <= item["hit_at_k"] <= 1.0

    # 混合检索 Recall 不劣于单路（本实验结论）
    assert results["hybrid"]["recall_at_k"] >= results["dense"]["recall_at_k"]
    assert results["hybrid"]["recall_at_k"] >= results["sparse"]["recall_at_k"]
