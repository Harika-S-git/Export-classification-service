# Export Classification Service — Operations & Troubleshooting Runbook

## 1. Environment & Architecture Overview

The Export Classification Service consists of five microservices orchestrated via Docker Compose:
- **`api`**: FastAPI service handling REST ingestion, schema validation, rate-limiting, and run-status lookups.
- **`agent-worker`**: RQ background worker executing LangGraph research, classification, and verification graphs.
- **`redis`**: Key-value store and message broker for the `classification` queue, public run mappings, idempotency keys, and quarantined payloads.
- **`prometheus`**: Optional scraper for API `/metrics` (the API endpoint uses port 8000 inside Compose; the host mapping depends on deployment).
- **`grafana`**: Visualization dashboards (port 3000).

---

## 2. Startup & Deployment

### Clean Startup
1. Copy the environment template:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Build and launch services:
   ```powershell
   docker compose up --build -d
   ```
3. Check running containers:
   ```powershell
   docker compose ps
   ```

### Handling Host Port Conflicts (e.g., Port 8000 Occupied)
If another application (such as an unrelated backend) occupies port 8000 on the host machine:
1. Build/start Redis and the worker without publishing their ports:
   ```powershell
   docker compose up -d --build redis agent-worker
   ```
2. Run the API image on host port 8001:
   ```powershell
   docker compose run -d --no-deps -p 8001:8000 --name exportclassification-api-live api
   ```
   If that named Export Classification API container already exists, verify it is the service bound to port 8001 before stopping/removing it; never stop the unrelated service on port 8000.
3. Export the endpoint URL for evaluation runners and benchmarks:
   ```powershell
   $env:API_BASE_URL = "http://localhost:8001"
   ```

---

## 3. Health & Readiness Observability

The service provides distinct endpoints for orchestrators (e.g., Kubernetes / Compose):

| Endpoint | Purpose | Expected Status | Description |
|---|---|---|---|
| `GET /live` | Liveness probe | `200 OK` | Verifies the FastAPI HTTP server process is responsive. |
| `GET /ready` | Readiness probe | `200 OK` / `503 Service Unavailable` | Checks Redis connectivity, active worker count, and queue depth. |
| `GET /health` | Backward-compatible status | `200 OK` | Reports overall status (`ok` or `degraded`). |
| `GET /metrics` | Prometheus metrics | `200 OK` | Exports API process metrics and verification counters read from Redis; Redis must be reachable. |

### Verification Commands
```powershell
# Check liveness
curl.exe http://localhost:8001/live

# Check dependency readiness
curl.exe http://localhost:8001/ready

# Check Prometheus metrics
curl.exe http://localhost:8001/metrics

# Check worker verification outcomes after a completed classification run
curl.exe -s http://localhost:8001/metrics | Select-String "export_verification_total"
```

The worker increments the bounded `outcome` values `failed_citation`, `failed_relevance`, and `passed` in Redis hash `export:metrics:verification`. The API exports these as `export_verification_total{outcome="..."}`. This simple shared counter has no expiry and persists with the Redis data volume; it is not a per-run/event history. Both API and worker must use the same reachable Redis instance. Redis errors are logged by workers; an API scrape that cannot read Redis fails instead of reporting false zero values.

---

## 4. Image Freshness & Stale Container Verification

To prevent debugging stale container images where local changes were not recompiled:

1. **Verify Code SHA-256 Checksums:**
   ```powershell
   # Check local file hash
   Get-FileHash app/core.py -Algorithm SHA256

   # Check container file hash
   docker exec exportclassification-api-live sha256sum /srv/app/core.py
   docker exec exportclassification-agent-worker-1 sha256sum /srv/app/core.py
   ```
2. **Rebuilding Stale Containers:**
   If container hashes differ from local code:
   ```powershell
   docker compose build
   docker compose up -d --no-deps agent-worker
   docker rm -f exportclassification-api-live
   docker compose run -d -p 8001:8000 --name exportclassification-api-live api
   ```

---

## 5. Idempotent Submission Handling

Clients can supply an `X-Idempotency-Key` header with `POST /v1/runs`:
- When an identical key is received within 24 hours, the API returns the existing `run_id` with `idempotent_replay: true` without creating redundant background jobs.
- Example:
  ```powershell
  $headers = @{ "Content-Type" = "application/json"; "X-Idempotency-Key" = "order-ref-987" }
  Invoke-RestMethod -Method Post -Uri "http://localhost:8001/v1/runs" -Headers $headers -Body $body
  ```

---

## 6. Failure Modes & Recovery Procedures

### Failure Mode 1: Redis Unavailable
- **Symptom:** `/ready` returns `503 Not Ready`, submission returns `503 Service Unavailable ("Queue unavailable...")`.
- **Diagnosis:**
  ```powershell
  docker compose logs --tail=50 redis
  docker exec exportclassification-redis-1 redis-cli ping
  ```
- **Recovery:**
  Restart the Redis container:
  ```powershell
  docker compose restart redis
  ```
  Once Redis responds with `PONG`, check that the API and worker reconnected.

### Failure Mode 2: Worker Crushed or Killed
- **Symptom:** Submitted runs stay in `queued` status indefinitely; `/ready` reports `active_workers: 0`.
- **Diagnosis:**
  ```powershell
  docker compose logs --tail=100 agent-worker
  ```
- **Recovery:**
  Restart or scale the agent worker:
  ```powershell
  docker compose restart agent-worker
  # Or scale to multiple workers:
  docker compose up -d --scale agent-worker=3
  ```

### Failure Mode 3: Job Failure in Pipeline
- **Symptom:** Run status transitions to `failed`.
- **Safety Guarantee:** The API guarantees fail-closed behavior:
  - `status`: `"failed"`
  - `recommendation`: `"specialist-classification-review"`
  - `proposed_hs_code`: `null`
  - `verification_passed`: `false`
  The system **never** returns an unverified guess or partial HS code when a background exception occurs.

### Failure Mode 4: Rate Limit Exceeded (HTTP 429)
- **Symptom:** API returns `HTTP 429 Rate limit exceeded` with `Retry-After: <seconds>`.
- **Cause:** Default sliding window enforces `RATE_LIMIT_PER_MINUTE=10` per client IP.
- **Resolution:**
  - Automated clients should honor the `Retry-After` header.
  - In batch testing, `evals/run_batch.py` spaces submissions by 6.2s to operate smoothly under the limit.

### Failure Mode 5: Malformed Request / Prompt Injection Quarantine
- **Symptom:** Request returns `422 Unprocessable Entity` with `quarantined: true`.
- **Diagnosis:** Inspect recent quarantined payloads:
  ```powershell
  curl.exe http://localhost:8001/v1/quarantine/summary
  ```

---

## 7. Operational Testing & Verification Runbook

### Run Full Test Suite
```powershell
.venv\Scripts\python.exe -m pytest -v
```

### Run Batch Evaluation Suite
```powershell
$env:API_BASE_URL = "http://localhost:8001"
.venv\Scripts\python.exe evals/run_batch.py
```

### Run Evaluation Summary & Comparison
```powershell
.venv\Scripts\python.exe evals/evaluate_results.py --results evals/latest_results.json --baseline evals/baseline_before_verification.json --annotations evals/manual_annotations_template.json
```

### Run Performance & Load Benchmark
```powershell
.venv\Scripts\python.exe benchmarks/run_load_test.py --url http://localhost:8001
```
The default bounded run measures 20 health requests at concurrency 1 and 3, six submissions at concurrency 2, then waits 61 seconds before running seven E2E jobs (3 at concurrency 1, 4 at concurrency 2). It writes timestamped workload details, errors, median/p95 latency, throughput, queue wait, and worker duration to `benchmarks/load_test_results.json`. Small samples are diagnostic only, not production-capacity estimates.
