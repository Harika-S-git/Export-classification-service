# Start here

1. Read README.md for Docker-only setup and demonstration commands.
2. Read docs/REPORT.pdf for measured results and design decisions.
3. Read docs/REQUIREMENTS.md and docs/LIMITATIONS.md for honest requirement coverage.
4. Fill in actual student details in docs/TEAM.md, push to GitHub, and confirm the
   frozen corpus with the evaluator before the live demonstration.

The default delayed stub runs without a model key. A real LLM can be configured in
.env; its quality has not been evaluated in this package. Default policy routing
requires confirmation of the historical tariff/policy snapshot.

Validation included: 26 container unit tests; 28 fixed evaluation scenarios;
Chromium form/citations/feedback checks; failure-path integration; actual Jaeger
traces; Locust complete-run/scaling measurements; cache latency measurements.
