# Predeclared service objective
Declared before the first load run: 95% of valid submissions reach a final,
verified result or explicit escalation within **30 seconds**, measured from just
before POST /v1/runs until a polling GET observes a terminal state. Target workload:
10 concurrent clients, one classifier worker, cold whole-run cache, two 750 ms
provider calls per routine request. Availability target: 99% terminal runs within
the 45 second hard execution deadline (queue time excluded from execution limit,
but included in the SLO).

Rationale: this is interactive analyst assistance before a shipment is filed;
a half-minute response fits that workflow. An immediate 202 is not completion.
Load tests deliberately use unique request nonces, bypassing whole-run cache.
The load script increases clients until p95 exceeds 30 seconds; results cannot
be used to revise this target. Provider rate limits are excluded by a delayed stub.
