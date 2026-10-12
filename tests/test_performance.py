import json
import pytest
from benchmarks import run_load_test


def test_benchmark_read_endpoint_calculates_statistics():
    fake_results = [(200, b"ok", 0.010), (200, b"ok", 0.020), (200, b"ok", 0.030)]

    def fake_req(*args, **kwargs):
        return fake_results.pop(0)

    # Monkeypatch http_request
    original_http = run_load_test.http_request
    run_load_test.http_request = fake_req
    try:
        summary = run_load_test.benchmark_read_endpoint("http://localhost:8001", concurrency=1, total_requests=3)
        assert summary["total_requests"] == 3
        assert summary["p50_latency_ms"] == 20.0
        assert summary["error_count"] == 0
        assert summary["error_rate"] == 0.0
    finally:
        run_load_test.http_request = original_http


def test_percentile_uses_nearest_rank_for_small_samples():
    assert run_load_test.percentile(list(range(1, 21)), 0.95) == 19
    assert run_load_test.percentile([1.0, 2.0, 3.0], 0.95) == 3.0


def test_benchmark_submission_separates_errors_and_rate_limits():
    fake_results = [
        (202, b'{"run_id":"r1","status_url":"/v1/runs/r1"}', 0.015),
        (429, b'Rate limit exceeded', 0.005),
    ]

    def fake_req(*args, **kwargs):
        return fake_results.pop(0)

    original_http = run_load_test.http_request
    run_load_test.http_request = fake_req
    try:
        summary = run_load_test.benchmark_submission_endpoint("http://localhost:8001", concurrency=1, total_requests=2)
        assert summary["total_requests"] == 2
        assert summary["accepted_202_count"] == 1
        assert summary["error_count"] == 1
        assert summary["status_counts"][202] == 1
        assert summary["status_counts"][429] == 1
    finally:
        run_load_test.http_request = original_http
