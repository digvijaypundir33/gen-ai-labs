"""
Stage 7: store Stages 4-6 results in DynamoDB so they become a queryable history.

Every evaluation in Series 1 wrote a local JSON file that nothing read again. This
loads the committed result files (no model calls) into `EvaluationResults`:

    run_id       (partition key)  e.g. p07-s5-rubric-nova-micro
    item_metric  (sort key)       e.g. q01-lambda-concurrency#factual_accuracy, or "#run" for the run record

Each row carries score (the mean when n > 1), n, stdev, min, max, scorer, model and
stage. Each run gets one "#run" record with its description, source file and
recorded cost. Stage 8's gate reads its baseline from here; it can't regression-test
against a baseline that was never stored.

Writes are idempotent: rerunning overwrites the same keys.

Run:  .venv/bin/python store_results.py --dry-run
      .venv/bin/python store_results.py
      .venv/bin/python store_results.py --show p07-s5-rubric-nova-micro
"""

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from decimal import Decimal

from evalkit.bedrock import REGION
from evalkit.golden import load_golden_set

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
TABLE = "EvaluationResults"

NOVA_MICRO = "amazon.nova-micro-v1:0"
GPT_OSS = "openai.gpt-oss-120b-1:0"
SHORT = {NOVA_MICRO: "nova-micro", GPT_OSS: "gpt-oss", "amazon.nova-lite-v1:0": "nova-lite"}


def stats_row(run_id, item, metric, values, **extra):
    values = [v for v in values if v is not None]
    row = {"run_id": run_id, "item_metric": f"{item}#{metric}", "item_id": item, "metric": metric, "n": len(values)}
    if values:
        row.update(score=statistics.mean(values), min=min(values), max=max(values),
                   stdev=statistics.stdev(values) if len(values) > 1 else 0.0)
    row.update(extra)
    return row


def run_record(run_id, stage, description, source, cost_usd, **extra):
    return {"run_id": run_id, "item_metric": "#run", "stage": stage, "description": description,
            "source_file": source, "recorded_cost_usd": cost_usd, **extra}


def load(name):
    with open(os.path.join(RESULTS, name)) as f:
        return json.load(f)


def build_rows():
    rows = []

    # Stage 4b: managed programmatic Q&A, one run per model. The job output's `category`
    # is the expected *document*, and two questions share each of four documents. So rows
    # are keyed by the golden item_id, matched on the question text. The first load keyed
    # them by category and silently overwrote 32 of 335 rows; a duplicate-key test caught it.
    item_by_question = {q["question"]: q["item_id"] for q in load_golden_set()}
    qa = load("managed-eval/qa-summary.json")
    for job, s in qa.items():
        run_id = f"p07-s4-managed-{job}"
        rows.append(run_record(run_id, 4, f"Bedrock automatic Q&A eval, bare {SHORT[s['model']]}, no retrieval",
                               "results/managed-eval/qa-summary.json", 0.005, model=s["model"]))
        for i in s["items"]:
            for metric, key in (("f1", "managed_f1"), ("robustness", "managed_robustness"),
                                ("toxicity", "managed_toxicity"), ("p01_overlap", "p01_overlap")):
                rows.append(stats_row(run_id, item_by_question[i["prompt"]], metric, [i[key]], stage=4, model=s["model"],
                                      scorer="bedrock-managed" if key.startswith("managed") else "p01-word-recall"))

    # Stage 4c: managed RAG judge on generate's answers.
    run_id = "p07-s4-managed-rag-judge"
    rows.append(run_record(run_id, 4, "Bedrock RAG evaluation (bring your own responses), Nova Micro judge",
                           "results/managed-eval/judge-summary.json", 0.005, model=NOVA_MICRO))
    for r in load("managed-eval/judge-summary.json"):
        for metric, score in r["scores"].items():
            # A None score is stored with n=0, not dropped: the silent empty score is itself a finding.
            rows.append(stats_row(run_id, r["item_id"], metric.lower(), [score], stage=4, model=NOVA_MICRO,
                                  scorer="bedrock-rag-judge", blocked=r["blocked"]))

    # Stage 5: the assignment's combined prompt, and the independent rubrics per judge.
    j = load("judge-eval.json")
    run_id = "p07-s5-assignment-nova-micro"
    rows.append(run_record(run_id, 5, "Assignment's combined 1-10 judge prompt; trial 0 = single run, 1-5 = five-run",
                           "results/judge-eval.json", 0.007, model=NOVA_MICRO, scale="1-10"))
    for item in sorted({r["item_id"] for r in j["arm_a"]}):
        mine = [r for r in j["arm_a"] if r["item_id"] == item]
        for dim in mine[0]["scores"]:
            single = next((r["scores"][dim] for r in mine if r["trial"] == 0), None)
            rows.append(stats_row(run_id, item, dim, [r["scores"][dim] for r in mine if r["trial"] >= 1],
                                  stage=5, model=NOVA_MICRO, scorer="assignment-judge", single_run=single))
    for judge in (NOVA_MICRO, GPT_OSS):
        run_id = f"p07-s5-rubric-{SHORT[judge]}"
        rows.append(run_record(run_id, 5, f"Independent 1-5 rubric per dimension, {SHORT[judge]}, 5 runs",
                               "results/judge-eval.json", 0.003 if judge == NOVA_MICRO else 0.038,
                               model=judge, scale="1-5"))
        cells = {}
        for r in j["arm_b"]:
            if r["judge"] == judge:
                cells.setdefault((r["item_id"], r["dimension"]), []).append(r["score"])
        for (item, dim), scores in sorted(cells.items()):
            rows.append(stats_row(run_id, item, dim, scores, stage=5, model=judge, scorer="rubric-judge"))

    # Stage 6: claim checks per judge, and guardrail grounding.
    g = load("grounding-eval.json")
    for judge in (NOVA_MICRO, GPT_OSS):
        run_id = f"p07-s6-claims-{SHORT[judge]}"
        rows.append(run_record(run_id, 6, f"Claim-level check against retrieved passages, {SHORT[judge]}, 3 runs",
                               "results/grounding-eval.json", 0.02, model=judge))
        for r in g["items"]:
            c = r["claims"].get(judge)
            if c:
                rows.append(stats_row(run_id, r["item_id"], "unsupported_share", c["hallucination_rate"], stage=6,
                                      model=judge, scorer="claim-check", flagged=c["flagged"],
                                      regenerated_draft=r["answer_is_regenerated_draft"]))
    run_id = "p07-s6-guardrail-grounding"
    rows.append(run_record(run_id, 6, "ApplyGuardrail contextual grounding, rag-assistant-guardrail v5, 5 runs",
                           "results/grounding-eval.json", 0.02, threshold=0.75))
    for r in g["items"]:
        if r["grounding_scores"]:
            rows.append(stats_row(run_id, r["item_id"], "grounding", r["grounding_scores"], stage=6,
                                  scorer="bedrock-guardrail", regenerated_draft=r["answer_is_regenerated_draft"]))
    return rows


def to_dynamo(value):
    if isinstance(value, float):
        return Decimal(str(round(value, 6)))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items() if v is not None}
    return value


def main():
    parser = argparse.ArgumentParser(description="Stage 7: store results in DynamoDB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--show", metavar="RUN_ID", help="query one run back and print it")
    args = parser.parse_args()

    if args.show:
        import boto3
        from boto3.dynamodb.conditions import Key
        table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
        items = table.query(KeyConditionExpression=Key("run_id").eq(args.show))["Items"]
        for it in items:
            print(it["item_metric"], {k: (float(v) if isinstance(v, Decimal) else v)
                                      for k, v in it.items() if k not in ("run_id", "item_metric")})
        print(f"{len(items)} rows for {args.show}")
        return 0

    rows = build_rows()
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    runs = sorted({r["run_id"] for r in rows})
    print(f"{len(rows)} rows across {len(runs)} runs:")
    for run_id in runs:
        print(f"  {run_id:34s} {sum(1 for r in rows if r['run_id'] == run_id):4d}")
    if args.dry_run:
        return 0

    keys = {(r["run_id"], r["item_metric"]) for r in rows}
    if len(keys) != len(rows):
        print(f"refusing to write: {len(rows) - len(keys)} duplicate keys would overwrite each other")
        return 1

    import boto3
    from boto3.dynamodb.conditions import Key
    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    # Keep each run an exact copy of its source files: remove keys the files no longer produce.
    stale = []
    for run_id in runs:
        resp = table.query(KeyConditionExpression=Key("run_id").eq(run_id), ProjectionExpression="item_metric")
        stale += [(run_id, it["item_metric"]) for it in resp["Items"] if (run_id, it["item_metric"]) not in keys]
    with table.batch_writer(overwrite_by_pkeys=["run_id", "item_metric"]) as batch:
        for run_id, item_metric in stale:
            batch.delete_item(Key={"run_id": run_id, "item_metric": item_metric})
        for row in rows:
            batch.put_item(Item=to_dynamo({**row, "recorded_at": recorded_at}))
    print(f"wrote {len(rows)} rows to {TABLE}, removed {len(stale)} stale rows")

    stored = sum(table.query(KeyConditionExpression=Key("run_id").eq(r), Select="COUNT")["Count"] for r in runs)
    print(f"read back: {stored} rows {'(matches)' if stored == len(rows) else '(MISMATCH)'}")
    return 0 if stored == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
