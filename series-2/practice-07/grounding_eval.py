"""
Stage 6: claim-level checks vs. the guardrail's single grounding score.

Bedrock's contextual grounding gives one 0-1 number per answer. This splits the
answer into its factual claims and labels each one against the retrieved
passages: supported, contradicted or not_mentioned. Unlike Stage 5's judges, it
gets the passages, which is the gap that made gpt-oss mark a true fact false.

Built to spend as little as possible:
- Claim checks run first. They're one cheap call per answer listing and labelling
  every claim, 3 runs, with two judge families.
- The guardrail's grounding score (~$0.001 a call) is re-run 5 times only where
  it matters: answers the claim check flags, q10 (the suspected false block),
  P05's hallucination probe, and one control.

Blocked answers were replaced by a refusal, so their real text was never seen.
Their draft is regenerated once with generate's exact prompt, Nova Lite at
temperature 0 and no guardrail. It approximates what the guardrail saw; Stage 3
showed temperature 0 isn't fully deterministic.

Run:  .venv/bin/python grounding_eval.py --dry-run
      .venv/bin/python grounding_eval.py
"""

import argparse
import json
import os
import statistics
import sys

from evalkit.bedrock import Bedrock, BudgetExceeded, add_budget_args
from evalkit.lambdas import CachedLambda
from judge_eval import GPT_OSS, NOVA_MICRO, extract_json

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "results", "cache")
RESPONSES_PATH = os.path.join(HERE, "results", "responses.jsonl")
OUT_PATH = os.path.join(HERE, "results", "grounding-eval.json")

NOVA_LITE = "amazon.nova-lite-v1:0"
GUARDRAIL_ID, GUARDRAIL_VERSION = "5jk3sefhtv16", "5"  # what generate uses
GROUNDING_THRESHOLD = 0.75
CLAIM_JUDGES = {NOVA_MICRO: 800, GPT_OSS: 2000}  # max tokens; gpt-oss spends some on reasoning
CLAIM_TRIALS = 3
GROUNDING_TRIALS = 5
CONTROL_ITEM = "q06-dynamodb-on-demand-capacity"
SUSPECTED_FALSE_BLOCK = "q10-apigateway-caching"
LABELS = ("supported", "contradicted", "not_mentioned")

# P05 grounding_test.py: a detail that isn't in any corpus doc.
PROBE_ID = "probe-snapstart"
PROBE_QUESTION = ("What is the exact millisecond value of Lambda SnapStart's cold start "
                  "improvement, as stated in the documentation?")


def generate_prompt_parts(question, chunks):
    """generate's exact grounding source and instruction (series-1/practice-02/lambda/generate)."""
    source = "\n\n".join(f"[Source {i + 1}: {c['doc']}]\n{c['text']}" for i, c in enumerate(chunks))
    instruction = (
        "Use the reference material to answer the question below. Include a [Source N] "
        "citation for any fact you use. If the material doesn't cover the answer, state "
        f"that clearly.\n\nQuestion: {question}"
    )
    return source, instruction


def claims_prompt(source, answer):
    return f"""Below are reference passages and an answer that was written from them.

Split the answer into its individual factual claims. Ignore citation markers like [Source 1], formatting, and statements that only say the passages don't cover something. Label each claim:
- supported: the passages state it
- contradicted: the passages say something different
- not_mentioned: the passages don't cover it

Reference passages:
{source}

Answer:
{answer}

Reply with only a JSON object, no other text: {{"claims": [{{"claim": "<the claim>", "label": "supported|contradicted|not_mentioned"}}]}}"""


def parse_claims(text):
    """A list of {claim, label}, or None if the reply isn't usable. A bad label voids the reply."""
    data = extract_json(text)
    claims = (data or {}).get("claims")
    if not isinstance(claims, list):
        return None
    out = []
    for c in claims:
        if not isinstance(c, dict) or c.get("label") not in LABELS or not c.get("claim"):
            return None
        out.append({"claim": c["claim"], "label": c["label"]})
    return out


def hallucination_rate(claims):
    """Share of claims not supported by the passages, or None with no claims (e.g. a pure refusal)."""
    if not claims:
        return None
    return sum(1 for c in claims if c["label"] != "supported") / len(claims)


def flagged(runs):
    """True when a majority of runs found at least one unsupported claim."""
    usable = [r for r in runs if r is not None]
    if not usable:
        return False
    return sum(1 for r in usable if any(c["label"] != "supported" for c in r)) * 2 > len(usable)


def load_items(bedrock, generate):
    with open(RESPONSES_PATH) as f:
        rows = sorted((r for r in map(json.loads, f) if r["trial"] == 0), key=lambda r: r["item_id"])
    items = [{"item_id": r["item_id"], "question": r["question"], "chunks": r["chunks"],
              "shown": r["answer"], "blocked": r["guardrail_action"] != "none",
              "stage3_grounding": r["grounding_score"]} for r in rows]

    probe = generate.invoke({"query": PROBE_QUESTION, "include_debug": True})
    if probe is not None:
        body = probe["body"]
        items.append({"item_id": PROBE_ID, "question": PROBE_QUESTION, "chunks": body["debug"]["chunks"],
                      "shown": body["answer"], "blocked": body["guardrail_action"] != "none",
                      "stage3_grounding": body.get("confidence")})

    for item in items:
        item["answer"] = item["shown"]
        if item["blocked"]:
            source, instruction = generate_prompt_parts(item["question"], item["chunks"])
            rec = bedrock.converse(NOVA_LITE, f"{source}\n\n{instruction}", max_tokens=500, temperature=0)
            item["answer"] = rec["text"] if rec else None
            item["answer_is_regenerated_draft"] = True
    return items


def run(bedrock, generate):
    items = load_items(bedrock, generate)
    for item in items:
        item["claims"] = {}
        if item["answer"] is None:
            continue
        source, _ = generate_prompt_parts(item["question"], item["chunks"])
        for judge, max_tokens in CLAIM_JUDGES.items():
            runs = []
            for t in range(CLAIM_TRIALS):
                rec = bedrock.converse(judge, claims_prompt(source, item["answer"]),
                                       max_tokens=max_tokens, temperature=0.2, trial=t)
                runs.append(parse_claims(rec["text"]) if rec else None)
            item["claims"][judge] = runs

    for item in items:
        targets = (any(flagged(r) for r in item["claims"].values())
                   or item["item_id"] in (SUSPECTED_FALSE_BLOCK, PROBE_ID, CONTROL_ITEM))
        item["grounding_runs"] = []
        if not targets or item["answer"] is None:
            continue
        source, instruction = generate_prompt_parts(item["question"], item["chunks"])
        for t in range(GROUNDING_TRIALS):
            rec = bedrock.apply_guardrail(GUARDRAIL_ID, GUARDRAIL_VERSION, source, instruction, item["answer"], trial=t)
            if rec:
                item["grounding_runs"].append(rec)
    return items


def analyse(items):
    rows = []
    for item in items:
        per_judge = {}
        for judge, runs in item["claims"].items():
            usable = [r for r in runs if r is not None]
            rates = [hallucination_rate(r) for r in usable]
            per_judge[judge] = {
                "usable_runs": len(usable), "parse_failures": len(runs) - len(usable),
                "claims_per_run": [len(r) for r in usable],
                "hallucination_rate": [x for x in rates],
                "flagged": flagged(runs),
                "unsupported_claims": sorted({c["claim"] for r in usable for c in r if c["label"] != "supported"}),
            }
        scores = [g["grounding"] for g in item["grounding_runs"] if g["grounding"] is not None]
        rows.append({
            "item_id": item["item_id"], "blocked": item["blocked"],
            "answer_is_regenerated_draft": item.get("answer_is_regenerated_draft", False),
            "answer": item["answer"], "stage3_grounding": item["stage3_grounding"],
            "claims": per_judge,
            "grounding_scores": scores,
            "grounding_range": (max(scores) - min(scores)) if scores else None,
            "grounding_passes": sum(1 for s in scores if s >= GROUNDING_THRESHOLD),
        })

    # Prediction 4a: an answer the claim check flags, whose grounding passed at least once.
    caught = [r for r in rows if any(j["flagged"] for j in r["claims"].values()) and r["grounding_passes"] >= 1]
    # Prediction 4b: grounding ranges by more than 0.2 across 5 runs on the same answer.
    wide = [r for r in rows if r["grounding_range"] is not None and r["grounding_range"] > 0.2]
    return {"items": rows,
            "prediction_4a_flagged_but_grounding_passed": [r["item_id"] for r in caught],
            "prediction_4b_grounding_range_gt_0_2": [r["item_id"] for r in wide],
            "grounding_ranges": {r["item_id"]: r["grounding_range"] for r in rows if r["grounding_range"] is not None}}


def print_report(result):
    short = {NOVA_MICRO: "nova-micro", GPT_OSS: "gpt-oss"}
    print(f"\n{'item':40s} {'shown':8s} {'judge':10s} {'claims':10s} {'unsupported share':22s} grounding x5")
    print("-" * 118)
    for r in result["items"]:
        g = " ".join(f"{s:.2f}" for s in r["grounding_scores"]) or "-"
        for i, (judge, j) in enumerate(r["claims"].items()):
            rates = " ".join(f"{x:.2f}" if x is not None else "-" for x in j["hallucination_rate"])
            label = ("BLOCKED" if r["blocked"] else "ok") if i == 0 else ""
            print(f"{(r['item_id'] if i == 0 else ''):40s} {label:8s} {short[judge]:10s} "
                  f"{str(j['claims_per_run']):10s} {rates:22s} {g if i == 0 else ''}"
                  f"{'  (parse failures: %d)' % j['parse_failures'] if j['parse_failures'] else ''}")
    print("\nUnsupported claims, for hand adjudication against the passages:")
    for r in result["items"]:
        for judge, j in r["claims"].items():
            for c in j["unsupported_claims"]:
                print(f"  {r['item_id']:38s} [{short[judge]}] {c}")
    print(f"\nPrediction 4a (claim check flags an answer whose grounding passed >= once): "
          f"{result['prediction_4a_flagged_but_grounding_passed'] or 'none'}")
    print(f"Prediction 4b (grounding range > 0.2 across 5 runs): {result['prediction_4b_grounding_range_gt_0_2'] or 'none'}")
    print("  ranges:", {k: round(v, 2) for k, v in result["grounding_ranges"].items()})


def main():
    parser = add_budget_args(argparse.ArgumentParser(description="Stage 6 claim checks vs grounding"), default_max_calls=150)
    args = parser.parse_args()
    bedrock = Bedrock(CACHE_DIR, max_calls=args.max_calls, dry_run=args.dry_run)
    generate = CachedLambda("generate", CACHE_DIR, max_calls=1, dry_run=args.dry_run)
    try:
        items = run(bedrock, generate)
    except BudgetExceeded as e:
        print(f"stopped: {e}")
        print(bedrock.summary())
        return 0
    print(bedrock.summary())
    print(generate.summary())
    if args.dry_run:
        return 0
    result = analyse(items)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print_report(result)
    print(f"\nwrote {os.path.relpath(OUT_PATH, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
