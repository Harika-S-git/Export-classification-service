import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app import core, main


class FakeRedis:
    def __init__(self):
        self.values = {}

    def hincrby(self, name, key, amount):
        assert name == core.VERIFICATION_METRIC_KEY
        self.values[key] = self.values.get(key, 0) + amount
        return self.values[key]

    def hgetall(self, name):
        assert name == core.VERIFICATION_METRIC_KEY
        return {
            key.encode(): str(value).encode()
            for key, value in self.values.items()
        }


def test_worker_verification_counters_are_scrapeable_from_redis(monkeypatch):
    redis_client = FakeRedis()
    monkeypatch.setattr(core, "_VERIFICATION_METRICS_REDIS", redis_client)

    core._increment_verification_outcome("failed_citation")
    core._increment_verification_outcome("failed_relevance")
    core._increment_verification_outcome("passed")
    core._increment_verification_outcome("passed")

    registry = CollectorRegistry()
    registry.register(main.RedisVerificationCollector(redis_client))
    metrics = generate_latest(registry).decode()

    assert 'export_verification_total{outcome="failed_citation"} 1.0' in metrics
    assert 'export_verification_total{outcome="failed_relevance"} 1.0' in metrics
    assert 'export_verification_total{outcome="passed"} 2.0' in metrics


def test_worker_verification_counter_rejects_unknown_outcome():
    with pytest.raises(ValueError, match="Unsupported verification outcome"):
        core._increment_verification_outcome("unexpected")


@pytest.mark.parametrize(
    ("request_data", "passage", "outcome"),
    [
        (
            {"description": "Stainless steel vacuum flask"},
            {"id": "missing.txt#p1", "text": "unresolved"},
            "failed_citation",
        ),
        (
            {"description": "Stainless steel vacuum flask"},
            {
                "id": "tariff.txt#p1",
                "text": "Fresh bananas are imported under the fruit provisions.",
            },
            "failed_relevance",
        ),
        (
            {"description": "Broom with plastic handle"},
            {
                "id": "tariff.txt#p1",
                "text": "Brooms and brushes with or without handles.",
            },
            "passed",
        ),
    ],
)
def test_verifier_increments_matching_shared_outcome(
    monkeypatch, request_data, passage, outcome
):
    redis_client = FakeRedis()
    monkeypatch.setattr(core, "_VERIFICATION_METRICS_REDIS", redis_client)
    canonical_passages = (
        [] if outcome == "failed_citation" else [passage]
    )
    monkeypatch.setattr(core, "load_passages", lambda: canonical_passages)
    state = {
        "request": request_data,
        "passages": [passage],
        "proposed_code": None,
        "route": "specialist-classification-review",
        "warnings": [],
        "steps": [],
    }

    core._verify(state)

    assert redis_client.values == {outcome: 1}
