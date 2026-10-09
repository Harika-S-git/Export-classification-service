# Mini Project 07 — Export Classification Check Service

**Course:** UE24AM342AA5 — ML System Design and AgentOps  
**Status:** Engineering report template; measured values must be filled from an actual run before submission.

## 1. Problem and scope

The service accepts an export product description, validates it, asynchronously researches tariff text, and returns a recommendation route with citations or escalates to a specialist. It does not file declarations, calculate duty, or replace a licensed customs broker. The assignment's difficult reference case is “Stainless steel vacuum flask with a moulded plastic outer body.”

## 2. Architecture and deployment boundaries

FastAPI validates the contract and submits work to Redis/RQ. The worker executes a bounded LangGraph research → classification → verification flow. Redis separates request acceptance from processing and stores completed results/feedback. Prometheus scrapes API metrics; Grafana displays operational metrics. The API, worker, Redis, Prometheus and Grafana are separate Compose services so the worker can scale independently and queue failures do not block the HTTP process.

    Client → FastAPI (schema / guardrails / correlation ID) → Redis + RQ queue
    Redis + RQ → Agent worker → Research tools → Classification → Evidence verification
    FastAPI → Prometheus → Grafana

## 3. Agent topology, tools, verification and limits

The research, classification and verification nodes have distinct responsibilities and explicit hand-offs. Available tools are request-field lookup, lexical corpus search and clause lookup. The graph uses a recursion limit; the queue job has a configurable wall-clock timeout. The verifier resolves citation IDs against indexed source text and fails closed. If required evidence is missing, the system returns specialist review rather than inventing an HS code.

**Important corpus boundary:** the repository does not bundle a legally verified, current CBIC/DGFT corpus. Do not treat starter/sample text as authoritative. The vacuum-flask reference case cannot be considered correctly classified until the official named-article heading, applicable GRI and notes are loaded and independently verified.

## 4. Design decisions and alternatives

- **FastAPI + Redis/RQ:** chosen for a documented REST contract and asynchronous execution; synchronous processing was rejected because runs may take tens of seconds.
- **LangGraph:** chosen for explicit agent hand-offs and bounded graph execution.
- **Fail-closed routing:** chosen over material-only code prediction because tariff notes and named-article headings can override a superficial material match.
- **Lexical retrieval is currently a baseline.** The assignment asks for FAISS or Chroma plus an idempotent ingestion/indexing command; that requirement is not proven complete by the lexical baseline.
- **No external model provider is enabled in the current implementation.** Therefore provider circuit-breaker behaviour, token accounting and model cost cannot be claimed as implemented or measured.

## 5. Evaluation plan and results

The fixed starter set is `evals/scenarios.json` (20 scenarios). Expected routes are test hypotheses, not legally adjudicated HS-code gold labels. Run the service and `python evals/run_batch.py`; retain `evals/latest_results.json`. Manually label passage relevance and factual claim support before calculating the metrics below.

| Metric | Definition |
|---|---|
| Groundedness | Supported factual claims / all factual claims reviewed |
| Context relevance | Retrieved passages labelled relevant / all retrieved passages reviewed |
| Faithfulness | Answer claims entailed by cited context / answer claims reviewed |
| Hallucination rate | Unsupported factual claims / all factual claims reviewed |

**Before/after prompt comparison:** not yet measured. Prompt version two/retrieval strategy must be run on the same fixed cases as version one. Record the raw results, exact deliberate change, denominators and metric deltas. Do not fill in estimates or fabricated values.

## 6. SLO, load test, bottleneck and cost

Declare the SLO before load testing: **p95 <= 30 seconds from submission through final completed/failed status at concurrency 5**. This is a proposed interactive analyst workflow target; it is not a measured result. Use Locust against the local Compose stack with the deterministic stub enabled, and record concurrency 1/5/10/20, RPS, p50, p95, failure rate, worker count and whether the SLO was met. Compare one worker with three workers. The bottleneck and scaling effect are **pending measurement**.

No LLM provider is currently called, so provider token cost is not applicable. Do not claim total monetary cost without measuring it. Once a provider is added, track prompt/completion tokens and calculate cost per 100 runs.

## 7. Reliability, security and what did not work

The API uses request validation, correlation IDs, health and metrics endpoints, and a fail-closed classification route. The deterministic guardrail is a narrow rule-based demonstration and is not a general-purpose toxicity classifier. Malformed-request quarantine, distributed rate limiting, complete OpenTelemetry traces, vector indexing, provider circuit breaker, token/cost accounting, and automatically scored live quality metrics remain items to verify or implement.

A local dependency installation exposed incompatible versions already present in the user's Anaconda environment. `python -m pytest -q` subsequently passed **4 tests** before the additional guardrail tests were added, and `docker compose config --quiet` returned no errors. These checks are not an end-to-end or load-test result. Re-run tests after pulling the final commit.

## 8. Submission evidence checklist

- [ ] Clean-clone `docker compose up --build -d` and healthy API/worker/Redis/monitoring
- [ ] Valid request and citations resolving to retrieved source text
- [ ] Malformed request rejected before a run starts, with quarantine evidence
- [ ] Unsupported case escalated, and unsupported answer caught by verification
- [ ] Prompt-injection attempt rejected/flagged
- [ ] Provider-down/circuit-breaker demo (only after a provider adapter exists)
- [ ] Vacuum-flask case verified against official source heading, GRI and notes
- [ ] 20-case evaluation output and two prompt variants with all four measured metrics
- [ ] Locust report, SLO decision, concurrency failure point and one-vs-three-worker comparison
- [ ] Genuine incident-log entry, screenshots and demo recording
