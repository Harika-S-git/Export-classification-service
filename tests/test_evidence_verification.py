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


@pytest.mark.parametrize(
    ("request_data", "passage"),
    [
        (
            {"description": "Vacuum flask with moulded plastic outer body"},
            {
                "id": "tariff.txt#p14",
                "text": (
                    "Stainless steel outer body components for vacuum-insulated "
                    "metal containers."
                ),
            },
        ),
        (
            {
                "description": "Vacuum flask with outer body",
                "materials": "titanium alloy",
            },
            {
                "id": "tariff.txt#p14",
                "text": "Titanium alloy outer body components.",
            },
        ),
        (
            {"description": "Stainless steel thermos with plastic shell"},
            {
                "id": "tariff.txt#p14",
                "text": (
                    "Stainless steel and plastic shells are used for insulated "
                    "beverage vessels."
                ),
            },
        ),
    ],
    ids=[
        "vacuum-flask-material-overlap",
        "declared-material-overlap",
        "thermos-material-overlap",
    ],
)
def test_material_overlap_without_matching_article_terms_fails(
    request_data, passage
):
    result = core._assess_evidence_relevance(request_data, [passage])

    assert result["passed"] is False
    assert result["relevant_passage_ids"] == []


def test_broom_heading_matches_broom_and_handle_terms():
    result = core._assess_evidence_relevance(
        {"description": "Broom with plastic handle"},
        [{
            "id": "chap_96.txt#p3",
            "text": (
                "9603 BROOMS, BRUSHES, HAND-OPERATED MECHANICAL FLOOR "
                "SWEEPERS; brooms and brushes with or without handles."
            ),
        }],
    )

    assert result["passed"] is True
    assert result["matched_terms"] == ["broom", "handle"]
    assert result["relevant_passage_ids"] == ["chap_96.txt#p3"]


@pytest.mark.parametrize(
    "description",
    [
        "Stainless steel vacuum flask with moulded plastic outer body",
        "Stainless steel thermos with a plastic shell",
    ],
    ids=["S01-vacuum-flask", "S19-thermos"],
)
def test_hidden_named_article_heading_does_not_verify_truncated_citation(
    monkeypatch, description
):
    passage = {
        "id": "chap_96.txt#p7",
        "text": (
            "Stainless steel outer body components. " * 40
            + "9617 VACUUM FLASKS AND OTHER VACUUM VESSELS."
        ),
    }
    monkeypatch.setattr(core, "load_passages", lambda: [passage])
    state = _verification_state(
        {"description": description},
        passage,
        route="specialist-classification-review",
    )

    core._verify(state)

    assert state["citation_resolution_passed"] is True
    assert state["evidence_relevance_passed"] is False
    assert state["verified"] is False
    assert state["route"] == "specialist-classification-review"


def test_visible_broom_heading_is_relevant_but_not_classification_support(
    monkeypatch,
):
    passage = {
        "id": "chap_96.txt#p3",
        "text": (
            "9603 BROOMS, BRUSHES, HAND-OPERATED MECHANICAL FLOOR "
            "SWEEPERS; brooms and brushes with or without handles."
        ),
    }
    monkeypatch.setattr(core, "load_passages", lambda: [passage])
    state = _verification_state(
        {"description": "Broom with plastic handle"},
        passage,
        proposed_code="DUMMY-NOT-A-TARIFF-CODE",
        route="specialist-classification-review",
    )

    core._verify(state)

    assert state["citation_resolution_passed"] is True
    assert state["evidence_relevance_passed"] is True
    assert state["classification_support_passed"] is False
    assert state["verified"] is True
    assert state["proposed_code"] is None
    assert state["route"] == "specialist-classification-review"
    assert "preliminary lexical relevance only" in state["verification_scope"]
    assert "not semantic entailment, classification support, or legal correctness" in (
        state["verification_scope"]
    )
    assert any(
        "does not establish classification support" in warning
        for warning in state["warnings"]
    )


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
    assert state["classification_support_passed"] is False
    assert state["proposed_code"] is None
    assert state["route"] == "specialist-classification-review"
    assert any(
        "does not establish classification support" in warning
        for warning in state["warnings"]
    )


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
    assert state["classification_support_passed"] is False
    assert state["route"] == "seek-product-clarification"


def test_no_code_specialist_review_reports_relevance_without_classification_support(
    monkeypatch,
):
    passage = {
        "id": "chap_96.txt#p3",
        "text": (
            "9603 BROOMS, BRUSHES, HAND-OPERATED MECHANICAL FLOOR SWEEPERS; "
            "brooms and brushes with or without handles."
        ),
    }
    monkeypatch.setattr(core, "load_passages", lambda: [passage])
    state = _verification_state(
        {"description": "Broom with plastic handle"},
        passage,
        route="specialist-classification-review",
    )

    core._verify(state)

    assert state["citation_resolution_passed"] is True
    assert state["evidence_relevance_passed"] is True
    assert state["classification_support_passed"] is False
    assert state["verified"] is True
    assert state["proposed_code"] is None
    assert state["route"] == "specialist-classification-review"


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
    state = _verification_state(
        request_data,
        canonical_passages[0],
        route="seek-product-clarification",
    )

    core._verify(state)

    assert state["citation_resolution_passed"] is True
    assert state["evidence_relevance_passed"] is False
    assert state["classification_support_passed"] is False
    assert state["evidence_relevance_result"]["requested_terms"] == []
    assert state["route"] == "seek-product-clarification"
