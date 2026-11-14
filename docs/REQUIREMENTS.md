# Guide-to-evidence matrix

Status: implemented = code and specific validation exist within the bounded scope;
partial = a material requirement or validation remains limited. These labels do
not assert production legal accuracy or faculty acceptance.

| ID | Status | Implementation / evidence |
|---|---|---|
| F1 | Implemented | FastAPI REST, OpenAPI and JSON schemas; web/browser check |
| F2 | Implemented | Strict types, ranges/categories/cross-fields; integration shows quarantine and unchanged run count |
| F3 | Partial | Explicit article/material recogniser; unknown synonyms need clarification |
| F4 | Implemented within scope | Agent searches material, reads notes, derives article query; exact clause lookup; bounded article coverage |
| F5 | Partial | Canonical evidence, GRI 1 and applicability checks; no general expert legal reasoning |
| F6 | Implemented | All three routes; results/integration-evidence.json |
| F7 | Implemented within scope | Out-of-scope/excluded/unresolved composite escalations; no invented tariff fallback |
| F8 | Implemented core | Health, metrics, structured audit/logs; full dashboard runtime not verified |
| A1 | Partial | LangGraph and three tools with dynamic note-derived query/retry; deterministic planner rather than autonomous LLM tool selection |
| A2 | Implemented | Separate classifier worker and verifier service/graph; explicit handoff and failures |
| A3 | Implemented within scope | Every citation matches retrieved canonical text/hash; unsupported draft triggers second lookup then escalation |
| A4 | Implemented | Redis/RQ between 202 submission and execution; documented polling |
| A5 | Implemented core | 5s tool/provider deadline, bounded exponential retry, shared breaker, fail-closed fallback; outage tests |
| A6 | Partial | Per-agent audit/metrics and provisioned dashboard; full Grafana/resource display unverified here |
| A7 | Measured | Worker scale tests and Locust CSVs; see REPORT.md for actual results and limits |
| A8 | Implemented | Web form/polling/citations/route/feedback; browser screenshot and zero console errors |
| L1 | Implemented | LangChain retriever + local hash embeddings + FAISS; incremental embedding cache; semantic recall tradeoff documented |
| L2 | Partial | Versioned prompts and matched-set v1/v2 ablation; no credentialed live-LLM prompt comparison |
| L3 | Partial | 28 gold scenarios, CLI, four transparent deterministic proxies before/after; no independent semantic or legal judge |
| L4 | Partial | Every model-reaching free text guarded; finite outputs, injection/toxicity screening; regex baseline has known gaps |
| L5 | Implemented in stub scope | Per-step/run usage and cost; stub token estimates labelled and actual cost $0; live adapter untested |
| L6 | Implemented | Persisted feedback/aggregates; automatic sampled evidence metrics; web quality chart |
| D1 | Implemented | Schema artifacts, strict validation before enqueue, quarantine with field errors/hash |
| D2 | Implemented for bundled PDFs | Idempotent parser/chunker/embed/index CLI; manifest freshness/source versions/count/throughput; no bundled OCR |
| D3 | Partial | 13 declared services including optional tools, health/dependencies; core stack validated; full clean simultaneous monitoring startup blocked by cloud disk |
| D4 | Implemented with explicit interpretation | External provider URL/model/secret runtime-only; .env.example has placeholders/demo deployment addresses. Internal Compose endpoints and source citation URLs necessarily remain in deployment/provenance artifacts |
| D5 | Partial | Reconstructible audit and actual four-service Jaeger spans; Prometheus/Grafana/cAdvisor configs included; full resource dashboard not runtime-validated |
| D6 | Measured | Predeclared 30s p95, complete-run Locust metrics, delayed stub, tested concurrency threshold and scaling; short runs on 2 CPUs |
| D7 | Implemented demo scope | Cache p95/token measurements; per-client rate limit and 429 evidence; identity header requires authenticated gateway in production |
| D8 | Implemented | Two failure runbooks; genuine parser, TLS, storage, permissions, trace and API incidents |

Deliverables included: corpus confirmation packet and project plan, complete source
folder, final report/PDF, architecture, demo/viva guide, presentation PDF, source
snapshots, evaluation set/results, load CSVs, cache measurements, runbook, incident
log, environment template and CI. Real names/SRNs, faculty corpus confirmation,
GitHub push, live presentation and viva remain student actions.
