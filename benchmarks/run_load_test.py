#!/usr/bin/env python3
"""Reproducible performance and load testing suite for Export Classification Service.

Tests:
1. Health check read latency and throughput (GET /health)
2. API Submission latency and rate limit behavior (POST /v1/runs)
3. End-to-end asynchronous lifecycle (POST /v1/runs -> poll GET /v1/runs/{id} to terminal status)

Measures:
- Throughput (RPS)
- p50 (median) latency
- p95 latency
- p99 latency
- Error rate
- Separation of API response time vs asynchronous background job processing time
"""

import argparse
import concurrent.futures
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SAMPLE_PAYLOAD = {
    "description": "Stainless steel vacuum flask with a moulded plastic outer body",
    "materials": ["stainless steel", "plastic"],
    "intended_use": "Reusable beverage container",
    "country_of_export": "India",
    "destination_country": "United States",
    "client_id": "load-test-client",
}


def percentile(values: List[float], fraction: float) -> float:
    """Return a nearest-rank percentile for a non-empty sample."""
    if not values:
        return 0.0
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be between 0 and 1")
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def http_request(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
) -> Tuple[int, bytes, float]:
    """Execute an HTTP request and measure precise round-trip latency."""
    req_headers = headers or {}
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        content = exc.read()
        status = exc.code
    except Exception as exc:
        latency = time.perf_counter() - start
        return 0, str(exc).encode(), latency

    latency = time.perf_counter() - start
    return status, content, latency


def benchmark_read_endpoint(
    base_url: str,
    endpoint: str = "/health",
    concurrency: int = 1,
    total_requests: int = 50,
) -> Dict[str, Any]:
    """Benchmark a read endpoint across specified concurrency."""
    url = f"{base_url.rstrip('/')}{endpoint}"
    latencies: List[float] = []
    status_counts: Dict[int, int] = {}
    errors = 0

    def single_req(_) -> Tuple[int, float]:
        status, _, lat = http_request(url)
        return status, lat

    wall_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(single_req, range(total_requests)))
    wall_duration = time.perf_counter() - wall_start

    for status, lat in results:
        latencies.append(lat)
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != 200:
            errors += 1

    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = percentile(latencies, 0.95)
    p99 = percentile(latencies, 0.99)
    rps = (total_requests / wall_duration) if wall_duration > 0 else 0.0

    return {
        "endpoint": endpoint,
        "concurrency": concurrency,
        "total_requests": total_requests,
        "wall_duration_seconds": round(wall_duration, 4),
        "rps": round(rps, 2),
        "p50_latency_ms": round(p50 * 1000, 2),
        "p95_latency_ms": round(p95 * 1000, 2),
        "p99_latency_ms": round(p99 * 1000, 2),
        "status_counts": status_counts,
        "error_count": errors,
        "error_rate": round(errors / total_requests, 4) if total_requests > 0 else 0.0,
    }


def benchmark_submission_endpoint(
    base_url: str,
    concurrency: int = 1,
    total_requests: int = 10,
    client_prefix: str = "bench",
) -> Dict[str, Any]:
    """Benchmark POST /v1/runs submission latency and observe rate limit behavior."""
    url = f"{base_url.rstrip('/')}/v1/runs"
    latencies: List[float] = []
    status_counts: Dict[int, int] = {}
    errors = 0
    run_ids: List[str] = []

    def single_submit(i: int) -> Tuple[int, bytes, float]:
        payload = dict(SAMPLE_PAYLOAD)
        payload["client_id"] = f"{client_prefix}-{i}"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        return http_request(url, method="POST", data=data, headers=headers)

    wall_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(single_submit, range(total_requests)))
    wall_duration = time.perf_counter() - wall_start

    for status, content, lat in results:
        latencies.append(lat)
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == 202:
            try:
                body = json.loads(content)
                run_ids.append(body.get("run_id"))
            except Exception:
                pass
        else:
            errors += 1

    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = percentile(latencies, 0.95)
    p99 = percentile(latencies, 0.99)
    rps = (total_requests / wall_duration) if wall_duration > 0 else 0.0

    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "accepted_202_count": len(run_ids),
        "wall_duration_seconds": round(wall_duration, 4),
        "submission_rps": round(rps, 2),
        "submission_p50_ms": round(p50 * 1000, 2),
        "submission_p95_ms": round(p95 * 1000, 2),
        "submission_p99_ms": round(p99 * 1000, 2),
        "status_counts": status_counts,
        "error_count": errors,
        "error_rate": round(errors / total_requests, 4) if total_requests > 0 else 0.0,
        "run_ids": run_ids,
    }


def benchmark_end_to_end_lifecycle(
    base_url: str,
    concurrency: int = 1,
    total_jobs: int = 5,
    poll_interval: float = 0.5,
    poll_timeout: float = 60.0,
) -> Dict[str, Any]:
    """Benchmark end-to-end user journey: submit -> poll -> terminal result.

    Distinguishes:
    - Submission latency (HTTP POST time)
    - Total job completion time (submission to terminal result)
    - Asynchronous processing time (worker processing duration)
    - Queue wait time estimate (completion time minus worker duration)
    """
    submit_url = f"{base_url.rstrip('/')}/v1/runs"

    def run_lifecycle(index: int) -> Dict[str, Any]:
        payload = dict(SAMPLE_PAYLOAD)
        payload["client_id"] = f"e2e-bench-{index}"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        # 1. Submission (with bounded retry if rate-limited)
        submit_status, submit_body, submit_latency = 0, b"", 0.0
        max_sub_retries = 3
        for attempt in range(max_sub_retries + 1):
            submit_status, submit_body, submit_latency = http_request(
                submit_url, method="POST", data=data, headers=headers
            )
            if submit_status == 202:
                break
            if submit_status == 429 and attempt < max_sub_retries:
                time.sleep(3.0 + attempt * 2.0)

        if submit_status != 202:
            return {
                "success": False,
                "submit_status": submit_status,
                "submit_latency": submit_latency,
                "error": f"HTTP {submit_status}",
                "e2e_duration": submit_latency,
            }

        try:
            submit_data = json.loads(submit_body)
            status_url = f"{base_url.rstrip('/')}{submit_data['status_url']}"
            run_id = submit_data["run_id"]
        except Exception as exc:
            return {
                "success": False,
                "submit_status": submit_status,
                "submit_latency": submit_latency,
                "error": f"Failed to parse submission: {exc}",
                "e2e_duration": submit_latency,
            }

        # 2. Polling loop
        e2e_start = time.perf_counter()
        deadline = e2e_start + poll_timeout
        poll_count = 0
        final_result = None

        while time.perf_counter() < deadline:
            poll_count += 1
            p_status, p_body, _ = http_request(status_url)
            if p_status == 200:
                try:
                    p_data = json.loads(p_body)
                    state = p_data.get("status")
                    if state in ("completed", "failed"):
                        final_result = p_data
                        break
                except Exception:
                    pass
            time.sleep(poll_interval)

        e2e_duration = time.perf_counter() - e2e_start
        if not final_result:
            return {
                "success": False,
                "run_id": run_id,
                "submit_latency": submit_latency,
                "poll_count": poll_count,
                "e2e_duration": e2e_duration,
                "error": "Poll timeout exceeded",
            }

        worker_duration = final_result.get("duration_seconds", 0.0)
        queue_wait = max(0.0, e2e_duration - worker_duration)

        return {
            "success": True,
            "run_id": run_id,
            "status": final_result.get("status"),
            "submit_latency": submit_latency,
            "poll_count": poll_count,
            "e2e_duration": e2e_duration,
            "worker_duration": worker_duration,
            "queue_wait_estimate": queue_wait,
            "recommendation": final_result.get("recommendation"),
            "verification_passed": final_result.get("verification_passed"),
        }

    wall_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        job_results = list(executor.map(run_lifecycle, range(total_jobs)))
    wall_duration = time.perf_counter() - wall_start

    successful = [r for r in job_results if r["success"]]
    e2e_times = sorted([r["e2e_duration"] for r in successful])
    submit_times = sorted([r["submit_latency"] for r in job_results])
    worker_times = sorted([r["worker_duration"] for r in successful if "worker_duration" in r])
    queue_waits = sorted([r["queue_wait_estimate"] for r in successful if "queue_wait_estimate" in r])

    return {
        "concurrency": concurrency,
        "total_jobs": total_jobs,
        "successful_jobs": len(successful),
        "wall_duration_seconds": round(wall_duration, 4),
        "throughput_jobs_per_sec": round(len(successful) / wall_duration, 2) if wall_duration > 0 else 0.0,
        "submit_latency_median_ms": round(statistics.median(submit_times) * 1000, 2) if submit_times else 0.0,
        "e2e_median_seconds": round(statistics.median(e2e_times), 3) if e2e_times else 0.0,
        "e2e_p95_seconds": round(percentile(e2e_times, 0.95), 3),
        "worker_median_seconds": round(statistics.median(worker_times), 4) if worker_times else 0.0,
        "queue_wait_median_seconds": round(statistics.median(queue_waits), 3) if queue_waits else 0.0,
        "error_count": total_jobs - len(successful),
        "job_details": job_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Performance and Load Testing for Export Classification Service.")
    parser.add_argument("--url", default=os.getenv("API_BASE_URL", "http://localhost:8001"), help="Target API URL")
    parser.add_argument("--mode", choices=["all", "read", "submit", "e2e"], default="all", help="Test mode")
    parser.add_argument("--output", default="benchmarks/load_test_results.json", help="Path to save results JSON")
    parser.add_argument(
        "--rate-limit-cooldown-seconds",
        type=float,
        default=61.0,
        help="Cooldown between submission and E2E phases in all mode",
    )
    args = parser.parse_args()

    base_url = args.url
    print(f"Targeting API endpoint: {base_url}")

    # Check API health before starting
    status, body, lat = http_request(f"{base_url}/health")
    if status != 200:
        print(f"ERROR: API health check failed at {base_url}/health: HTTP {status} ({body.decode(errors='ignore')})")
        sys.exit(1)
    print(f"API is healthy (health round-trip: {lat*1000:.1f}ms). Starting warmup...")

    # Warmup
    for _ in range(5):
        http_request(f"{base_url}/health")
    print("Warmup complete.\n")

    timestamp = time.time()
    results_report = {
        "target_url": base_url,
        "timestamp": timestamp,
        "timestamp_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        "sample_note": (
            "Bounded student-project benchmark samples; results are not a "
            "production capacity guarantee."
        ),
        "workload": {
            "read_requests_per_concurrency": 20,
            "read_concurrency_levels": [1, 3],
            "submission_requests": 6,
            "submission_concurrency": 2,
            "e2e_jobs": [{"concurrency": 1, "jobs": 3}, {"concurrency": 2, "jobs": 4}],
            "rate_limit_cooldown_seconds": args.rate_limit_cooldown_seconds,
            "rate_limit_note": (
                "The submission benchmark is limited to six requests. In all "
                "mode, a cooldown precedes the separate seven-job E2E phase."
            ),
        },
        "runs": {},
    }
    outpath = Path(args.output)
    if outpath.exists():
        previous = json.loads(outpath.read_text(encoding="utf-8"))
        previous_history = previous.get("previous_e2e_benchmark_history", [])
        if previous.get("previous_e2e_benchmark"):
            previous_history.append(previous["previous_e2e_benchmark"])
        old_e2e = previous.get("runs", {}).get("e2e_benchmark")
        if old_e2e:
            results_report["previous_e2e_benchmark"] = {
                "timestamp": previous.get("timestamp"),
                "runs": old_e2e,
            }
        if previous_history:
            results_report["previous_e2e_benchmark_history"] = previous_history

    if args.mode in ("all", "read"):
        print("=== 1. READ ENDPOINT BENCHMARK (GET /health) ===")
        read_results = []
        for c in (1, 3):
            res = benchmark_read_endpoint(base_url, endpoint="/health", concurrency=c, total_requests=20)
            read_results.append(res)
            print(f"  Concurrency {c:2d}: {res['rps']:6.1f} RPS | Median: {res['p50_latency_ms']:5.1f} ms | p95: {res['p95_latency_ms']:5.1f} ms | Errors: {res['error_count']}")
        results_report["runs"]["read_benchmark"] = read_results

    if args.mode in ("all", "submit"):
        print("\n=== 2. SUBMISSION BENCHMARK (POST /v1/runs) ===")
        # Keep total within default rate limit (10 per minute) to measure clean submission latency
        sub_res = benchmark_submission_endpoint(base_url, concurrency=2, total_requests=6)
        print(f"  Concurrency 2: {sub_res['submission_rps']:5.1f} RPS | Median: {sub_res['submission_p50_ms']:5.1f} ms | p95: {sub_res['submission_p95_ms']:5.1f} ms | 202 Accepted: {sub_res['accepted_202_count']}/{sub_res['total_requests']}")
        results_report["runs"]["submission_benchmark"] = sub_res

    if args.mode in ("all", "e2e"):
        if args.mode == "all" and "submission_benchmark" in results_report["runs"]:
            print(
                f"\nWaiting {args.rate_limit_cooldown_seconds:.0f}s for the "
                "submission rate-limit window to clear..."
            )
            time.sleep(args.rate_limit_cooldown_seconds)
        print("\n=== 3. END-TO-END ASYNCHRONOUS USER JOURNEY ===")
        print("  (POST /v1/runs -> poll GET /v1/runs/{id} until terminal state)")
        e2e_results = []
        # Keep the E2E sample bounded and below the per-minute submission limit.
        for c, count in [(1, 3), (2, 4)]:
            e2e = benchmark_end_to_end_lifecycle(base_url, concurrency=c, total_jobs=count, poll_interval=0.5)
            e2e_results.append(e2e)
            print(f"  Concurrency {c:2d} ({count} jobs):")
            print(f"    Completed:               {e2e['successful_jobs']}/{e2e['total_jobs']}")
            print(f"    Submit Median:           {e2e['submit_latency_median_ms']:.1f} ms")
            print(f"    Worker Median:           {e2e['worker_median_seconds']:.3f} s")
            print(f"    Queue Wait Estimate:     {e2e['queue_wait_median_seconds']:.3f} s")
            print(f"    E2E Median Duration:     {e2e['e2e_median_seconds']:.3f} s")
            print(f"    E2E p95 Duration:        {e2e['e2e_p95_seconds']:.3f} s")
            print(f"    Throughput:              {e2e['throughput_jobs_per_sec']:.2f} jobs/sec")
        results_report["runs"]["e2e_benchmark"] = e2e_results

    # Save results
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(json.dumps(results_report, indent=2), encoding="utf-8")
    print(f"\nSaved benchmark results to {outpath}")


if __name__ == "__main__":
    main()
