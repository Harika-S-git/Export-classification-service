# Corpus confirmation and project plan

The reference case is a complete stainless steel vacuum flask with a moulded
plastic outer body. Proposed heading **9617**, under **GRI 1**, not 7323 merely
because of the steel. CBIC 2022 tariff physical page 825 supplies heading 9617.
Section XV notes (physical page 573 onward) exclude articles of Chapter 96 from
base-metal classification. Chapter 96 notes are physical page 819; none excludes
a complete ordinary vacuum flask. WCO 2022 GRI page 1 supplies the rule.
DGFT Notification_ITCHS.pdf's P9617 clause supplies flask capacity splits and
snapshot export policy. The clause IDs, exact passages, page anchors and SHA256s
are in corpus/clauses.json; sources and versions are in corpus/sources.json.

Test values: description exactly as above; capacity absent -> propose 9617,
seek-product-clarification for eight-digit item. At 0.5 L and exactly 0.75 L ->
96170011; at 0.751 L and 1 L -> 96170012. Parts are not silently treated as a
complete flask; glass inners escalate outside the chapters. Default current-policy
routing still requires specialist confirmation of the frozen corpus.

Confirmation checklist for the evaluator: confirm the mirrored CBIC-authored
2022 text is acceptable for this academic snapshot; replace it with a currently
confirmed CBIC edition when accessible; confirm WCO GRI substitution or supply
CBIC GRI; confirm DGFT snapshot version and subsequent amendments; agree the
reference at heading level with missing capacity. No faculty confirmation is
claimed. The service does not use these documents as instructions to act or file.

Plan (relative weeks; no invented submission dates):
1. Week 1: corpus confirmation, data contracts, architecture and SLO declaration.
2. Week 2: functioning API -> Redis -> classifier -> verifier -> web result.
3. Week 3: note-derived search, verification retry, guardrails, failures and traces.
4. Week 4: fixed evaluations, prompt/planner ablation, load/scaling/cache evidence.
5. Week 5: report, clean-clone rehearsal, demo and viva. Final repository/report
   are due one week before the actual presentation date set by the course.

Suggested 2–3 student split: ingestion/corpus and evaluation; agents/API and
verification; containers/observability/load/report. Fill real names and contributions
in docs/TEAM.md. Do not claim AI-generated work as independently performed student
work where the course requires disclosure.
