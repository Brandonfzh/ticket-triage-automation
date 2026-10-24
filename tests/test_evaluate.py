import evaluate


def test_evaluate_scores_correctly():
    items = [
        {"id": "a", "subject": "s", "body": "b", "expected_category": "access", "expected_priority": "high"},
        {"id": "b", "subject": "s", "body": "b", "expected_category": "billing", "expected_priority": "low"},
    ]
    def classify(t):
        return {"category": "access", "priority": "high"} if t["id"] == "a" else {"category": "other", "priority": "low"}
    r = evaluate.evaluate(items, classify)
    assert r["n"] == 2
    assert r["category_accuracy"] == 0.5
    assert r["priority_accuracy"] == 1.0
    assert len(r["misses"]) == 1
