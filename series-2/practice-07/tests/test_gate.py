import importlib.util
import os

import pytest

from gate_baseline import ONE_ITEM_FLIP, threshold_from

spec = importlib.util.spec_from_file_location(
    "gate_lambda", os.path.join(os.path.dirname(__file__), "..", "lambda", "eval-quality-gate", "lambda_function.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_parse_score():
    assert gate.parse_score('{"score": 4, "reason": "x"}') == 4
    assert gate.parse_score('ok {"score": 6} ok') is None
    assert gate.parse_score("no json") is None
    assert gate.parse_score(None) is None


def test_score_answer_averages_dimensions_and_runs():
    replies = iter(['{"score": 5}', '{"score": 5}', '{"score": 4}', '{"score": 3}', "garbage", '{"score": 3}'])
    score, failures = gate.score_answer({"question": "q", "ground_truth": "r"}, "a", lambda *a: next(replies))
    assert failures == 1
    assert score == pytest.approx((5 + 5 + 4 + 3 + 3) / 5)


def test_score_answer_with_nothing_parseable_scores_as_a_refusal():
    score, failures = gate.score_answer({"question": "q", "ground_truth": "r"}, "a", lambda *a: "nope")
    assert score == 1.0 and failures == len(gate.DIMENSIONS) * gate.SCORE_RUNS


def test_decide():
    assert gate.decide(3.9, {"threshold": 3.8}) == "PASS"
    assert gate.decide(3.8, {"threshold": 3.8}) == "PASS"
    assert gate.decide(3.79, {"threshold": 3.8}) == "FAIL"


def test_threshold_uses_two_sd_or_the_one_item_floor():
    mean, sd, t = threshold_from([4.2, 4.2, 4.2])
    assert sd == 0 and t == pytest.approx(4.2 - ONE_ITEM_FLIP)
    mean, sd, t = threshold_from([4.6, 3.6, 4.1])
    assert t == pytest.approx(mean - 2 * sd)


def test_prompt_parts_match_generate():
    source, instruction = gate.generate_prompt_parts("Q?", [{"doc": "a.md", "text": "T"}])
    assert source == "[Source 1: a.md]\nT" and instruction.endswith("Question: Q?")
