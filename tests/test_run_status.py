import json
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app import main


class FakeRedis:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key):
        return self.values.get(key)


def test_run_status_resolves_public_id_to_rq_job_id(monkeypatch):
    fake_redis = FakeRedis({"run-job:public-run": b"rq-job-123"})
    fake_job = Mock()
    fake_job.get_status.return_value = "started"
    monkeypatch.setattr(main, "redis_conn", fake_redis)
    monkeypatch.setattr(main, "RUNS", {})
    monkeypatch.setattr(main, "queue", Mock(get_jobs=Mock(return_value=[])))
    from rq import job as rq_job
    monkeypatch.setattr(rq_job.Job, "fetch", Mock(return_value=fake_job))

    result = main.get_run("public-run")

    rq_job.Job.fetch.assert_called_once_with("rq-job-123", connection=fake_redis)
    assert result == {"run_id": "public-run", "status": "started"}


def test_completed_result_is_returned_from_redis_before_rq_lookup(monkeypatch):
    expected = {"run_id": "public-run", "status": "completed", "recommendation": "specialist-classification-review"}
    monkeypatch.setattr(main, "redis_conn", FakeRedis({"run-result:public-run": json.dumps(expected)}))
    monkeypatch.setattr(main, "RUNS", {})
    fetch = Mock(side_effect=AssertionError("RQ lookup should not be needed"))
    from rq import job as rq_job
    monkeypatch.setattr(rq_job.Job, "fetch", fetch)

    assert main.get_run("public-run") == expected
    fetch.assert_not_called()


def test_unknown_run_returns_404(monkeypatch):
    monkeypatch.setattr(main, "redis_conn", FakeRedis())
    monkeypatch.setattr(main, "RUNS", {})
    monkeypatch.setattr(main, "queue", Mock(get_jobs=Mock(return_value=[])))
    from rq import job as rq_job
    monkeypatch.setattr(rq_job.Job, "fetch", Mock(side_effect=KeyError("missing")))

    with pytest.raises(HTTPException) as exc:
        main.get_run("unknown-run")
    assert exc.value.status_code == 404


def test_finished_rq_enum_returns_job_result_when_cache_is_missing(monkeypatch):
    from enum import Enum
    from rq import job as rq_job

    class Status(Enum):
        FINISHED = "finished"

    expected = {"run_id": "public-run", "status": "completed", "recommendation": "specialist-classification-review"}
    fake_redis = FakeRedis({"run-job:public-run": b"rq-job-123"})
    fake_job = Mock()
    fake_job.get_status.return_value = Status.FINISHED
    fake_job.result = expected
    monkeypatch.setattr(main, "redis_conn", fake_redis)
    monkeypatch.setattr(main, "RUNS", {})
    monkeypatch.setattr(main, "queue", Mock(get_jobs=Mock(return_value=[])))
    monkeypatch.setattr(rq_job.Job, "fetch", Mock(return_value=fake_job))

    assert main.get_run("public-run") == expected
