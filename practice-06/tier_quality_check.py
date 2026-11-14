"""
Stage 4 verification: does complexity tiering cost answer quality?

Tiering only pays if the cheaper/stronger model it picks answers at least as
well as the nova-lite default it replaced. The first live smoke test looked
alarming - the micro and pro tiers both came back guardrail-blocked as
ungrounded (grounding 0.02 and 0.38) while lite answered the same corpus
cleanly at 0.91 - but a single sample cannot distinguish "this tier answers
worse" from "this query is hard" from plain noise.

Practice-05 measured exactly this trap: the contextual grounding score is
non-deterministic, scoring one well-supported answer between 0.30 and 0.72
across 6 identical calls against a fixed 0.75 threshold. A single-sample
comparison across models is therefore worthless, and practice-05 already
retracted a finding built on n=1.

So: hold the query constant, vary only the tier (via generate's direct-invoke
`tier` override), n trials each, and report the distribution rather than a
number.

Run:  AWS_PROFILE=rag-assistant python tier_quality_check.py
"""

import json
import statistics
import sys

import boto3

lambda_client = boto3.client("lambda", region_name="us-east-1")

TRIALS = 5
TIERS = ["micro", "lite", "pro"]

# The two queries that came back blocked in the smoke test, plus the one that
# passed - so the comparison covers a known-good case as a control.
QUERIES = [
    ("short/definitional", "What is AWS Lambda?"),
    ("corpus-answerable (control)",
     "What is the default total concurrency limit for Lambda functions in an AWS account?"),
    ("multi-part/complex",
     "Compare S3 versioning and DynamoDB on-demand capacity, and explain how each "
     "affects cost and durability"),
]


def call(query, tier):
    resp = lambda_client.invoke(
        FunctionName="generate",
        Payload=json.dumps({"query": query, "tier": tier}),
    )
    body = json.loads(json.loads(resp["Payload"].read())["body"])
    return body.get("confidence"), body.get("answer", ""), body.get("guardrail_action")


def main():
    print("=" * 90)
    print(f"Stage 4 verification: grounding score by tier, n={TRIALS} per cell")
    print("Query held constant; only modelId/maxTokens vary.")
    print("=" * 90)

    for label, query in QUERIES:
        print(f"\n### {label}")
        print(f'    "{query[:78]}{"..." if len(query) > 78 else ""}"')
        print()
        print(f"    {'tier':6s} {'scores':38s} {'mean':>6s} {'min':>6s} {'max':>6s} {'blocked':>8s}")
        print("    " + "-" * 80)
        for tier in TIERS:
            scores, blocked = [], 0
            for _ in range(TRIALS):
                conf, answer, action = call(query, tier)
                if conf is not None:
                    scores.append(conf)
                if action and action != "none":
                    blocked += 1
            if scores:
                shown = " ".join(f"{s:.2f}" for s in scores)
                mean = statistics.mean(scores)
                print(f"    {tier:6s} {shown:38s} {mean:6.2f} {min(scores):6.2f} "
                      f"{max(scores):6.2f} {blocked:5d}/{TRIALS}")
            else:
                print(f"    {tier:6s} {'(no grounding score returned)':38s} "
                      f"{'-':>6s} {'-':>6s} {'-':>6s} {blocked:5d}/{TRIALS}")
    print()
    print("=" * 90)
    print("Reading it: if a tier's score range OVERLAPS lite's, the tier is not the")
    print("cause - the query is. Only a non-overlapping, consistently lower range")
    print("is evidence that tiering degraded the answer.")
    print("=" * 90)


if __name__ == "__main__":
    sys.exit(main())
