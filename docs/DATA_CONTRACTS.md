# External interfaces, contract v1

The machine-readable source of truth is `docs/openapi.json` (also /openapi.json and
/docs at runtime) plus `app/contracts.py`. JSON only; unknown fields are rejected.

POST /v1/runs accepts {product, prompt_version?, cache?, nonce?, fault?}; product
requires description (10–2000 chars). Optional intended_use ≤300 chars, materials
≤8 entries {name, percent}, capacity_l >0 and ≤100, quantity strict integer
1..1,000,000, vacuum_insulated boolean, complete boolean, destination uppercase
2-letter code. Material names enumerate stainless_steel/steel/iron/plastic/glass/
wood/other, percentages (0,100] sum to 100, names unique. Capacity requires a
complete vessel; vacuum flag may not contradict description. Non-finite ranges,
unknown categories and unexpected fields fail before enqueue. Free text is guarded.
Destination is a syntactic code, not a claim that bilateral restrictions are checked.

202 returns run_id, status_url, trace_url. GET status returns queued/running/
completed/escalated plus result when available. `verified` says evidence checks
passed; `proposed_only` is always true. Heading is four digits; tariff_item is
populated only for a complete vacuum flask with explicit capacity. Routes enumerate
clear-for-filing / seek-product-clarification / specialist-classification-review.
Clear-for-filing means this proposed evidence package can go to the licensed broker,
never that a filing occurred. Policy is tied to a frozen snapshot, not live law.
422 returns quarantine_id, field-level detail and agent_started=false. 429 includes
Retry-After. 403 rejects fault controls unless ENABLE_FAULTS=true. 503 is dependency
failure. In demo deployment X-Client-ID selects rate bucket; it is not authentication.

GET /v1/runs/{id}/trace returns all persisted model/tool/retrieval/verifier events.
POST /v1/runs/{id}/feedback accepts {satisfactory: boolean, reason: 3..500 guarded
characters}; terminal run required. 201 confirms persistence. GET /v1/analytics
aggregates feedback and automatic quality samples. GET /v1/corpus publishes index
version, freshness, chunk count, throughput and source provenance.
GET /health is readiness for local dependencies; /metrics emits Prometheus format.
UI is GET /. No callback or upload interface; neither is silently accepted.

Internal contracts: verifier /verify uses VerifyRequest in app/contracts.py;
stub /generate accepts product, candidates, passages, prompt_version, optional fault
and returns answer plus usage. Redis persists versioned JSON with UUID run keys;
RQ job arguments are validated submissions only. Internal ports are not exposed to
host by Compose. The JSON schema artifacts include Submission, Product,
Recommendation, Feedback and VerifyRequest. Health and analytics are operational
responses; their exact OpenAPI shapes are published with the service.
