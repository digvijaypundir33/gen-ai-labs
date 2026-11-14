"""
Stage 8: cost-capability tradeoff reporting over REAL production data.

Bonus Assignment 01 Part 2 Step 2 ships `analyze_cost_capability_tradeoff()`
driven by a hand-written `test_history` list - five synthetic dicts with made-up
costs. That structure can only ever tell you what you already typed into it.

This reads the actual `RoutingMetrics` DynamoDB table, which practice-03 has
been writing on every real request through document-routing-workflow, and which
practice-06 Stage 8 extended with real billed token counts and computed cost.

It also refuses to make claims the data can't support. The assignment's version
happily recommends "downgrade these queries to a cheaper model" off a single
row per model; here, any model or complexity tier below MIN_SAMPLES is reported
as insufficient rather than ranked. That guard is the same lesson practice-05
learned the hard way when a confident n=1 finding had to be retracted.

Run:  AWS_PROFILE=rag-assistant python cost_capability_report.py
"""

import statistics
from collections import defaultdict
from decimal import Decimal

import boto3

TABLE = "RoutingMetrics"
MIN_SAMPLES = 3  # below this, report the gap instead of ranking

# Same table as record-metrics/benchmark_models, re-verified 2026-08-18.
PRICING_PER_1K_TOKENS = {
    "amazon.nova-micro-v1:0": {"input": 0.000035, "output": 0.00014},
    "amazon.nova-lite-v1:0": {"input": 0.00006, "output": 0.00024},
    "amazon.nova-pro-v1:0": {"input": 0.0008, "output": 0.0032},
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.001, "output": 0.005},
}


def _f(v):
    return float(v) if isinstance(v, Decimal) else v


def load_rows():
    table = boto3.resource("dynamodb").Table(TABLE)
    rows, kwargs = [], {}
    while True:
        resp = table.scan(**kwargs)
        rows.extend(resp["Items"])
        if "LastEvaluatedKey" not in resp:
            return rows
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def main():
    rows = load_rows()
    priced = [r for r in rows if r.get("estimated_cost_usd") is not None]

    print("=" * 84)
    print("Stage 8: cost-capability tradeoff, from real RoutingMetrics data")
    print("=" * 84)
    print(f"rows in table       : {len(rows)}")
    print(f"rows with cost data : {len(priced)}   "
          f"({len(rows) - len(priced)} predate Stage 8 / had no usage block)")
    print()

    if not priced:
        print("No priced rows yet. Run traffic through document-routing-workflow first.")
        return

    # ---- per-model ----
    by_model = defaultdict(list)
    for r in priced:
        by_model[r["model_used"]].append(r)

    print("-" * 84)
    print("Per model")
    print("-" * 84)
    print(f"{'model':26s} {'n':>3s} {'avg in':>8s} {'avg out':>8s} "
          f"{'avg $/req':>12s} {'total $':>12s}")
    for model, rs in sorted(by_model.items()):
        costs = [_f(r["estimated_cost_usd"]) for r in rs]
        ins = [int(r["input_tokens"]) for r in rs if r.get("input_tokens") is not None]
        outs = [int(r["output_tokens"]) for r in rs if r.get("output_tokens") is not None]
        print(f"{model:26s} {len(rs):3d} "
              f"{statistics.mean(ins) if ins else 0:8.0f} "
              f"{statistics.mean(outs) if outs else 0:8.0f} "
              f"{statistics.mean(costs):12.8f} {sum(costs):12.8f}")

    # ---- per complexity tier ----
    print()
    print("-" * 84)
    print("Per complexity tier - which model actually served it, and at what cost")
    print("-" * 84)
    by_tier = defaultdict(lambda: defaultdict(list))
    for r in priced:
        by_tier[str(r.get("complexity", "unknown"))][r["model_used"]].append(
            _f(r["estimated_cost_usd"]))

    for tier in sorted(by_tier):
        total_n = sum(len(v) for v in by_tier[tier].values())
        print(f"\n  complexity={tier}  (n={total_n})")
        if total_n < MIN_SAMPLES:
            print(f"    INSUFFICIENT DATA - {total_n} sample(s), need {MIN_SAMPLES}. "
                  f"Not ranking.")
            continue
        for model, costs in sorted(by_tier[tier].items(), key=lambda kv: statistics.mean(kv[1])):
            print(f"    {model:26s} n={len(costs):3d}  avg=${statistics.mean(costs):.8f}")

    # ---- what a switch would cost ----
    print()
    print("-" * 84)
    print("Counterfactual: same observed token volumes, priced at each model's rate")
    print("-" * 84)
    tot_in = sum(int(r["input_tokens"]) for r in priced if r.get("input_tokens") is not None)
    tot_out = sum(int(r["output_tokens"]) for r in priced if r.get("output_tokens") is not None)
    actual = sum(_f(r["estimated_cost_usd"]) for r in priced)
    print(f"observed volume: {tot_in} input + {tot_out} output tokens over {len(priced)} requests")
    print(f"actual spend   : ${actual:.8f}\n")
    print(f"{'if everything ran on':30s} {'total $':>12s} {'vs actual':>12s}")
    for model, price in sorted(PRICING_PER_1K_TOKENS.items()):
        hypo = (tot_in / 1000.0) * price["input"] + (tot_out / 1000.0) * price["output"]
        delta = hypo - actual
        print(f"{model:30s} {hypo:12.8f} {delta:+12.8f}")

    # ---- recommendations, with the sample-size guard ----
    print()
    print("-" * 84)
    print("Recommendations")
    print("-" * 84)
    issued = False
    for tier, models in sorted(by_tier.items()):
        n = sum(len(v) for v in models.values())
        if n < MIN_SAMPLES:
            print(f"  [tier={tier}] n={n} - too few samples to recommend anything. "
                  f"This is a gap to fill, not a finding.")
            issued = True
            continue
        if len(models) > 1:
            ranked = sorted(models.items(), key=lambda kv: statistics.mean(kv[1]))
            cheap, exp = ranked[0], ranked[-1]
            ratio = statistics.mean(exp[1]) / statistics.mean(cheap[1])
            print(f"  [tier={tier}] served by {len(models)} models; "
                  f"{exp[0].split('.')[-1]} costs {ratio:.1f}x {cheap[0].split('.')[-1]}.")
            print("     Cost alone does not justify a switch - check the quality data in "
                  "practice-06 Stage 4 before downgrading.")
            issued = True
    if not issued:
        print("  Each complexity tier is served by a single model; no routing change to weigh.")
    print()
    print("NOTE: cost is only half the tradeoff. practice-06 Stage 4 measured nova-micro")
    print("      producing answers that the guardrail BLOCKED 8/10 times on a query")
    print("      nova-lite answered 10/10 - a cheaper per-token rate that buys refusals")
    print("      is not cheaper. Read this report alongside that measurement.")


if __name__ == "__main__":
    main()
