# Manual Evaluation Protocol and Annotation Guide

## 1. Objective and Scope

This document defines the manual evaluation protocol for the Export Classification Service.
Automated metrics (such as string matching or lexical keyword overlap) can verify software mechanics, but they **cannot** establish legal tariff classification correctness or factual claim entailment.

This protocol distinguishes three fundamental tiers of evaluation:

1. **Preliminary Lexical Relevance (Automated Signal):**
   - Heuristic term overlap between the product description and corpus passages.
   - *Limitation:* Shared words (e.g., "steel", "article") do not imply that the tariff passage applies to the product.
2. **Semantic Entailment and Claim Support (Manual Linguistic Review):**
   - Determining whether the visible cited excerpt directly supports the rationale statement made by the agent.
   - Assesses whether the model hallucinates statements not present in the cited text.
3. **Legal Classification Correctness (Statutory Customs Review):**
   - Evaluates whether the proposed HS classification or routing complies with the General Rules for the Interpretation of the Harmonized System (GRI 1 through 6), Section Notes, Chapter Notes, and official rulings.
   - *Note:* In student/development environments without a licensed customs broker and complete official tariff schedule, the system must fail-closed and escalate to specialist review rather than asserting unverified HS codes.

---

## 2. Annotation Schema

Each scenario in `evals/manual_annotations_template.json` contains the following fields:

### A. Product Description Sufficiency (`product_description_sufficiency`)
Evaluates whether the user's input contains enough physical and functional details to even attempt tariff classification:
- `sufficient`: Description clearly identifies the physical article, its composition, and its function (e.g., "Stainless steel vacuum flask with a moulded plastic outer body").
- `insufficient`: Crucial information is missing, making classification impossible (e.g., "Unspecified manufactured item").
- `ambiguous`: Description provides some clues but omits key distinguishing characteristics (e.g., "Iron cast article with unknown intended use").
- `pending`: Awaiting manual judgment.

### B. Citation Resolution (`citation_resolution`)
Evaluates whether cited passages refer to existing, indexed corpus records:
- `all_resolved`: All cited passage IDs exist in the indexed corpus and contain non-empty text.
- `partially_resolved`: Some cited passage IDs resolve, but others are broken or missing.
- `unresolved`: None of the cited IDs resolve to valid corpus entries.
- `no_citations_needed`: Case was routed directly to clarification without requiring corpus research.
- `pending`: Awaiting manual judgment.

### C. Passage Relevance to Product (`passage_relevance`)
Evaluates whether the retrieved and cited passages relate to the specific product article (not just coincidental material words):
- `relevant`: The passage explicitly addresses the specific article type or its governing heading/notes (e.g., heading 9603 for a broom).
- `partially_relevant`: The passage addresses general material provisions (e.g., Chapter 73 general steel provisions) but fails to address the specific article or heading.
- `irrelevant`: The passage has no meaningful relationship to the product (e.g., rail joints for a kitchen utensil).
- `pending`: Awaiting manual judgment.

### D. Claim Support and Entailment (`claim_support_entailment`)
Evaluates whether the visible excerpt logically entails the factual statements made in the agent's `rationale`:
- `entailed`: Every factual assertion in the rationale is supported by the cited excerpt.
- `partially_supported`: Some assertions are supported, but others are unverified or extrapolated.
- `unsupported`: The rationale claims things contradicted by or entirely absent from the cited excerpt (hallucination).
- `pending`: Awaiting manual judgment.

### E. Classification Support (`classification_support`)
Evaluates whether the evidence genuinely establishes an HS code under statutory classification principles:
- `supported`: Legally sufficient evidence (named heading, applicable GRI, chapter notes) confirms the classification.
- `insufficient_evidence`: Passages provide candidates or context, but essential tariff notes or headings are missing.
- `unsupported`: The classification is contradicted or unsupported by the evidence.
- `pending`: Awaiting manual judgment.

### F. Routing Appropriateness (`routing_appropriateness`)
Evaluates whether the final route chosen by the service was the legally and operationally safe decision:
- `specialist_review_appropriate`: Evidence is incomplete, competing headings exist, or legal ambiguity requires human broker review.
- `clarification_appropriate`: Input was insufficient or ambiguous, so requesting clarification from the exporter was correct.
- `clear_for_filing_appropriate`: Classification was conclusively verified (requires authoritative corpus and legal proof).
- `inappropriate`: The system chose an unsafe route (e.g., guessed a code when evidence was missing, or asked for clarification on a clear description).
- `pending`: Awaiting manual judgment.

---

## 3. Strict Prohibitions on Metrics

To maintain scientific integrity and avoid misleading claims:
1. **Never conflate Route Match with Legal Accuracy:**
   A 100% route match simply means the agent routed scenarios to `specialist-classification-review` or `seek-product-clarification` as expected by the test harness. It does **not** prove that the service knows the legal HS code.
2. **Never report Groundedness, Faithfulness, or Hallucination Rate without Manual Annotations:**
   If annotations are marked `pending`, the reporting script must report them as **PENDING / NOT EVALUATED**. Do not fabricate percentages or substitute lexical overlap metrics.
3. **Lexical overlap is a heuristic filter, not semantic entailment:**
   Matching the word "steel" in a table about steel pipes does not mean the excerpt supports classifying a stainless steel thermos.
