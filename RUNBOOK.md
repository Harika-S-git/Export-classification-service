# Runbook

## Start and smoke-test
1. Copy `.env.example` to `.env`; replace the example Grafana password.
2. Add current, verified CBIC/DGFT source text to `corpus/` before attempting legal classification.
3. Run `docker compose up --build -d`, then `docker compose ps`.
4. Check `curl.exe http://localhost:8000/health`, `/docs`, `/metrics`, Prometheus on port 9090 and Grafana on port 3000.
5. Submit a valid product request and poll the returned `status_url`. Specialist review is expected when the official corpus cannot support the decision.

## Failure mode 1 — requests remain queued
- **Symptom:** run remains queued or submission returns 503.
- **Confirm:** `docker compose ps`; `docker compose logs --tail=200 redis agent-worker api`; check `/health`.
- **Recover:** `docker compose restart redis agent-worker api`. Retry only after Redis health is green. Never mark a failed run as completed manually.

## Failure mode 2 — no citation or unexpected escalation
- **Symptom:** result has no citations or routes to specialist review.
- **Confirm:** inspect result `steps`, `citations`, `warnings`, worker logs, and files under `corpus/`.
- **Recover:** add current official text with headings and notes preserved, rebuild/reload the index, and rerun the fixed evaluation set. Never fix this by hardcoding a desired HS code.

## Load testing
Use deterministic stub mode only for service-performance tests; it is not legal classification evidence. Record test date, git commit, worker count, concurrency, RPS, p50/p95 and failures. Compare one worker with three workers. Keep actual measured output with the submission.
