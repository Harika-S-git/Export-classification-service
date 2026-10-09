# Runbook

## Start and smoke-test
1. Copy `.env.example` to `.env`; replace the example Grafana password.
2. Add current, verified CBIC/DGFT source text to `corpus/` before attempting legal classification.
3. Run `docker compose up --build -d`, then `docker compose ps`.
4. Check `curl.exe http://localhost:8000/health`, `/docs`, `/metrics`, Prometheus on port 9090 and Grafana on port 3000.
5. Submit a valid product request and poll the returned `status_url`. The API stores `run-job:{run_id}` in Redis to map the public run ID to its RQ job ID, and returns cached `run-result:{run_id}` output when available. Specialist review is expected when the official corpus cannot support the decision.

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


## Evaluation runner recovery
- Run `python evals/run_batch.py` from the repository root while the Compose stack is healthy.
- The runner spaces submissions to stay under the default per-IP limit of 10 requests/minute and retries HTTP 429 and transient 5xx/connection failures with bounded backoff. The API sends `Retry-After` on 429 responses; do not disable rate limiting to make the batch pass.
- Inspect the per-scenario console summary and `evals/latest_results.json`. Failed, timed-out, or unpolled runs must remain failures and must never count as route matches.
- If a run status returns 404, inspect `run-job:{run_id}`, `run-result:{run_id}`, the API logs, and whether API and worker use the same Redis URL. Do not rely on finished jobs remaining in the RQ queue registry.
- The current lexical token-overlap retriever can return weakly related passages. The citation verifier checks citation-ID existence against retrieved corpus text; it does not verify source authority, relevance, legal reasoning, or claim entailment. Treat `verification_passed` as a narrow technical check, not a legal-quality metric. Manually annotate relevance and claim support before calculating evaluation metrics.
