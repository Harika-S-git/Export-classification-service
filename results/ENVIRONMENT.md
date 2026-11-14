Measured 2026-11-13 UTC in a managed Linux container, Python 3.12, Docker 29.9.2,
Compose 2.40.3, Docker storage driver VFS. cgroup CPU budget: 2 cores
(cpu.max 200000/100000); memory limit: 8 GiB; root disk: 7.9 GB.
Production components ran in Docker. To avoid another 335 MB VFS container copy,
Locust 2.47.0 was installed into a temporary directory in the API container and
executed as a separate process there. This shares the API's CPU budget; it is a
measurement limitation, not an external LLM rate limit. Reproduction uses the
separate Locust profile declared in compose.yaml. Core test image was flattened
to fit the cloud disk and source-mounted; original multi-stage Dockerfile and
Compose build remain the portable deliverable.
