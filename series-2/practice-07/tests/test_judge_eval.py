from judge_eval import (DIMENSIONS, GPT_OSS, NOVA_MICRO, analyse, assignment_prompt, extract_json,
                        parse_assignment, parse_rubric, rubric_prompt)


def test_extract_json_bare_fenced_and_garbage():
    assert extract_json('{"score": 4, "reason": "ok"}') == {"score": 4, "reason": "ok"}
    assert extract_json('Sure!\n```json\n{"score": 2}\n```\nThanks') == {"score": 2}
    assert extract_json("Here you go: {\"score\": 5} done") == {"score": 5}
    assert extract_json("no json here") is None
    assert extract_json("") is None


def test_rubric_score_out_of_range_or_missing_is_a_failure_not_a_guess():
    assert parse_rubric('{"score": 4}') == 4
    assert parse_rubric('{"score": "5"}') == 5
    assert parse_rubric('{"score": 7}') is None
    assert parse_rubric('{"reason": "forgot the score"}') is None
    assert parse_rubric("I'd say about a 4") is None


def test_assignment_parse_reads_all_six_dimensions():
    text = '{"dimensions": {' + ", ".join(f'"{d}": {{"score": 8}}' for d in DIMENSIONS) + '}, "overall_score": 8}'
    assert parse_assignment(text) == {d: 8 for d in DIMENSIONS}
    partial = parse_assignment('{"dimensions": {"relevance": {"score": 11}, "fluency": {"score": 9}}}')
    assert partial["relevance"] is None and partial["fluency"] == 9 and partial["completeness"] is None


def test_assignment_prompt_has_no_leaked_step_marker():
    p = assignment_prompt("q", "a", "ref")
    assert "Step 2" not in p
    assert "Reference Information" in p and "1 to 10" in p


def test_rubric_prompt_judges_completeness_against_the_question():
    p = rubric_prompt("completeness", "q", "a", "ref")
    assert "not everything the reference" in p


def _answers():
    return [{"item_id": "q01", "trial": 0, "usage": {"outputTokens": 100}, "latency_ms": 2000,
             "guardrail_action": "none"}]


def test_analyse_single_outside_range_and_spread():
    arm_a = [{"item_id": "q01", "trial": 0, "scores": {d: 3 for d in DIMENSIONS}}] + [
        {"item_id": "q01", "trial": t, "scores": {d: 8 for d in DIMENSIONS}} for t in range(1, 6)]
    arm_b = []
    for judge, scores in ((NOVA_MICRO, [4, 4, 5, 4, 4]), (GPT_OSS, [4, 4, 4, 4, 4])):
        for d in DIMENSIONS:
            for t, s in enumerate(scores):
                arm_b.append({"item_id": "q01", "judge": judge, "dimension": d, "trial": t, "score": s,
                              "stop_reason": "end_turn"})
    managed = [{"item_id": "q01", "scores": {"Correctness": 1.0}}]
    r = analyse(_answers(), arm_a, arm_b, managed)

    # single run 3 vs five-run [8,8,8,8,8] -> outside, in all 6 dimensions
    assert r["prediction_3"]["b_single_outside_five_run_range"]["outside"] == 6
    # Nova Micro spreads 4..5 in every cell; gpt-oss never does
    assert r["prediction_3"]["a_run_to_run_spread"][NOVA_MICRO]["share"] == 1.0
    assert r["prediction_3"]["a_run_to_run_spread"][GPT_OSS]["share"] == 0.0
    # gap 0.2 is not bigger than micro's 1-point spread
    assert r["prediction_3"]["c_between_vs_within"]["cells_gap_exceeds_within_spread"] == 0
    # median 4 -> pass; managed 1.0 -> pass -> agree
    assert r["prediction_2"]["agree"] == 1
    assert r["efficiency"][0]["quality_per_100_tokens"] is not None


def test_analyse_counts_parse_failures_and_skips_blocked_token_ratio():
    answers = [{"item_id": "q07", "trial": 0, "usage": {"outputTokens": 0}, "latency_ms": 1500,
                "guardrail_action": "converse_ungrounded_intervened"}]
    arm_b = [{"item_id": "q07", "judge": NOVA_MICRO, "dimension": d, "trial": 0, "score": None if d == "fluency" else 1,
              "stop_reason": "end_turn"} for d in DIMENSIONS]
    r = analyse(answers, [], arm_b, [{"item_id": "q07", "scores": {"Correctness": 0.0}}])
    assert r["parse_failures"][NOVA_MICRO]["failed"] == 1
    assert r["efficiency"][0]["quality_per_100_tokens"] is None
