import io
import json
import urllib.error
from email.message import Message

from evals import run_batch


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_request_json_retries_429_and_honors_retry_after(monkeypatch):
    headers = Message()
    headers["Retry-After"] = "0"
    rate_limited = urllib.error.HTTPError(
        "http://localhost:8000/v1/runs", 429, "Too Many Requests", headers, io.BytesIO(b"")
    )
    responses = iter([rate_limited, FakeResponse({"ok": True})])
    sleeps = []
    monkeypatch.setattr(run_batch.urllib.request, "urlopen", lambda *a, **k: next(responses))
    monkeypatch.setattr(run_batch.time, "sleep", sleeps.append)

    assert run_batch.request_json("http://localhost:8000/v1/runs", retries=1) == {"ok": True}
    assert sleeps == [0.0]


def test_failed_run_is_never_reported_as_route_match(monkeypatch):
    responses = iter([
        {"status_url": "/v1/runs/run-1"},
        {
            "run_id": "run-1",
            "status": "failed",
            "recommendation": "specialist-classification-review",
            "verification_passed": False,
            "error_type": "RuntimeError",
        },
    ])
    monkeypatch.setattr(run_batch, "request_json", lambda *a, **k: next(responses))
    monkeypatch.setattr(run_batch.time, "sleep", lambda *_: None)
    scenario = {
        "id": "S-test",
        "description": "A sample manufactured item",
        "expected_route": "specialist-classification-review",
    }

    result = run_batch.run_one(scenario, 0.0)

    assert result["status"] == "failed"
    assert result["route_match"] is False
    assert result["verification_passed"] is False
    assert result["error"] == "RuntimeError"
