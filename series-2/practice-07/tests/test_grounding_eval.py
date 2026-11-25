import pytest

from evalkit.pricing import guardrail_cost_estimate, text_units
from grounding_eval import flagged, generate_prompt_parts, hallucination_rate, parse_claims


def test_parse_claims_valid_and_invalid():
    ok = parse_claims('{"claims": [{"claim": "Limit is 1,000", "label": "supported"}]}')
    assert ok == [{"claim": "Limit is 1,000", "label": "supported"}]
    assert parse_claims('{"claims": [{"claim": "x", "label": "maybe"}]}') is None  # bad label voids the reply
    assert parse_claims('{"claims": "none"}') is None
    assert parse_claims("not json") is None
    assert parse_claims('{"claims": []}') == []


def test_hallucination_rate():
    claims = [{"claim": "a", "label": "supported"}, {"claim": "b", "label": "not_mentioned"},
              {"claim": "c", "label": "contradicted"}, {"claim": "d", "label": "supported"}]
    assert hallucination_rate(claims) == 0.5
    assert hallucination_rate([]) is None


def test_flagged_needs_a_majority_of_usable_runs():
    bad = [{"claim": "x", "label": "not_mentioned"}]
    good = [{"claim": "y", "label": "supported"}]
    assert flagged([bad, bad, good]) is True
    assert flagged([bad, good, good]) is False
    assert flagged([bad, None, None]) is True  # one usable run, and it's flagged
    assert flagged([None, None, None]) is False


def test_prompt_parts_match_generate():
    source, instruction = generate_prompt_parts("Q?", [{"doc": "a.md", "text": "T1"}, {"doc": "b.md", "text": "T2"}])
    assert source == "[Source 1: a.md]\nT1\n\n[Source 2: b.md]\nT2"
    assert instruction.endswith("Question: Q?") and "[Source N] citation" in instruction


def test_guardrail_cost_estimate():
    assert text_units("") == 1 and text_units("x" * 1000) == 1 and text_units("x" * 1001) == 2
    # 5 units of source + 1 query + 1 answer grounding, + 1 answer unit of content/topic/PII
    assert guardrail_cost_estimate("x" * 4500, "q", "a") == pytest.approx(7 * 0.0001 + 0.0004)
