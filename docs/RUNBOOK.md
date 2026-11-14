# Operations runbook

## 1. Provider unavailable or slow
Symptom: results escalate with provider_unavailable/circuit_open; retries and
provider failure audit events increase. Confirm /v1/runs/{id}/trace, verifier
metrics provider_circuit_open, and `docker compose logs provider-stub verifier
classifier-worker`. A shared Redis breaker opens after three failed attempts,
blocks calls for 15 seconds, then admits one half-open probe. Recovery: restore
provider configuration/network; wait for cooldown and submit one new request.
Never convert the old unverified run to a successful recommendation. The fallback
is a specialist route with no heading. Reproduce with ENABLE_FAULTS=true and
fault=provider_down or timeout. Disable fault injection after the demo.

## 2. Worker/queue interruption
Symptom: runs stay queued/running, queue depth rises, completion p95 increases.
Confirm `docker compose ps`, `docker compose logs classifier-worker redis`,
RQ job status and Redis queue length. Recovery: restore Redis, then
`docker compose up -d --scale classifier-worker=3`. RQ persists jobs and failed
registries. Polling converts failed/stopped jobs to an explicit escalation; a
five-minute watchdog on status prevents indefinite queued/running responses.
A killed running job is NOT automatically declared complete. Resubmit after
review; duplicate executions are safe because there is no external filing.

Persistent data: Redis AOF holds run state, audit, quarantine metadata, feedback
and queue; index volume holds generations and embedding cache. Back these up
before removal. `docker compose down` preserves volumes. `down -v` deletes them.

The service is a loopback-bound academic deployment. It has demo per-client rate
limits, not authenticated tenant isolation. Add a gateway with authenticated
client identity and restrict internal ports before shared deployment. Audit can
contain submitted product data. Define retention and access controls before
handling confidential descriptions. Quarantine stores body hash and field errors;
it intentionally avoids copying hostile raw inputs into general logs.
