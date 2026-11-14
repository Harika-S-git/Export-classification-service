# Export Classification Check Service

**Download:** [Final project ZIP](https://github.com/Harika-S-git/new_proj/raw/refs/heads/main/dist/Export_Classification_Check_Final_Project.zip) · [Project report](https://github.com/Harika-S-git/new_proj/blob/main/docs/REPORT.pdf) · [Presentation](https://github.com/Harika-S-git/new_proj/blob/main/docs/PRESENTATION.pdf)

UE24AM342AA5 · Mini Project 07 · Chapters 73 and 96.
A containerised FastAPI service with queued LangGraph classification and an
independently deployed verification agent, local LangChain/FAISS retrieval,
web client, feedback, audit, tracing, dashboards and reproducible evaluation.

**Start here:** the default mode uses a delayed deterministic model stub. It is
free, needs no API key and demonstrates the entire system. A real provider can
be injected by configuration. The bundled tariff is historical; the default
routing requires specialist policy confirmation before a clear-for-filing route.
See `docs/LIMITATIONS.md` and `docs/REQUIREMENTS.md` for exact coverage and gaps.

## Quick start — Docker only

Prerequisites: Docker Engine/Desktop with Compose v2, internet for image/package
pulls, at least 8 GB free disk (more with Docker's VFS storage driver), and ports
8000, 3000, 9090, 16686 available. All service processes run in containers.

```bash
cp .env.example .env
docker compose up --build -d
```

Windows PowerShell: `Copy-Item .env.example .env`, then the same Compose command.
The one-shot indexer builds FAISS from bundled parsed, source-cited clauses. It
needs no network, credentials or embedding-model download at startup. Wait until
`docker compose ps` shows API healthy (first image build can take several minutes).

- Web client: http://localhost:8000
- Interactive REST documentation: http://localhost:8000/docs
- Grafana: http://localhost:3000 (credentials in your .env)
- Prometheus: http://localhost:9090
- Jaeger: http://localhost:16686

Submit the prefilled reference description. Heading 9617 should be proposed,
with GRI 1, applicable notes and policy citations. With no capacity, the route is
seek-product-clarification. Supply 1 L for item 96170012; the default policy
confirmation safeguard routes that result to specialist review. For an academic
**frozen-snapshot demonstration only**, set POLICY_SNAPSHOT_CONFIRMED=true in .env
and recreate app containers; this acknowledges the snapshot, not current law.

```bash
curl -s http://localhost:8000/v1/runs -H 'Content-Type: application/json' \
  -d '{"product":{"description":"Stainless steel vacuum flask with a moulded plastic outer body.","capacity_l":1}}'
# Poll returned status_url until completed or escalated:
curl -s http://localhost:8000/v1/runs/REPLACE_WITH_RUN_ID
curl -s http://localhost:8000/v1/runs/REPLACE_WITH_RUN_ID/trace
```

## Evaluation, failures, and load

```bash
# Same 28 scenarios against v1/v2. For expected clear routes, explicitly acknowledge
# the frozen snapshot in .env before this academic evaluation.
docker compose --profile tools run --rm toolbox python -m tools.evaluate
# Development faults are off by default. This script temporarily enables them:
bash scripts/demo.sh
# The SLO was declared in docs/SLO.md before measurements.
bash scripts/load_matrix.sh
# Scaling without host port collisions:
docker compose up -d --scale classifier-worker=3
```

Results are written to `results/`. The checked-in reports distinguish actual
measurements from limitations. To repeat unit checks inside Docker, build the
test image: `docker build --target tests -t export-check-tests .`, then
`docker run --rm export-check-tests`. Do not expect unit tests to need Redis or a
paid provider. An optional managed-cloud CA override is in compose.cloud.yaml;
set BUILD_CA_FILE to the approved combined CA bundle and add
`-f compose.yaml -f compose.cloud.yaml` to the build. Never disable TLS checks.

## Refresh the corpus

`corpus/raw/` contains the downloaded source snapshots; `corpus/sources.json`
records URLs, versions, hashes and known provenance limitations. The CBIC-authored
2022 document came from a labelled mirror; GRI came from WCO. Confirm these with
the evaluator before treating Evaluation 1 as complete. No live legal freshness
is claimed. Full original PDFs are retained for reproducibility; only chapters
73/96, applicable notes and GRI are indexed. Scoped extracts are included.

```bash
# Run raw PDF parsing/chunking/embedding/indexing when source files change:
docker compose run --rm --user 0 -v "${PWD}/corpus:/app/corpus" indexer sh -c 'python -m tools.ingest && chown -R 10001:10001 /data'
# Re-embed without re-parsing every document:
docker compose run --rm indexer python -m tools.index --reembed
```

The ingest parser is designed for the bundled layouts. Replacement editions
need source/page review; parser checks fail closed if required headings disappear.
There is no OCR engine bundled: scanned PDFs must be converted to text before
this parser is used. Runtime workers read published immutable generations only.

## Optional real model

Edit .env only: PROVIDER_MODE=compatible, PROVIDER_URL to the provider's API base
(the code appends /chat/completions), PROVIDER_MODEL to an available model,
PROVIDER_API_KEY to your key, and input/output token prices in USD per million.
Recreate app services. No credentials or provider-specific model IDs are committed.
Tokens are taken from provider usage; absent usage is explicitly a limitation.
Stub tokens are labelled estimates and actual stub cost is zero. Set provider
account spend limits separately. Reported stub performance does not measure real
LLM legal reasoning or provider latency. Do not submit secrets as product data.

## Repository map and deliverables

- `app/`: contracts, ingestion API, queue, agents, verification, provider and telemetry.
- `corpus/`: raw PDFs, scoped extracts, exact clauses and provenance.
- `prompts/`: versioned v1 and v2 artifacts; prompt version recorded per model step.
- `eval/`: fixed scenarios, expected routes/passages, Locust workload.
- `tests/`: validation, citation integrity and verification rejection checks.
- `observability/`: Prometheus, Grafana provisioning and dashboard.
- `docs/REPORT.md` / `docs/REPORT.pdf`: final report, architecture and measured results.
- `docs/EVALUATION_1.md`: corpus confirmation packet and project plan.
- `docs/DEMO_AND_VIVA.md`: ten-item rehearsal and viva preparation.
- `docs/RUNBOOK.md`, `docs/INCIDENTS.md`: recovery and genuine development failures.
- `docs/REQUIREMENTS.md`: guide-to-implementation evidence matrix.
- `results/`: actual evaluation, performance and demonstration evidence.

Repository: https://github.com/Harika-S-git/new_proj. Fill in actual names/SRNs
in docs/TEAM.md, confirm the corpus with the evaluator and perform the live
presentation/viva. The downloadable ZIP contains the complete source deliverable;
faculty confirmation and live presentation are not claimed as completed.

Stop with `docker compose down`; this preserves data volumes. `down -v` deletes
run history, feedback and indexes. Do not delete volumes unless you intend that.
