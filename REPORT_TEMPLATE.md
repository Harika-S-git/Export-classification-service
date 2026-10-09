# Mini Project 07 — Export Classification Check Service

## 1. Problem and scope
Describe the trade-compliance problem, supported Chapters 73 and 96, and explicit exclusions: no declaration filing, duty calculation or shipping documentation.

## 2. Architecture and deployment boundaries
Insert the repository architecture diagram. Explain API/queue/worker/Redis/monitoring separation, scaling, and failure isolation.

## 3. Agent topology, tools and loop limits
Describe Research, Classification and Verification hand-offs; corpus search, clause lookup and request-field tools; step/time/tool limits; fail-closed policy.

## 4. Data contract and corpus
List schema and cross-field checks. Document official CBIC/DGFT source title, version/date, download URL, extraction/OCR, chunking, embedding and index freshness.

## 5. Difficult case
Show exact official passages for “Stainless steel vacuum flask with a moulded plastic outer body”; explain GRI in numerical order, named-article heading, applicable notes, verification, citations and final human escalation/confirmed proposal.

## 6. Evaluation and prompt comparison
Report the 20+ scenario results. Compare prompt versions on the same cases. Give groundedness, context relevance, faithfulness and hallucination rate before/after one deliberate change, with definitions and calculation method.

## 7. SLO, load test and scaling
State the SLO before measurement. Report end-to-end RPS, p50/p95, error rate, concurrency where SLO fails, bottleneck, and one-worker vs three-worker measurements using fixed-delay stub.

## 8. Observability, reliability and cost
Show one reconstructed run, correlation ID, tool calls, queries, retrieved passages, prompt version, per-step latency, retry/circuit-breaker state, tokens/cost if an LLM is used, and Grafana charts. Report cost per 100 runs or explain why it is zero/not applicable for the no-LLM baseline.

## 9. What did not work and engineering decisions
Include actual incidents, alternatives rejected, limitations and lessons.

## 10. Conclusion
Summarize verified capability and remaining human-review boundary.
