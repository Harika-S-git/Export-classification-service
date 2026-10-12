import json
from unittest.mock import Mock, patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main, core
from app.main import app, ProductRequest


client = TestClient(app)


def test_live_endpoint_returns_ok():
    response = client.get("/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_ready_endpoint_returns_ready_when_redis_connected(monkeypatch):
    fake_redis = Mock()
    fake_redis.ping.return_value = True
    monkeypatch.setattr(main, "redis_conn", fake_redis)
    fake_queue = Mock()
    fake_queue.name = "classification"
    fake_queue.count = 0
    monkeypatch.setattr(main, "queue", fake_queue)

    with patch("rq.Worker.count", return_value=1):
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["redis"] == "ok"
        assert data["active_workers"] == 1


def test_ready_endpoint_returns_503_when_redis_unavailable(monkeypatch):
    fake_redis = Mock()
    fake_redis.ping.side_effect = ConnectionError("Redis is down")
    monkeypatch.setattr(main, "redis_conn", fake_redis)

    response = client.get("/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["redis"] == "unavailable"


def test_submission_returns_503_when_redis_queue_unavailable(monkeypatch):
    fake_queue = Mock()
    fake_queue.enqueue.side_effect = ConnectionError("Cannot reach Redis queue")
    monkeypatch.setattr(main, "queue", fake_queue)

    payload = {
        "description": "Steel bolts for construction",
        "destination_country": "United States",
    }
    response = client.post("/v1/runs", json=payload)
    assert response.status_code == 503
    assert "Queue unavailable" in response.json()["detail"]


def test_idempotent_submission_returns_cached_run_id(monkeypatch):
    fake_redis = Mock()
    fake_redis.get.return_value = b"cached-run-uuid-123"
    monkeypatch.setattr(main, "redis_conn", fake_redis)

    payload = {
        "description": "Steel bolts for construction",
        "destination_country": "United States",
    }
    response = client.post("/v1/runs", json=payload, headers={"X-Idempotency-Key": "unique-order-abc"})
    assert response.status_code == 202
    data = response.json()
    assert data["run_id"] == "cached-run-uuid-123"
    assert data.get("idempotent_replay") is True


def test_worker_job_failure_returns_safe_specialist_escalation(monkeypatch):
    from rq.job import Job
    fake_redis = Mock()
    fake_redis.get.side_effect = lambda k: b"job-fail-1" if k == "run-job:run-fail" else None
    fake_job = Mock()
    fake_job.get_status.return_value = "failed"
    monkeypatch.setattr(main, "redis_conn", fake_redis)
    monkeypatch.setattr(main, "RUNS", {})
    monkeypatch.setattr(Job, "fetch", Mock(return_value=fake_job))

    result = main.get_run("run-fail")
    assert result["status"] == "failed"
    assert result["recommendation"] == "specialist-classification-review"
    assert result["proposed_hs_code"] is None
    assert result["verification_passed"] is False


def test_missing_or_invalid_request_data_is_quarantined_and_returns_422():
    # Description shorter than 8 chars
    payload = {"description": "short", "destination_country": "United States"}
    response = client.post("/v1/runs", json=payload)
    assert response.status_code == 422
    assert response.json()["quarantined"] is True


def test_citation_resolution_failure_clears_code_and_escalates(monkeypatch):
    # Citation does not resolve to canonical passages
    monkeypatch.setattr(core, "load_passages", lambda: [])
    state: core.AgentState = {
        "request": {"description": "Stainless steel pipe"},
        "passages": [{"id": "unresolved.txt#p1", "text": "Some text"}],
        "proposed_code": "7304.11",
        "route": "clear-for-filing",
        "warnings": [],
        "steps": [],
    }
    result = core._verify(state)
    assert result["verified"] is False
    assert result["citation_resolution_passed"] is False
    assert result["proposed_code"] is None
    assert result["route"] == "specialist-classification-review"


def test_evidence_relevance_failure_clears_code_and_escalates(monkeypatch):
    canonical = [
        {"id": "doc.txt#p1", "text": "Apples and oranges are agricultural fruit produce."}
    ]
    monkeypatch.setattr(core, "load_passages", lambda: canonical)
    state: core.AgentState = {
        "request": {"description": "Stainless steel pipe for fluid transport"},
        "passages": canonical,
        "proposed_code": "7304.11",
        "route": "clear-for-filing",
        "warnings": [],
        "steps": [],
    }
    result = core._verify(state)
    assert result["verified"] is False
    assert result["evidence_relevance_passed"] is False
    assert result["proposed_code"] is None
    assert result["route"] == "specialist-classification-review"


def test_vague_description_preserves_seek_product_clarification():
    state: core.AgentState = {
        "request": {"description": "unspecified manufactured item"},
        "passages": [],
        "warnings": [],
        "steps": [],
    }
    result = core._classify(state)
    assert result["route"] == "seek-product-clarification"
    assert result["proposed_code"] is None
    assert "missing" in result["rationale"].lower() or "clarification" in result["warnings"][0].lower()
