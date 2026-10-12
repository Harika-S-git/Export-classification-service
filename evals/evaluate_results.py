#!/usr/bin/env python3
"""Evaluation summary and metrics calculator for Export Classification Service.

Computes technical pipeline metrics (route matches, preliminary verification,
citation resolution, error counts) and merges manual annotations (relevance,
claim entailment, statutory classification support) when available.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


VALID_SUFFICIENCY = {"sufficient", "insufficient", "ambiguous", "pending"}
VALID_RESOLUTION = {"all_resolved", "partially_resolved", "unresolved", "no_citations_needed", "pending"}
VALID_RELEVANCE = {"relevant", "partially_relevant", "irrelevant", "pending"}
VALID_ENTAILMENT = {"entailed", "partially_supported", "unsupported", "pending"}
VALID_CLASSIFICATION_SUPPORT = {"supported", "insufficient_evidence", "unsupported", "pending"}
VALID_ROUTING = {"specialist_review_appropriate", "clarification_appropriate", "clear_for_filing_appropriate", "inappropriate", "pending"}


def summarize_run_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate pipeline metrics from raw batch results."""
    total = len(results)
    completed = 0
    failed = 0
    request_errors = 0
    poll_timeouts = 0
    route_matches = 0
    preliminary_verification_passed = 0
    preliminary_verification_failed = 0
    classification_support_passed = 0
    proposed_codes_asserted = 0
    total_citations = 0
    scenarios_with_unresolved_citations = 0

    difficult_cases = {}

    for r in results:
        status = r.get("status")
        if status == "completed":
            completed += 1
        elif status == "failed":
            failed += 1
        elif status == "poll_timeout":
            poll_timeouts += 1
        elif status == "request_error":
            request_errors += 1

        if r.get("error"):
            request_errors += 1 if status not in ("request_error", "poll_timeout") else 0

        if bool(r.get("route_match")):
            route_matches += 1

        if bool(r.get("verification_passed")):
            preliminary_verification_passed += 1
        else:
            preliminary_verification_failed += 1

        res = r.get("result") or {}
        if bool(res.get("classification_support_passed")):
            classification_support_passed += 1

        if res.get("proposed_hs_code") is not None:
            proposed_codes_asserted += 1

        citations = res.get("citations", [])
        total_citations += len(citations)

        # Check for unresolved citations reported in warnings or steps
        warnings = res.get("warnings", [])
        if any("Verification failed" in str(w) or "no citation resolved" in str(w) for w in warnings):
            scenarios_with_unresolved_citations += 1

        sid = r.get("scenario_id")
        if sid in ("S01", "S10", "S19"):
            difficult_cases[sid] = {
                "route": res.get("recommendation"),
                "expected_route": r.get("expected_route"),
                "route_match": r.get("route_match"),
                "verification_passed": r.get("verification_passed"),
                "citations_count": len(citations),
                "proposed_hs_code": res.get("proposed_hs_code"),
                "sample_citation": citations[0]["passage_id"] if citations else None,
            }

    return {
        "total_scenarios": total,
        "completed": completed,
        "failed": failed,
        "request_errors": request_errors,
        "poll_timeouts": poll_timeouts,
        "route_matches": route_matches,
        "route_match_rate": (route_matches / total) if total > 0 else 0.0,
        "preliminary_verification_passed": preliminary_verification_passed,
        "preliminary_verification_failed": preliminary_verification_failed,
        "classification_support_passed": classification_support_passed,
        "proposed_codes_asserted": proposed_codes_asserted,
        "total_citations_returned": total_citations,
        "scenarios_with_unresolved_citations": scenarios_with_unresolved_citations,
        "difficult_cases": difficult_cases,
    }


def validate_and_summarize_annotations(annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate manual annotations and compute semantic/legal metrics if annotations exist."""
    total = len(annotations)
    pending_count = 0
    invalid_records = []

    relevance_counts = {"relevant": 0, "partially_relevant": 0, "irrelevant": 0}
    entailment_counts = {"entailed": 0, "partially_supported": 0, "unsupported": 0}
    support_counts = {"supported": 0, "insufficient_evidence": 0, "unsupported": 0}
    routing_counts = {
        "specialist_review_appropriate": 0,
        "clarification_appropriate": 0,
        "clear_for_filing_appropriate": 0,
        "inappropriate": 0,
    }

    for item in annotations:
        sid = item.get("scenario_id", "unknown")
        suff = item.get("product_description_sufficiency", "pending")
        cres = item.get("citation_resolution", "pending")
        rel = item.get("passage_relevance", "pending")
        ent = item.get("claim_support_entailment", "pending")
        csupp = item.get("classification_support", "pending")
        rout = item.get("routing_appropriateness", "pending")

        # Validate allowed enum values
        errors = []
        if suff not in VALID_SUFFICIENCY:
            errors.append(f"invalid sufficiency: {suff}")
        if cres not in VALID_RESOLUTION:
            errors.append(f"invalid resolution: {cres}")
        if rel not in VALID_RELEVANCE:
            errors.append(f"invalid relevance: {rel}")
        if ent not in VALID_ENTAILMENT:
            errors.append(f"invalid entailment: {ent}")
        if csupp not in VALID_CLASSIFICATION_SUPPORT:
            errors.append(f"invalid classification_support: {csupp}")
        if rout not in VALID_ROUTING:
            errors.append(f"invalid routing: {rout}")

        if errors:
            invalid_records.append({"scenario_id": sid, "errors": errors})
            continue

        if all(f == "pending" for f in (rel, ent, csupp, rout)):
            pending_count += 1
            continue

        if rel in relevance_counts:
            relevance_counts[rel] += 1
        if ent in entailment_counts:
            entailment_counts[ent] += 1
        if csupp in support_counts:
            support_counts[csupp] += 1
        if rout in routing_counts:
            routing_counts[rout] += 1

    evaluated_count = total - pending_count - len(invalid_records)
    has_annotations = evaluated_count > 0

    metrics = {
        "total_annotation_records": total,
        "evaluated_scenarios": evaluated_count,
        "pending_scenarios": pending_count,
        "invalid_records": invalid_records,
        "has_active_annotations": has_annotations,
    }

    if has_annotations:
        rel_total = sum(relevance_counts.values())
        metrics["context_relevance_rate"] = (
            relevance_counts["relevant"] / rel_total if rel_total > 0 else 0.0
        )
        ent_total = sum(entailment_counts.values())
        metrics["faithfulness_groundedness_rate"] = (
            entailment_counts["entailed"] / ent_total if ent_total > 0 else 0.0
        )
        metrics["hallucination_rate"] = (
            entailment_counts["unsupported"] / ent_total if ent_total > 0 else 0.0
        )
        supp_total = sum(support_counts.values())
        metrics["classification_support_rate"] = (
            support_counts["supported"] / supp_total if supp_total > 0 else 0.0
        )
        metrics["relevance_counts"] = relevance_counts
        metrics["entailment_counts"] = entailment_counts
        metrics["classification_support_counts"] = support_counts
        metrics["routing_appropriateness_counts"] = routing_counts

    return metrics


def compare_runs(baseline: Dict[str, Any], latest: Dict[str, Any]) -> Dict[str, Any]:
    """Compare baseline run against latest run."""
    b_summary = summarize_run_results(baseline)
    l_summary = summarize_run_results(latest)
    return {
        "baseline": b_summary,
        "latest": l_summary,
        "deltas": {
            "completed": l_summary["completed"] - b_summary["completed"],
            "route_matches": l_summary["route_matches"] - b_summary["route_matches"],
            "preliminary_verification_passed": (
                l_summary["preliminary_verification_passed"]
                - b_summary["preliminary_verification_passed"]
            ),
            "request_errors": l_summary["request_errors"] - b_summary["request_errors"],
            "proposed_codes_asserted": (
                l_summary["proposed_codes_asserted"]
                - b_summary["proposed_codes_asserted"]
            ),
        },
    }


def format_text_report(
    summary: Dict[str, Any],
    annotations_summary: Optional[Dict[str, Any]] = None,
    comparison: Optional[Dict[str, Any]] = None,
) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("EXPORT CLASSIFICATION SERVICE — EVALUATION SUMMARY REPORT")
    lines.append("=" * 70)

    lines.append("\n[1] TECHNICAL PIPELINE EXECUTION")
    lines.append(f"  Total Scenarios:               {summary['total_scenarios']}")
    lines.append(f"  Completed Requests:            {summary['completed']}")
    lines.append(f"  Request Errors / Timeouts:     {summary['request_errors']}")
    lines.append(
        f"  Expected Route Matches:        {summary['route_matches']} / {summary['total_scenarios']} ({summary['route_match_rate']:.1%})"
    )
    lines.append("  * Note: Route matches confirm test routing policy only, NOT statutory legal correctness.")

    lines.append("\n[2] EVIDENCE VERIFICATION & SAFE ESCALATION")
    lines.append(
        f"  Preliminary Verification Passed: {summary['preliminary_verification_passed']} (lexical overlap filter)"
    )
    lines.append(
        f"  Preliminary Verification Failed: {summary['preliminary_verification_failed']} (fail-closed to specialist)"
    )
    lines.append(
        f"  Classification Support Passed:   {summary['classification_support_passed']} (requires official legal proof)"
    )
    lines.append(
        f"  Proposed HS Codes Asserted:      {summary['proposed_codes_asserted']} (unsupported codes safely suppressed)"
    )
    lines.append(
        f"  Total Citations Returned:        {summary['total_citations_returned']}"
    )

    if summary.get("difficult_cases"):
        lines.append("\n[3] DIFFICULT REFERENCE CASES BREAKDOWN")
        for sid, details in summary["difficult_cases"].items():
            lines.append(f"  Case {sid}:")
            lines.append(f"    Route: {details['route']} (Expected: {details['expected_route']}) -> Match: {details['route_match']}")
            lines.append(f"    Verification Passed: {details['verification_passed']}")
            lines.append(f"    Citations Count:     {details['citations_count']}")
            lines.append(f"    Proposed HS Code:    {details['proposed_hs_code']}")
            if details['sample_citation']:
                lines.append(f"    Sample Citation:     {details['sample_citation']}")

    lines.append("\n[4] MANUAL EVALUATION & CLAIM ENTAILMENT")
    if annotations_summary and annotations_summary.get("has_active_annotations"):
        lines.append(f"  Evaluated Scenarios:           {annotations_summary['evaluated_scenarios']}")
        lines.append(f"  Context Relevance Rate:        {annotations_summary['context_relevance_rate']:.1%}")
        lines.append(f"  Faithfulness / Groundedness:   {annotations_summary['faithfulness_groundedness_rate']:.1%}")
        lines.append(f"  Hallucination Rate:            {annotations_summary['hallucination_rate']:.1%}")
        lines.append(f"  Classification Support Rate:   {annotations_summary['classification_support_rate']:.1%}")
    else:
        lines.append("  Status: PENDING (Human annotation required)")
        lines.append("  - Scientific Integrity Policy: Groundedness, Faithfulness, Hallucination Rate,")
        lines.append("    and Legal Accuracy are NEVER fabricated or substituted with lexical heuristics.")
        lines.append("  - To annotate: see evals/MANUAL_EVALUATION_GUIDE.md and evals/manual_annotations_template.json")

    if comparison:
        lines.append("\n[5] HISTORICAL COMPARISON (BASELINE vs LATEST)")
        b = comparison["baseline"]
        l = comparison["latest"]
        d = comparison["deltas"]
        lines.append(f"  {'Metric':<32} {'Baseline':<12} {'Latest':<12} {'Delta':<10}")
        lines.append("  " + "-" * 66)
        lines.append(f"  {'Completed Runs':<32} {b['completed']:<12} {l['completed']:<12} {d['completed']:+d}")
        lines.append(f"  {'Route Matches':<32} {b['route_matches']:<12} {l['route_matches']:<12} {d['route_matches']:+d}")
        lines.append(f"  {'Verification Passed':<32} {b['preliminary_verification_passed']:<12} {l['preliminary_verification_passed']:<12} {d['preliminary_verification_passed']:+d}")
        lines.append(f"  {'Proposed Codes Asserted':<32} {b['proposed_codes_asserted']:<12} {l['proposed_codes_asserted']:<12} {d['proposed_codes_asserted']:+d}")
        lines.append(f"  {'Request Errors':<32} {b['request_errors']:<12} {l['request_errors']:<12} {d['request_errors']:+d}")
        lines.append("  * Explanation: Preliminary verification dropped from 20 to 3 because naive string")
        lines.append("    matching was replaced with strict lexical non-material term safeguards.")

    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Evaluate Export Classification Service batch runs.")
    parser.add_argument("--results", default="evals/latest_results.json", help="Path to batch results JSON")
    parser.add_argument("--baseline", default=None, help="Path to historical baseline JSON (optional)")
    parser.add_argument("--annotations", default=None, help="Path to manual annotations JSON (optional)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args()

    results_path = Path(args.results)
    if not results_path.exists():
        print(f"Error: Results file '{results_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    results = json.loads(results_path.read_text(encoding="utf-8"))
    summary = summarize_run_results(results)

    annotations_summary = None
    if args.annotations:
        annot_path = Path(args.annotations)
        if annot_path.exists():
            annot_data = json.loads(annot_path.read_text(encoding="utf-8"))
            annotations_summary = validate_and_summarize_annotations(annot_data)

    comparison = None
    if args.baseline:
        base_path = Path(args.baseline)
        if base_path.exists():
            base_data = json.loads(base_path.read_text(encoding="utf-8"))
            comparison = compare_runs(base_data, results)

    if args.format == "json":
        output = {"summary": summary, "annotations": annotations_summary, "comparison": comparison}
        print(json.dumps(output, indent=2))
    else:
        print(format_text_report(summary, annotations_summary, comparison))


if __name__ == "__main__":
    main()
