"""Run the fixed scenario set against a live local API; preserve failures honestly."""
import json
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "http://localhost:8000"
MAX_RETRIES = 5
POLL_TIMEOUT_SECONDS = 100
SUBMISSION_INTERVAL_SECONDS = 6.2  # stays below the default 10 submissions/minute limit


def _retry_delay(error, attempt):
    """Honor Retry-After (seconds or HTTP date), otherwise use bounded backoff."""
    header = error.headers.get("Retry-After") if getattr(error, "headers", None) else None
    if header:
        try:
            return min(60.0, max(0.0, float(header)))
        except ValueError:
            try:
                return min(60.0, max(0.0, (parsedate_to_datetime(header).timestamp() - time.time())))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(16.0, 1.0 * (2 ** attempt))


def request_json(url, *, data=None, headers=None, timeout=10, retries=MAX_RETRIES):
    """HTTP JSON request with bounded retry for rate limits and transient server errors."""
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method="POST" if data is not None else "GET"
    )
    retryable = {429, 500, 502, 503, 504}
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code not in retryable or attempt >= retries:
                raise
            delay = _retry_delay(exc, attempt)
            print(f"HTTP {exc.code} for {url}; retry {attempt + 1}/{retries} in {delay:.1f}s")
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt >= retries:
                raise
            delay = min(16.0, 1.0 * (2 ** attempt))
            print(f"Temporary request error for {url}: {exc}; retry in {delay:.1f}s")
            time.sleep(delay)
    raise RuntimeError("Retry loop ended unexpectedly")


def run_one(scenario, last_submit_time):
    now = time.monotonic()
    wait = SUBMISSION_INTERVAL_SECONDS - (now - last_submit_time)
    if last_submit_time and wait > 0:
        time.sleep(wait)

    body = {
        "description": scenario["description"],
        "destination_country": "United States",
        "country_of_export": "India",
        "client_id": "batch-eval",
    }
    payload = json.dumps(body).encode("utf-8")
    job = request_json(
        BASE + "/v1/runs",
        data=payload,
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    submitted_at = time.monotonic()
    status_url = job.get("status_url")
    if not status_url:
        raise RuntimeError("Submission response did not contain status_url")

    deadline = submitted_at + POLL_TIMEOUT_SECONDS
    out = None
    last_poll_error = None
    while time.monotonic() < deadline:
        try:
            out = request_json(BASE + status_url, timeout=10)
            last_poll_error = None
            if out.get("status") in ("completed", "failed"):
                break
        except urllib.error.HTTPError as exc:
            # 404 is not transient unless the service fixes its run mapping; keep
            # polling briefly because a just-submitted mapping can race startup.
            if exc.code not in {404, 429, 500, 502, 503, 504}:
                raise
            last_poll_error = f"HTTP {exc.code}: {exc.reason}"
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_poll_error = str(exc)
        time.sleep(1)

    latency = round(time.monotonic() - submitted_at, 3)
    if out is None or out.get("status") not in ("completed", "failed"):
        return {
            "scenario_id": scenario["id"],
            "expected_route": scenario["expected_route"],
            "actual_route": (out or {}).get("recommendation"),
            "status": (out or {}).get("status", "poll_timeout"),
            "latency_seconds": latency,
            "route_match": False,
            "verification_passed": False,
            "error": last_poll_error or "Timed out waiting for terminal run status",
            "result": out,
        }

    actual = out.get("recommendation")
    terminal_status = out.get("status")
    # A route match is only a route-level test, not proof of legal correctness.
    route_match = terminal_status == "completed" and actual == scenario["expected_route"]
    return {
        "scenario_id": scenario["id"],
        "expected_route": scenario["expected_route"],
        "actual_route": actual,
        "status": terminal_status,
        "latency_seconds": latency,
        "route_match": route_match,
        "verification_passed": bool(out.get("verification_passed", False)),
        "error": (out.get("error") or out.get("error_type") or "Background job failed") if terminal_status == "failed" else None,
        "result": out,
    }


def main():
    scenarios = json.loads((ROOT / "scenarios.json").read_text(encoding="utf-8"))
    results = []
    last_submit_time = 0.0
    for scenario in scenarios:
        try:
            result = run_one(scenario, last_submit_time)
            # Count submission pacing from this run's start, including any retry wait.
            last_submit_time = time.monotonic()
        except Exception as exc:
            result = {
                "scenario_id": scenario.get("id", "UNKNOWN"),
                "expected_route": scenario.get("expected_route"),
                "actual_route": None,
                "status": "request_error",
                "latency_seconds": None,
                "route_match": False,
                "verification_passed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "result": None,
            }
            last_submit_time = time.monotonic()
        results.append(result)
        print(
            f"{result['scenario_id']}: status={result['status']} "
            f"expected={result.get('expected_route')} actual={result.get('actual_route')} "
            f"route_match={result['route_match']} error={result.get('error')}"
        )

    outpath = ROOT / "latest_results.json"
    outpath.write_text(json.dumps(results, indent=2), encoding="utf-8")
    completed = sum(r.get("status") == "completed" for r in results)
    matches = sum(bool(r.get("route_match")) for r in results)
    errors = sum(bool(r.get("error")) for r in results)
    print(f"Saved {len(results)} raw results to {outpath}")
    print(f"Completed: {completed}/{len(results)}; route matches: {matches}/{len(results)}; errors: {errors}")
    print("Route matches are not legal-correctness scores. Manually label passage relevance and claim support before reporting groundedness, context relevance, faithfulness, or hallucination rate.")


if __name__ == "__main__":
    main()
