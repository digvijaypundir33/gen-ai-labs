from decimal import Decimal

from store_results import build_rows, stats_row, to_dynamo


def test_build_rows_from_committed_results():
    rows = build_rows()
    keys = [(r["run_id"], r["item_metric"]) for r in rows]
    assert len(keys) == len(set(keys)), "duplicate primary keys would silently overwrite each other"
    runs = {r["run_id"] for r in rows}
    assert all((run, "#run") in keys for run in runs), "every run has a run record"
    assert ("p07-s5-rubric-gpt-oss", "q01-lambda-concurrency#factual_accuracy") in keys


def test_missing_score_is_kept_with_n_zero_not_dropped():
    row = stats_row("r", "q03", "correctness", [None])
    assert row["n"] == 0 and "score" not in row


def test_stats_row_summarises_repeated_runs():
    row = stats_row("r", "q01", "fluency", [4, 5, 5, 5, 5])
    assert row["n"] == 5 and row["min"] == 4 and row["max"] == 5 and row["score"] == 4.8


def test_to_dynamo_converts_floats_and_drops_nones():
    assert to_dynamo({"a": 0.1, "b": None, "c": "x", "d": 3}) == {"a": Decimal("0.1"), "c": "x", "d": 3}
