# Genuine development incidents

2026-11-13 UTC — Corpus ingestion stopped with `StopIteration`, then
`Heading not found 7307`. Confirmation: CBIC's extracted section title is uppercase
and heading 7307 shares its line with heading text; the parser expected mixed
case and a newline. Impact: no usable index; no agent could start. Recovery:
normalised section matching and anchored heading code plus uppercase heading
text; added immutable-corpus tests and retained parser checks that fail closed.

2026-11-13 UTC — First Docker build failed TLS verification while pip contacted
PyPI. The host trust store included the managed proxy CA, but the image did not.
Recovery: mounted the combined public CA bundle as a BuildKit secret for the pip
step. TLS verification stayed enabled. Added an optional compose.cloud.yaml;
ordinary Docker Desktop requires no session-specific certificate.

2026-11-13 UTC — CBIC-hosted tariff download attempts returned HTTP 503; guessed
DGFT schedule paths returned 403. Confirmed successful DGFT published
Notification_ITCHS.pdf and general-notes downloads. Used a labelled mirror of the
CBIC-authored 2022 tariff and WCO 2022 GRI. Current corpus confirmation remains
explicitly pending; default routing requires specialist policy review.

2026-11-13 UTC — Multi-service startup exhausted the 7.9 GB root filesystem.
Docker reported `no space left on device`; its storage driver was VFS, so image
layers and every container's root filesystem were copied. Recovery: removed only
this task's unused monitoring images/build cache, flattened the test image and
ran the core services with source mounts. Monitoring configuration is included,
but simultaneous full-stack clean startup is not represented as verified here.

2026-11-13 UTC — Containers initially could not import app/tools. Files created
in the workspace had mode 0600 and the runtime used UID 10001. Recovery: ensure
read/execute permissions on copied application files in the Dockerfile and invoke
Uvicorn through `python -m uvicorn`. Core readiness checks then passed.

2026-11-13 UTC — OTLP requests returned 403 even with NO_PROXY set. Inspection
showed Docker's inherited lowercase no_proxy omitted internal services and took
precedence. Recovery: declare both cases for internal services. Jaeger subsequently
listed submission-api, classifier-worker, verification-agent and provider-stub;
exported trace JSON contains spans from all four boundaries.

2026-11-13 UTC — Integration assertion found escalation heading missing rather
than null because FastAPI response_model_exclude_none was enabled. Recovery:
retain null fields in the published response; all integration checks then passed.

2026-11-13 UTC — First 3-worker/10-client load run began while verifier was
restarting. One run escalated with `Verification agent unavailable: ConnectError`
(run cd4d844d-0086-41b5-af53-d7bcf6a138dc), and Locust recorded 1 failure in 45
complete-run observations. This was a real availability miss. Recovery: wait for
service readiness before steady-state testing; retain the startup CSVs under
results/load/startup and repeat the same 10-client cell. Reproduction scripts use
Compose --wait. No unsupported answer was issued during the interruption.
