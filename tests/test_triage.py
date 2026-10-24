import json
import pytest
import triage


def test_validate_accepts_good_result():
    good = {"category": "access", "priority": "high", "summary": "s", "suggested_reply": "r"}
    assert triage.validate(good) == good


@pytest.mark.parametrize("bad", [
    {"category": "nope", "priority": "high", "summary": "s", "suggested_reply": "r"},
    {"category": "access", "priority": "asap", "summary": "s", "suggested_reply": "r"},
    {"category": "access", "priority": "high", "summary": "", "suggested_reply": "r"},
    ["not", "a", "dict"],
])
def test_validate_rejects_bad_result(bad):
    with pytest.raises(ValueError):
        triage.validate(bad)


def test_mock_flags_phishing_urgent():
    t = {"id": "x", "subject": "URGENT: possible phishing email", "body": "staff clicked a link"}
    assert triage.classify_mock(t)["priority"] == "urgent"
    assert triage.classify_mock(t)["category"] == "security"


def test_one_failure_does_not_stop_batch():
    tickets = [{"id": "a", "subject": "s", "body": "b"}, {"id": "b", "subject": "s", "body": "b"}]
    def classify(t):
        if t["id"] == "a":
            raise RuntimeError("boom")
        return {"category": "other", "priority": "low", "summary": "s", "suggested_reply": "r"}
    rows = triage.run(tickets, classify)
    assert rows[0]["status"].startswith("failed")
    assert rows[1]["status"] == "ok"


def test_llm_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}
    class R:
        def __init__(self, code, body=None):
            self.status_code = code; self._b = body
        def raise_for_status(self): pass
        def json(self): return self._b
    good = {"choices": [{"message": {"content": json.dumps(
        {"category": "access", "priority": "high", "summary": "s", "suggested_reply": "r"})}}]}
    def fake_post(*a, **k):
        calls["n"] += 1
        return R(429) if calls["n"] == 1 else R(200, good)
    monkeypatch.setattr(triage.requests, "post", fake_post)
    monkeypatch.setattr(triage.time, "sleep", lambda s: None)
    out = triage.classify_llm({"id": "t", "subject": "s", "body": "b"}, "key", "m")
    assert out["category"] == "access" and calls["n"] == 2


def test_llm_rejects_invalid_model_output(monkeypatch):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "{\"category\": \"made_up\"}"}}]}
    monkeypatch.setattr(triage.requests, "post", lambda *a, **k: R())
    monkeypatch.setattr(triage.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        triage.classify_llm({"id": "t", "subject": "s", "body": "b"}, "key", "m", retries=2)


def test_digest_sorts_by_priority_and_lists_failures():
    rows = [
        {"id": "1", "category": "billing", "priority": "low", "summary": "a", "status": "ok"},
        {"id": "2", "category": "security", "priority": "urgent", "summary": "b", "status": "ok"},
        {"id": "3", "status": "failed: x"},
    ]
    lines = triage.build_digest(rows).splitlines()
    assert lines[1].startswith("[URGENT]")
    assert "NEEDS HUMAN" in lines[-1]
