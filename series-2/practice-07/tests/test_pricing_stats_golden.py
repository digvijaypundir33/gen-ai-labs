import pytest

from evalkit.golden import load_golden_set
from evalkit.pricing import base_model_id, token_cost
from evalkit.stats import cohen_kappa, raw_agreement, summarize, wilson_interval


# --- pricing ---

def test_inference_profile_prefix_bills_at_base_price():
    assert base_model_id("us.amazon.nova-lite-v1:0") == "amazon.nova-lite-v1:0"
    assert token_cost("us.amazon.nova-lite-v1:0", 1000, 1000) == token_cost("amazon.nova-lite-v1:0", 1000, 1000)


def test_known_prices():
    assert token_cost("amazon.nova-micro-v1:0", 1000, 1000) == pytest.approx(0.000035 + 0.00014)
    assert token_cost("openai.gpt-oss-120b-1:0", 2000, 500) == pytest.approx(2 * 0.00015 + 0.5 * 0.0006)


def test_unknown_model_or_missing_usage_is_none():
    assert token_cost("mistral.mistral-large-2402-v1:0", 10, 10) is None
    assert token_cost("amazon.nova-micro-v1:0", None, 10) is None


# --- stats ---

def test_summarize_single_value_has_zero_stdev():
    assert summarize([3]) == {"n": 1, "mean": 3, "stdev": 0.0, "min": 3, "max": 3}


def test_summarize_distribution():
    s = summarize([1, 2, 3, 4, 5])
    assert s["mean"] == 3 and s["min"] == 1 and s["max"] == 5
    assert s["stdev"] == pytest.approx(1.5811, abs=1e-4)


def test_summarize_empty():
    assert summarize([])["n"] == 0


def test_wilson_perfect_score_is_not_certain():
    lo, hi = wilson_interval(10, 10)
    assert hi == 1.0
    assert lo == pytest.approx(0.7225, abs=1e-3)


def test_wilson_zero_and_half():
    assert wilson_interval(0, 10)[0] == 0.0
    lo, hi = wilson_interval(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3) and hi == pytest.approx(0.7634, abs=1e-3)


def test_kappa_perfect_and_chance():
    a = ["pass", "fail", "pass", "fail"]
    assert cohen_kappa(a, a) == pytest.approx(1.0)
    # Agreement exactly at chance level -> kappa 0
    assert cohen_kappa(["pass", "pass", "fail", "fail"], ["pass", "fail", "pass", "fail"]) == pytest.approx(0.0)


def test_kappa_collapses_on_a_single_label_stratum():
    # The trap: both raters say "pass" everywhere. 100% raw agreement, kappa undefined.
    a = ["pass"] * 10
    assert raw_agreement(a, a) == 1.0
    assert cohen_kappa(a, a) is None


def test_raw_agreement_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        raw_agreement(["a"], ["a", "b"])


# --- golden set ---

def test_golden_set_loads_with_stable_ids():
    items = load_golden_set()
    assert len(items) == 10
    assert items[0]["item_id"] == "q01-lambda-concurrency"
    assert len({i["item_id"] for i in items}) == 10
    assert all(i["question"] and i["ground_truth"] and i["expected_doc"] for i in items)
