"""
Stage 3: collect the answers every later stage scores, once.

The 10 golden questions go to the live `generate` Lambda, `--trials` times each,
by direct invoke with include_debug, so each answer comes back with the chunk
text it was generated from and the answer model's token usage. Each answer is
written to results/responses.jsonl. Stages 4-6 read that file rather than
generating new answers, so every scorer is compared on the same answers.

Trials 2-3 of a question will usually reuse trial 1's retrieval (generate's
RagQueryCache), and generation runs at temperature 0. So repeated trials mostly
measure the guardrail's non-determinism, not the answer model's. That is the
real system's behaviour, and it is recorded as such.

Run:  .venv/bin/python collect_responses.py --dry-run
      .venv/bin/python collect_responses.py --max-calls 3 --trials 1   (pilot)
      .venv/bin/python collect_responses.py
"""

import argparse
import json
import os
import sys

from evalkit.bedrock import BudgetExceeded, add_budget_args
from evalkit.golden import load_golden_set
from evalkit.lambdas import CachedLambda
from evalkit.stats import summarize

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "results", "cache")
OUT_PATH = os.path.join(HERE, "results", "responses.jsonl")


def doc_stem(doc):
    # Retrieved chunks name the file (lambda-concurrency.md); the golden set uses
    # the stem (lambda-concurrency). The pilot read 0/3 "expected doc retrieved"
    # until this was normalised.
    return doc[:-3] if doc.endswith(".md") else doc


def to_row(item, record):
    body = record["body"]
    debug = body.get("debug") or {}
    chunks = debug.get("chunks") or []
    retrieved = [doc_stem(c["doc"]) for c in chunks]
    return {
        "item_id": item["item_id"],
        "trial": record["trial"],
        "question": item["question"],
        "ground_truth": item["ground_truth"],
        "expected_doc": item["expected_doc"],
        "answer": body.get("answer"),
        "guardrail_action": body.get("guardrail_action"),
        "grounding_score": body.get("confidence"),
        "model_id": body.get("model_id"),
        "retrieved_docs": retrieved,
        "expected_doc_retrieved": item["expected_doc"] in retrieved,
        "chunks": chunks,
        "usage": debug.get("usage"),
        "latency_ms": record["latency_ms"],
        "called_at": record["called_at"],
    }


def main():
    parser = add_budget_args(argparse.ArgumentParser(description=__doc__.splitlines()[1]), default_max_calls=30)
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()

    golden = load_golden_set()
    generate = CachedLambda("generate", CACHE_DIR, max_calls=args.max_calls, dry_run=args.dry_run)

    rows = []
    try:
        for trial in range(args.trials):
            for item in golden:
                record = generate.invoke({"query": item["question"], "include_debug": True}, trial=trial)
                if record is not None:
                    rows.append(to_row(item, record))
    except BudgetExceeded as e:
        # A pilot stops here on purpose. What ran is cached, so the full run reuses it.
        print(f"stopped: {e}")

    print(generate.summary())
    if args.dry_run:
        return 0

    with open(OUT_PATH, "w") as f:
        for row in sorted(rows, key=lambda r: (r["item_id"], r["trial"])):
            f.write(json.dumps(row) + "\n")
    print(f"wrote {len(rows)} rows -> {os.path.relpath(OUT_PATH, HERE)}\n")

    print(f"{'item':34s} {'blocked':>8s} {'grounding scores':24s} {'expected doc retrieved':>22s}")
    print("-" * 92)
    for item in golden:
        mine = [r for r in rows if r["item_id"] == item["item_id"]]
        blocked = sum(1 for r in mine if r["guardrail_action"] != "none")
        scores = [r["grounding_score"] for r in mine if r["grounding_score"] is not None]
        shown = " ".join(f"{s:.2f}" for s in scores) or "-"
        retrieved = sum(1 for r in mine if r["expected_doc_retrieved"])
        print(f"{item['item_id']:34s} {blocked:3d}/{len(mine):<4d} {shown:24s} {retrieved:>16d}/{len(mine)}")
    all_scores = [r["grounding_score"] for r in rows if r["grounding_score"] is not None]
    s = summarize(all_scores)
    if s["n"]:
        print(f"\ngrounding overall: n={s['n']} mean={s['mean']:.2f} stdev={s['stdev']:.2f} "
              f"min={s['min']:.2f} max={s['max']:.2f}")
    print(f"blocked: {sum(1 for r in rows if r['guardrail_action'] != 'none')}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
