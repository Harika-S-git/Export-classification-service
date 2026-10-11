import pytest

from app import core


@pytest.fixture
def canonical_passages(monkeypatch):
    passages = [
        {
            "id": "tariff.txt#p1",
            "text": "Stainless steel vacuum flasks are insulated drinking containers.",
        }
    ]
    monkeypatch.setattr(core, "load_passages", lambda: passages)
    return passages


def _verification_state(request, passage, proposed_code=None, route=None):
    return {
        "request": request,
        "passages": [passage],
        "proposed_code": proposed_code,
        "route": route,
        "warnings": [],
        "steps": [],
    }


def test_relevant_product_terms_in_canonical_citation_pass_relevance(canonical_passages):
    state = _verification_state(
        {
            "description": "vacuum flask",
            "materials": "stainless steel",
            "intended_use": "drinking container",
        },
        canonical_passages[0],
    )

    core._verify(state)

    assert state["citation_resolution_passed"] is True
    assert state["evidence_relevance_passed"] is True
    assert state["evidence_relevance_result"]["relevant_passage_ids"] == [
        "tariff.txt#p1"
    ]


def test_unrelated_canonical_passage_fails_relevance(monkeypatch):
    unrelated = {
        "id": "tariff.txt#p2",
        "text": "Fresh bananas are imported under the applicable fruit provisions.",
    }
    monkeypatch.setattr(core, "load_passages", lambda: [unrelated])
    state = _verification_state(
        {"description": "stainless steel vacuum flask"},
        unrelated,
    )

    core._verify(state)

    assert state["citation_resolution_passed"] is True
    assert state["evidence_relevance_passed"] is False
    assert state["evidence_relevance_result"]["relevant_passage_ids"] == []


def test_proposed_code_is_cleared_and_escalated_when_relevance_fails(
    monkeypatch,
):
    unrelated = {
        "id": "tariff.txt#p2",
        "text": "Fresh bananas are imported under the applicable fruit provisions.",
    }
    monkeypatch.setattr(core, "load_passages", lambda: [unrelated])
    state = _verification_state(
        {"description": "stainless steel vacuum flask"},
        unrelated,
        proposed_code="DUMMY-NOT-A-TARIFF-CODE",
        route="candidate",
    )

    core._verify(state)

    assert state["citation_resolution_passed"] is True
    assert state["evidence_relevance_passed"] is False
    assert state["proposed_code"] is None
    assert state["route"] == "specialist-classification-review"
    assert any("Evidence relevance check failed" in warning for warning in state["warnings"])


def test_clarification_route_is_preserved_when_relevance_fails(
    monkeypatch,
):
    unrelated = {
        "id": "tariff.txt#p2",
        "text": "Fresh bananas are imported under the applicable fruit provisions.",
    }
    monkeypatch.setattr(core, "load_passages", lambda: [unrelated])
    state = _verification_state(
        {"description": "stainless steel vacuum flask"},
        unrelated,
        route="seek-product-clarification",
    )

    core._verify(state)

    assert state["evidence_relevance_passed"] is False
    assert state["route"] == "seek-product-clarification"


def test_unresolved_citation_fails_closed_and_escalates(canonical_passages):
    unresolved = {
        "id": "not-in-corpus.txt#p1",
        "text": "Stainless steel vacuum flasks are insulated drinking containers.",
    }
    state = _verification_state(
        {"description": "stainless steel vacuum flask"},
        unresolved,
        proposed_code="DUMMY-NOT-A-TARIFF-CODE",
        route="candidate",
    )

    core._verify(state)

    assert state["citation_resolution_passed"] is False
    assert state["verified"] is False
    assert state["proposed_code"] is None
    assert state["route"] == "specialist-classification-review"
    assert any("fail-closed escalation" in warning for warning in state["warnings"])


@pytest.mark.parametrize(
    "request_data",
    [
        {},
        {"description": "", "materials": None, "intended_use": " "},
    ],
    ids=["missing-details", "empty-details"],
)
def test_missing_or_empty_product_details_do_not_pass_relevance(
    canonical_passages, request_data
):
    state = _verification_state(request_data, canonical_passages[0])

    core._verify(state)

    assert state["citation_resolution_passed"] is True
    assert state["evidence_relevance_passed"] is False
    assert state["evidence_relevance_result"]["requested_terms"] == []
