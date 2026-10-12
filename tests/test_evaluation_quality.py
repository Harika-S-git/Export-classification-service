import pytest
from evals import evaluate_results


def test_summarize_run_results_counts_metrics_correctly():
    sample_results = [
        {
            "scenario_id": "S01",
            "expected_route": "specialist-classification-review",
            "actual_route": "specialist-classification-review",
            "status": "completed",
            "route_match": True,
            "verification_passed": False,
            "result": {
                "recommendation": "specialist-classification-review",
                "proposed_hs_code": None,
                "classification_support_passed": False,
                "citations": [{"passage_id": "chap_73.txt#p14"}],
            },
        },
        {
            "scenario_id": "S10",
            "expected_route": "specialist-classification-review",
            "actual_route": "specialist-classification-review",
            "status": "completed",
            "route_match": True,
            "verification_passed": True,
            "result": {
                "recommendation": "specialist-classification-review",
                "proposed_hs_code": None,
                "classification_support_passed": False,
                "citations": [{"passage_id": "chap_96.txt#p1"}],
            },
        },
        {
            "scenario_id": "S14",
            "expected_route": "seek-product-clarification",
            "actual_route": "seek-product-clarification",
            "status": "completed",
            "route_match": True,
            "verification_passed": False,
            "result": {
                "recommendation": "seek-product-clarification",
                "proposed_hs_code": None,
                "classification_support_passed": False,
                "citations": [],
            },
        },
        {
            "scenario_id": "S15",
            "expected_route": "seek-product-clarification",
            "actual_route": None,
            "status": "failed",
            "route_match": False,
            "verification_passed": False,
            "error": "TimeoutError",
            "result": None,
        },
    ]

    summary = evaluate_results.summarize_run_results(sample_results)

    assert summary["total_scenarios"] == 4
    assert summary["completed"] == 3
    assert summary["failed"] == 1
    assert summary["route_matches"] == 3
    assert summary["route_match_rate"] == 0.75
    assert summary["preliminary_verification_passed"] == 1
    assert summary["preliminary_verification_failed"] == 3
    assert summary["classification_support_passed"] == 0
    assert summary["proposed_codes_asserted"] == 0
    assert summary["total_citations_returned"] == 2
    assert "S01" in summary["difficult_cases"]
    assert "S10" in summary["difficult_cases"]


def test_summarize_run_handles_empty_or_malformed_records():
    empty_summary = evaluate_results.summarize_run_results([])
    assert empty_summary["total_scenarios"] == 0
    assert empty_summary["route_match_rate"] == 0.0

    malformed = [
        {"scenario_id": "S99"},  # missing most keys
        {"scenario_id": "S100", "status": "poll_timeout", "error": "timeout"},
    ]
    summary = evaluate_results.summarize_run_results(malformed)
    assert summary["total_scenarios"] == 2
    assert summary["completed"] == 0
    assert summary["poll_timeouts"] == 1
    assert summary["route_matches"] == 0


def test_annotations_summary_flags_pending_annotations_without_fabrication():
    template_data = [
        {
            "scenario_id": "S01",
            "product_description_sufficiency": "pending",
            "citation_resolution": "pending",
            "passage_relevance": "pending",
            "claim_support_entailment": "pending",
            "classification_support": "pending",
            "routing_appropriateness": "pending",
        }
    ]

    annot_summary = evaluate_results.validate_and_summarize_annotations(template_data)
    assert annot_summary["has_active_annotations"] is False
    assert annot_summary["pending_scenarios"] == 1
    assert annot_summary["evaluated_scenarios"] == 0
    assert "faithfulness_groundedness_rate" not in annot_summary
    assert "hallucination_rate" not in annot_summary


def test_annotations_summary_rejects_invalid_enum_values():
    invalid_data = [
        {
            "scenario_id": "S01",
            "product_description_sufficiency": "super_clear",  # invalid
            "citation_resolution": "pending",
            "passage_relevance": "pending",
            "claim_support_entailment": "pending",
            "classification_support": "pending",
            "routing_appropriateness": "pending",
        }
    ]
    annot_summary = evaluate_results.validate_and_summarize_annotations(invalid_data)
    assert len(annot_summary["invalid_records"]) == 1
    assert "invalid sufficiency: super_clear" in annot_summary["invalid_records"][0]["errors"]


def test_annotations_summary_calculates_rates_when_labels_present():
    annot_data = [
        {
            "scenario_id": "S01",
            "product_description_sufficiency": "sufficient",
            "citation_resolution": "all_resolved",
            "passage_relevance": "partially_relevant",
            "claim_support_entailment": "entailed",
            "classification_support": "insufficient_evidence",
            "routing_appropriateness": "specialist_review_appropriate",
        },
        {
            "scenario_id": "S10",
            "product_description_sufficiency": "sufficient",
            "citation_resolution": "all_resolved",
            "passage_relevance": "relevant",
            "claim_support_entailment": "entailed",
            "classification_support": "supported",
            "routing_appropriateness": "specialist_review_appropriate",
        },
        {
            "scenario_id": "S11",
            "product_description_sufficiency": "sufficient",
            "citation_resolution": "all_resolved",
            "passage_relevance": "irrelevant",
            "claim_support_entailment": "unsupported",
            "classification_support": "unsupported",
            "routing_appropriateness": "inappropriate",
        },
    ]

    annot_summary = evaluate_results.validate_and_summarize_annotations(annot_data)
    assert annot_summary["has_active_annotations"] is True
    assert annot_summary["evaluated_scenarios"] == 3
    # Context relevance: 1 relevant out of 3 = 33.3%
    assert round(annot_summary["context_relevance_rate"], 3) == 0.333
    # Faithfulness / Groundedness: 2 entailed out of 3 = 66.7%
    assert round(annot_summary["faithfulness_groundedness_rate"], 3) == 0.667
    # Hallucination rate: 1 unsupported out of 3 = 33.3%
    assert round(annot_summary["hallucination_rate"], 3) == 0.333
    # Classification support: 1 supported out of 3 = 33.3%
    assert round(annot_summary["classification_support_rate"], 3) == 0.333


def test_compare_runs_calculates_deltas_correctly():
    baseline = [
        {"scenario_id": "S01", "status": "completed", "route_match": True, "verification_passed": True, "result": {"proposed_hs_code": None}},
        {"scenario_id": "S02", "status": "completed", "route_match": True, "verification_passed": True, "result": {"proposed_hs_code": None}},
    ]
    latest = [
        {"scenario_id": "S01", "status": "completed", "route_match": True, "verification_passed": False, "result": {"proposed_hs_code": None}},
        {"scenario_id": "S02", "status": "completed", "route_match": True, "verification_passed": True, "result": {"proposed_hs_code": None}},
    ]

    comparison = evaluate_results.compare_runs(baseline, latest)
    assert comparison["deltas"]["completed"] == 0
    assert comparison["deltas"]["route_matches"] == 0
    assert comparison["deltas"]["preliminary_verification_passed"] == -1
