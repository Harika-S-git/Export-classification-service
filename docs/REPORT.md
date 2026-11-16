# Export Classification Check Service — Final Report
Course UE24AM342AA5 · Mini Project 07 · Logistics and Trade Compliance
Prepared 13 November 2026. Team names and SRNs: fill docs/TEAM.md.

## Problem and scope
Export misclassification can delay consignments and attract penalties. The system
accepts a product description and returns a proposed tariff classification,
retrieved evidence, snapshot export policy and one of three routes. A licensed
customs broker decides. It never files a declaration, calculates duty, or creates
shipping documents. Scope is Chapters 73 and 96, with explicitly bounded article
recognition; unsupported products escalate or request clarification.

The reference stainless-steel vacuum flask with a moulded plastic outer body is
proposed under heading 9617 using GRI 1. The heading names the article; Section XV
Note 1(m) excludes articles of Chapter 96 from material-based classification.
Multiple materials alone do not justify jumping to GRI 3. Missing capacity causes
clarification for the eight-digit split; 0.75 L belongs to 96170011, while 0.751 L
and 1 L belong to 96170012 in the frozen source snapshot. Glass inners are excluded.

## Corpus and confirmation
Bundled CBIC-authored 2022 tariff came from a labelled mirror after CBIC HTTP 503
failures. DGFT Notification_ITCHS.pdf and general notes came directly from DGFT.
WCO 2022 GRI substitutes for the unavailable CBIC-hosted rules. SHA256, original
versions, physical one-based page anchors and retrieval date are recorded in
corpus/sources.json. These are not asserted to be current law. Faculty confirmation
and amendment review remain pending; default POLICY_SNAPSHOT_CONFIRMED=false
routes otherwise clear cases to specialist policy review. Evaluation explicitly
acknowledged the frozen snapshot; no real shipment clearance is claimed.

## Agent design and boundaries
FastAPI validates before enqueue, Redis/RQ persists asynchronous jobs, and separate
classifier worker containers execute a LangGraph reasoning agent. A second
LangGraph agent runs in its own verifier service/process with an explicit JSON
handoff and independent canonical clause lookup. The provider stub is another
container; a compatible live provider is selected entirely by runtime configuration.
The diagram in docs/architecture.svg and ARCHITECTURE.md marks these boundaries.

The classifier chooses request_fields, corpus_search and clause_lookup tools from
its state. It retrieves material candidates, reads notes, derives an article query
from the modifying provisions, looks up rules/notes/policy and asks the provider to
propose. The verifier checks citation identity, exact text/hash, article fit,
applicable notes, rule and policy. Unsupported drafts trigger one alternate exact
lookup and another verification; failure returns no classification. The planner
is deliberately deterministic, not unrestricted LLM tool selection. This is a
material limitation against the strictest interpretation of A1.

Budgets: 20 decision steps, 14 tool calls, 45-second RQ hard execution timeout;
5-second local-tool/provider HTTP deadline; 15-second verifier handoff. Provider
calls retry at most twice with 150/300 ms exponential backoff. Redis shares a
three-failure circuit breaker across replicas, with 15-second cooldown and a
single half-open probe. Provider/verifier failures fall back to specialist review.
A dead worker is exposed as failed/escalated through polling; unfinished runs are
never promoted into verified answers.

## Design choices and rejected alternatives
A notebook and synchronous long-running API were rejected because this is a
service with durable asynchronous execution. Polling was chosen over callbacks
to avoid callback reachability and SSRF concerns. A single embedding search was
rejected because material similarity misses the article-naming provision. Two
prompts inside one process were rejected as insufficient agent separation.
Local hash word/trigram embeddings (768 dimensions), LangChain and FAISS give a
small, free, reproducible baseline without weight downloads. They sacrifice
semantic synonym recall; a sentence transformer is future work. Heading/note
clauses retain their legal context; background chunks are 4,500 characters.
Embedding caches are keyed by text hash plus algorithm version, and an atomic
manifest publishes immutable index generations. Repeated indexing returned an
identical manifest. Redis AOF is simple and persistent but is not high availability;
its every-second fsync can lose about a second on host failure.

## Fixed evaluation and deliberate change
The fixed set has 28 scenarios with expected headings, routes and supporting
passage IDs, including the reference, capacity boundaries, ordinary articles,
exclusions, out-of-scope goods and an unresolved composite. CLI: python -m
tools.evaluate. The deliberate change was material-first v1 to article-first v2,
with versioned prompt artifacts and the same corpus, scenarios and verifier.
This is a prompt/planner ablation under the deterministic stub, not an isolated
live-LLM prompt comparison. No credentialed real-provider results are invented.

| Metric | v1 | v2 | Absolute change |
|---|---|---|---|
| Accuracy | 0.8214 | 1.0000 | +0.1786 |
| Groundedness | 1.0000 | 1.0000 | +0.0000 |
| Context Relevance | 0.3201 | 0.3201 | +0.0000 |
| Faithfulness | 1.0000 | 1.0000 | +0.0000 |
| Hallucination Rate | 0.0000 | 0.0000 | +0.0000 |

Exact expected heading-and-route accuracy improved from 23/28 to 28/28, an
increase of 17.86 percentage points. The five
baseline flask failures were rejected on both verification attempts (10 rejected
drafts), rather than returned as wrong classifications. All emitted final claims
remained supported; that is why groundedness/faithfulness/hallucination did not
improve further. Perfect final evidence proxies do not prove legal correctness.

Groundedness is supported final heading/rule/policy claims divided by emitted
claims, requiring both a returned citation and matching retrieved passage ID.
No emitted claims score 1 as safe abstention and are flagged separately.
Context relevance is gold-support IDs plus POLICY-GENERAL intersected with distinct
retrieved IDs, divided by distinct retrieved IDs. Exact-ID matching is conservative.
Faithfulness uses the same bounded claim consistency check as groundedness here,
so it is not an independent semantic judge. Hallucination is unsupported final
claims divided by emitted claims, zero for no claims. These explicit deterministic
proxies are the evaluator equivalent; no TruLens library execution is claimed.

## Reliability, guardrails and observability validation
31 unit and regression tests passed inside a container. Integration evidence confirms malformed,
injected and toxic inputs produce 422 quarantine records without increasing the
run count; all three routes, verification retry, verifier outage, provider outage,
breaker-open fallback, feedback persistence and rate-limit 429 were exercised.
A Chromium browser test submitted the flask, displayed seven citations, saved
feedback and found no JavaScript errors. Screenshot and JSON evidence are in
results/. NFKC and regex screening cover free-text inputs and outputs; finite
outputs and limited tools constrain model authority, but multilingual/adversarial
coverage is a known weakness.

Structured audit records preserve each query, retrieved passage, prompt version,
latency, token/cost entry and verification. Correlation propagates through RQ and
HTTP; actual Jaeger traces include API, classifier, verifier and stub spans.
Prometheus endpoints and a Grafana dashboard are provisioned for completion p50/p95,
throughput, success/error rate, availability, per-agent steps/tools/retries,
uptime and container resources. Full simultaneous monitoring-stack startup was
not validated: this cloud root filesystem is 7.9 GB with Docker VFS and exhausted
space while extracting Grafana. Core services, three worker replicas and Jaeger
were validated after image flattening/source mounts. Portable Compose/Dockerfile
are included; a full clean-clone rehearsal on adequate storage remains necessary.

## Predeclared SLO and measured scaling
Before load testing, docs/SLO.md declared p95 complete-run latency at most 30 s
for 10 concurrent analysts with one worker. The complete interval begins before
submission and ends when polling observes a final result, including queue wait.
The workload uses a 750 ms delayed stub per provider call (two ordinary calls),
unique nonces and disabled whole-run caching. Each test admits traffic for 40 s
then drains outstanding runs; CSV throughput includes its measured interval.
The machine had a 2-core CPU quota and 8 GiB memory. To save VFS disk, Locust ran
as a separate process inside the API container, sharing its CPU budget. The
reproduction profile uses a separate Locust container.

| Workers | Clients | Completed | Failures | Runs/s | p50 s | p95 s | SLO met |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 18 | 0 | 0.450 | 2.0 | 2.3 | Yes |
| 1 | 10 | 28 | 0 | 0.490 | 20.0 | 20.0 | Yes |
| 1 | 30 | 45 | 0 | 0.453 | 51.0 | 65.0 | No |
| 3 | 10 | 60 | 0 | 1.303 | 7.2 | 8.7 | Yes |
| 3 | 30 | 72 | 0 | 1.172 | 25.0 | 28.0 | Yes |
| 3 | 60 | 102 | 0 | 1.206 | 43.0 | 51.0 | No |

With one worker, the first tested failure was 30 concurrent clients;
10 passed, so the crossing lies above 10 and no higher than 30 for this
workload, not at a precisely measured continuous boundary. With three workers,
first tested failure: 60.
The initial three-worker/10-client startup run had one verifier ConnectError while the verifier was restarting (1/45 failed observations). It missed the 99% availability objective and is retained under results/load/startup. The primary table uses the repeated steady-state run after readiness; the startup failure is not discarded. Locust observed one fewer completed run per cell than the server profile because a final accepted request outlived its stopped polling client; profile counts and server-complete latency are retained to expose this censoring limitation.

The baseline bottleneck is the serial classifier queue: each worker executes one
run at a time, and queue waiting grows while execution remains much shorter.
Detailed queue/execution percentiles are in results/load-profile.json. Three
workers increase parallelism; the measured improvement is bounded by two shared
CPU cores, JSON/audit overhead and polling. Those secondary costs were not
independently isolated, so no sole secondary bottleneck is asserted.

## Cache, cost and feedback
Twelve uncached samples had p50 1.9592 s and p95
2.5769 s. Eleven warm-cache hits had p50 0.0310 s
and p95 0.0459 s, a 98.22% p95 reduction in this small sample.
The cold fill is retained separately. Whole-run cache keys include canonical
product, prompt version, corpus generation, provider mode and policy-confirmation
state; unverified and fault-injected runs are never cached.

Actual stub cost is $0 per run and $0 per 100 runs, both before and after caching.
There is no paid-provider dollar-saving claim. Mean uncached prompt-token estimate
was 31531; warm hits made no model calls. Full retrieved
context and legal-note text dominate estimated token use; per-agent model-step
records identify classifier/verifier contributions. In real mode usage and runtime
USD-per-million rates are recorded at each call. Missing provider usage and free-tier
rate limits remain limitations. Rate limiting is per demo client label; real cost
control needs an authenticated gateway. Feedback is persisted and aggregated, and
a deterministic sample of live runs is charted over time as evidence quality.

## What did not work and remaining work
Genuine development failures included PDF-layout assumptions, container TLS trust,
VFS disk exhaustion, runtime file permissions, lowercase proxy bypass precedence,
and omitted null escalation fields. The incident log records symptoms and fixes.
The runbook covers provider failure and queue/worker failure. The full dashboard,
current CBIC corpus confirmation, robust multilingual guardrails and real-LLM
prompt/evaluation quality remain unproven. See the explicit F/A/L/D matrix instead
of assuming all guide requirements are fully met. The course guide itself allows
prioritisation; this project prioritises a working, auditable, fail-closed path.

## Submission and reproduction
README.md gives Docker-only startup, configuration, API usage, evaluation, load,
fault demonstration, indexing and recovery. Included deliverables are source,
source PDFs, scoped extracts, contracts, fixed tests/results, dashboards, report,
presentation, project plan and demo/viva notes. Fill actual names/SRNs, create and
push the GitHub repository, obtain evaluator corpus confirmation, and rehearse the
live demonstration. Those external actions have not been falsely marked complete.
