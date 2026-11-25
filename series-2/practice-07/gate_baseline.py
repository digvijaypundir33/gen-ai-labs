"""
Stage 8: build the quality gate's dataset and its baseline, and set the threshold from data.

1. gate_dataset.json (bundled into the Lambda): the 10 golden questions with their
   reference answers and Stage 3's retrieved passages, which candidate mode needs.
2. Baseline: score all 30 Stage 3 answers (3 runs of the real system) with the
   gate's exact scorer. The scoring functions are imported from the Lambda's own
   file, so the baseline and the gate can't drift apart. Calls go through
   evalkit's cache.
3. Threshold: each Stage 3 run gives one run score (mean over 10 items). The
   threshold is the mean of those minus 2 standard deviations, with a floor of one
   item flipping from a perfect answer to a refusal (0.4 on a 10-item mean of 1-5
   scores). Three runs is a very small sample, and a 2-sd margin computed from it
   could be near zero. The floor stops ordinary noise (one extra guardrail block,
   as q02 showed in Stage 3) from failing the gate.

Writes the baseline to EvaluationResults as run p07-s8-baseline: "#gate" holds
score and threshold, and one row per Stage 3 run.

Run:  .venv/bin/python gate_baseline.py --dry-run
      .venv/bin/python gate_baseline.py
"""

import argparse
import importlib.util
import json
import os
import statistics
import sys

from evalkit.bedrock import REGION, Bedrock, BudgetExceeded, add_budget_args

HERE = os.path.dirname(os.path.abspath(__file__))
LAMBDA_DIR = os.path.join(HERE, "lambda", "eval-quality-gate")
CACHE_DIR = os.path.join(HERE, "results", "cache")
RESPONSES_PATH = os.path.join(HERE, "results", "responses.jsonl")
OUT_PATH = os.path.join(HERE, "results", "gate-baseline.json")
ONE_ITEM_FLIP = (5 - 1) / 10  # one of 10 items going from a perfect 5 to a refusal's 1

spec = importlib.util.spec_from_file_location("gate", os.path.join(LAMBDA_DIR, "lambda_function.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def threshold_from(run_scores):
    mean = statistics.mean(run_scores)
    sd = statistics.stdev(run_scores) if len(run_scores) > 1 else 0.0
    return mean, sd, mean - max(2 * sd, ONE_ITEM_FLIP)


def main():
    parser = add_budget_args(argparse.ArgumentParser(description="Stage 8 gate baseline"), default_max_calls=180)
    args = parser.parse_args()

    with open(RESPONSES_PATH) as f:
        rows = [json.loads(line) for line in f]
    dataset = [{"item_id": r["item_id"], "question": r["question"], "ground_truth": r["ground_truth"],
                "chunks": [{"doc": c["doc"], "text": c["text"]} for c in r["chunks"]]}
               for r in sorted(rows, key=lambda r: r["item_id"]) if r["trial"] == 0]
    with open(os.path.join(LAMBDA_DIR, "gate_dataset.json"), "w") as f:
        json.dump(dataset, f, indent=1)
    by_id = {d["item_id"]: d for d in dataset}

    bedrock = Bedrock(CACHE_DIR, max_calls=args.max_calls, dry_run=args.dry_run)

    def cached_converse(model_id, prompt, max_tokens, run):
        rec = bedrock.converse(model_id, prompt, max_tokens=max_tokens, temperature=0.2, trial=run)
        return rec["text"] if rec else None

    per_trial = {}
    try:
        for r in sorted(rows, key=lambda r: (r["trial"], r["item_id"])):
            score, failures = gate.score_answer(by_id[r["item_id"]], r["answer"], cached_converse)
            per_trial.setdefault(r["trial"], []).append(
                {"item_id": r["item_id"], "score": score, "blocked": r["guardrail_action"] != "none",
                 "parse_failures": failures})
    except BudgetExceeded as e:
        print(f"stopped: {e}")
    print(bedrock.summary())
    if args.dry_run or len(per_trial) < 3:
        return 0

    run_scores = [statistics.mean(i["score"] for i in items) for _, items in sorted(per_trial.items())]
    mean, sd, threshold = threshold_from(run_scores)
    result = {"run_scores": run_scores, "mean": mean, "sd": sd, "threshold": threshold,
              "rule": "mean - max(2*sd, one-item flip of 0.4)", "per_trial": per_trial}
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nStage 3 run scores (gate scorer, mean of 10 items): {[round(s, 3) for s in run_scores]}")
    print(f"mean {mean:.3f}  sd {sd:.3f}  2*sd {2 * sd:.3f}  one-item floor {ONE_ITEM_FLIP:.2f}")
    print(f"threshold = {threshold:.3f}")
    for t, items in sorted(per_trial.items()):
        print(f"  trial {t}: " + " ".join(f"{i['item_id'][:3]}={i['score']:.1f}{'B' if i['blocked'] else ''}" for i in items))

    import boto3
    table = boto3.resource("dynamodb", region_name=REGION).Table("EvaluationResults")
    with table.batch_writer(overwrite_by_pkeys=["run_id", "item_metric"]) as batch:
        batch.put_item(Item=gate.to_dynamo({"run_id": "p07-s8-baseline", "item_metric": "#gate", "stage": 8,
                                            "score": mean, "threshold": threshold, "sd": sd,
                                            "rule": result["rule"], "source_file": "results/gate-baseline.json"}))
        for t, s in enumerate(run_scores):
            batch.put_item(Item=gate.to_dynamo({"run_id": "p07-s8-baseline", "item_metric": f"stage3-trial{t}",
                                                "stage": 8, "score": s}))
    print("stored baseline in EvaluationResults (run p07-s8-baseline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
