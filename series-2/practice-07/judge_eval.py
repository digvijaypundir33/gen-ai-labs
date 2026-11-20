"""
Stage 5: the assignment's single-run judge vs. an independent-rubric judge run
five times, on the same 10 `generate` answers Stage 4's managed judge scored.

Arm A reproduces the assignment's Module 1 judge as written:
- one combined prompt for all six dimensions, on a 1-10 scale;
- temperature 0.2, max 1000 tokens;
- the reference answer passed as "reference information".

Its defects are fixed rather than copied: the leaked "Step 2:" text, the module-level
_extract_json_from_text called through self, and the dead claude-3-sonnet ID, with
Nova Micro standing in. It runs six times per answer. Trial 0 is the single run the
assignment would report; trials 1-5 are the five-run distribution. Running trial 0 as
its own call is what lets prediction 3 ask whether it falls outside the five-run range.
It can't, by definition, if it's one of the five.

Arm B scores each dimension with its own anchored 1-5 rubric and a one-line JSON
verdict, five times, with two judge families: Nova Micro and gpt-oss-120b.
Completeness is judged against the question, not the reference. Stage 4 showed a
reference broader than its question (q09) makes reference-based completeness penalise
a right answer.

Both arms see question, answer and reference, not the retrieved passages. Grounding is
Stage 6's job, and leaving passages out keeps each call ~10x cheaper.

Run:  .venv/bin/python judge_eval.py --dry-run
      .venv/bin/python judge_eval.py --items 1           (pilot: both arms, both judges, one answer)
      .venv/bin/python judge_eval.py
"""

import argparse
import json
import os
import re
import statistics
import sys

from evalkit.bedrock import Bedrock, BudgetExceeded, add_budget_args
from evalkit.stats import summarize

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "results", "cache")
RESPONSES_PATH = os.path.join(HERE, "results", "responses.jsonl")
MANAGED_PATH = os.path.join(HERE, "results", "managed-eval", "judge-summary.json")
OUT_PATH = os.path.join(HERE, "results", "judge-eval.json")

DIMENSIONS = ["relevance", "factual_accuracy", "consistency", "fluency", "helpfulness", "completeness"]
NOVA_MICRO = "amazon.nova-micro-v1:0"
GPT_OSS = "openai.gpt-oss-120b-1:0"
JUDGES_B = [NOVA_MICRO, GPT_OSS]
TEMPERATURE = 0.2  # the assignment's setting, used in both arms so the arms differ only in method
ARM_A_TRIALS = 6   # trial 0 = the single run; trials 1-5 = the five-run distribution
ARM_B_TRIALS = 5
# gpt-oss spends output tokens on reasoning before its answer; too low a ceiling truncates the verdict.
ARM_B_MAX_TOKENS = {NOVA_MICRO: 150, GPT_OSS: 1000}


# ---- Arm A: the assignment's prompt (practice-07.md lines 132-212), defects fixed ----

def assignment_prompt(query, response, reference_info):
    prompt = f"""You are an expert evaluator for foundation model outputs. Please evaluate the following response to a user query across multiple quality dimensions.

User Query:
{query}

Model Response:
{response}
"""
    if reference_info:
        prompt += f"""
Reference Information (use this to verify factual accuracy):
{reference_info}
"""
    prompt += """
Please evaluate the response on the following dimensions, rating each on a scale from 1 to 10 where 1 is the lowest quality and 10 is the highest quality:

1. Relevance: How relevant is the response to the query?
2. Factual Accuracy: How factually accurate is the information in the response?
3. Consistency: How internally consistent is the response?
4. Fluency: How well-written and fluent is the response?
5. Helpfulness: How helpful is the response in addressing the user's needs?
6. Completeness: How complete is the response in addressing all aspects of the query?

For each dimension, please provide:
- A numerical score (1-10)
- A brief explanation of your rating
- Specific examples from the response that support your rating
- Suggestions for improvement

Finally, calculate an overall quality score as a weighted average of the individual scores, with Relevance, Factual Accuracy, and Helpfulness weighted twice as much as the other dimensions.

Format your response as a JSON object with the following structure:
```json
{
  "dimensions": {
    "relevance": {"score": <score>, "explanation": "<explanation>", "examples": "<examples>", "suggestions": "<suggestions>"},
    "factual_accuracy": {"score": <score>, "explanation": "<explanation>", "examples": "<examples>", "suggestions": "<suggestions>"},
    "consistency": {"score": <score>, "explanation": "<explanation>", "examples": "<examples>", "suggestions": "<suggestions>"},
    "fluency": {"score": <score>, "explanation": "<explanation>", "examples": "<examples>", "suggestions": "<suggestions>"},
    "helpfulness": {"score": <score>, "explanation": "<explanation>", "examples": "<examples>", "suggestions": "<suggestions>"},
    "completeness": {"score": <score>, "explanation": "<explanation>", "examples": "<examples>", "suggestions": "<suggestions>"}
  },
  "overall_score": <overall_score>,
  "summary": "<brief summary of evaluation>",
  "key_strengths": ["<strength1>", "<strength2>", ...],
  "key_weaknesses": ["<weakness1>", "<weakness2>", ...],
  "improvement_priority": "<dimension that most needs improvement>"
}
```
Provide only the JSON response without any additional text."""
    return prompt


# ---- Arm B: one anchored rubric per dimension ----

RUBRICS = {
    "relevance": "Does the response address the question that was asked? "
                 "5 = directly answers it; 3 = partly on-topic or padded with unrelated material; "
                 "1 = off-topic, or a refusal that answers nothing.",
    "factual_accuracy": "Are the response's facts correct, judged against the reference answer? "
                        "5 = every fact agrees with the reference and nothing is false; 3 = mostly right with a "
                        "minor error or an unsupported extra claim; 1 = contradicts the reference, or states no facts.",
    "consistency": "Is the response internally consistent? "
                   "5 = no part contradicts another; 3 = minor tension between parts; 1 = contradicts itself.",
    "fluency": "Is the response clear, well-formed English? "
               "5 = clear and well-structured; 3 = understandable but awkward; 1 = hard to follow.",
    "helpfulness": "Would this response help the person who asked? "
                   "5 = they can act on it immediately; 3 = useful but they'd need more; 1 = no help.",
    "completeness": "Does the response cover every part of the question asked (not everything the reference "
                    "mentions)? 5 = all parts; 3 = some parts missing; 1 = none.",
}


def rubric_prompt(dimension, query, response, reference):
    return f"""You are grading one quality dimension of an answer from a technical-documentation assistant.

Dimension: {dimension.replace('_', ' ')}
Rubric: {RUBRICS[dimension]}

Question:
{query}

Reference answer:
{reference}

Answer to grade:
{response}

Reply with only a JSON object, no other text: {{"score": <integer 1-5>, "reason": "<one sentence>"}}"""


# ---- parsing ----

def extract_json(text):
    """First JSON object in a reply (bare, or inside a ```json fence), or None."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None


def score_in_range(value, lo, hi):
    """An integer score in [lo, hi], or None. Anything else is a parse failure, counted, never guessed."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def parse_assignment(text):
    data = extract_json(text) or {}
    dims = data.get("dimensions") or {}
    return {d: score_in_range((dims.get(d) or {}).get("score"), 1, 10) for d in DIMENSIONS}


def parse_rubric(text):
    return score_in_range((extract_json(text) or {}).get("score"), 1, 5)


# ---- run ----

def load_answers():
    with open(RESPONSES_PATH) as f:
        rows = [r for r in map(json.loads, f) if r["trial"] == 0]
    return sorted(rows, key=lambda r: r["item_id"])


def run(bedrock, answers):
    arm_a, arm_b = [], []
    for row in answers:
        for t in range(ARM_A_TRIALS):
            rec = bedrock.converse(NOVA_MICRO, assignment_prompt(row["question"], row["answer"], row["ground_truth"]),
                                   max_tokens=1000, temperature=TEMPERATURE, trial=t)
            if rec:
                arm_a.append({"item_id": row["item_id"], "trial": t, "scores": parse_assignment(rec["text"]),
                              "usage": rec["usage"]})
    for row in answers:
        for judge in JUDGES_B:
            for dim in DIMENSIONS:
                for t in range(ARM_B_TRIALS):
                    rec = bedrock.converse(judge, rubric_prompt(dim, row["question"], row["answer"], row["ground_truth"]),
                                           max_tokens=ARM_B_MAX_TOKENS[judge], temperature=TEMPERATURE, trial=t)
                    if rec:
                        arm_b.append({"item_id": row["item_id"], "judge": judge, "dimension": dim, "trial": t,
                                      "score": parse_rubric(rec["text"]), "stop_reason": rec["stop_reason"],
                                      "usage": rec["usage"]})
    return arm_a, arm_b


# ---- analysis (pure, offline) ----

def analyse(answers, arm_a, arm_b, managed):
    out = {"parse_failures": {}, "prediction_3": {}, "prediction_2": {}, "dimension_means": {}, "efficiency": []}

    out["parse_failures"]["arm_a"] = sum(1 for r in arm_a for d in DIMENSIONS if r["scores"][d] is None)
    out["parse_failures"]["arm_a_cells"] = len(arm_a) * len(DIMENSIONS)
    for judge in JUDGES_B:
        mine = [r for r in arm_b if r["judge"] == judge]
        out["parse_failures"][judge] = {"failed": sum(1 for r in mine if r["score"] is None), "calls": len(mine),
                                        "truncated": sum(1 for r in mine if r["stop_reason"] == "max_tokens")}

    # 3a: share of (item, dimension) cells where the five runs spread by >= 1 point.
    cells = {}
    for r in arm_b:
        if r["score"] is not None:
            cells.setdefault((r["judge"], r["item_id"], r["dimension"]), []).append(r["score"])
    spread = {}
    for judge in JUDGES_B:
        mine = {k: v for k, v in cells.items() if k[0] == judge}
        varying = sum(1 for v in mine.values() if max(v) - min(v) >= 1)
        spread[judge] = {"cells": len(mine), "cells_spread_ge_1": varying,
                         "share": varying / len(mine) if mine else None}
    out["prediction_3"]["a_run_to_run_spread"] = spread

    # 3b: the assignment's single run (trial 0) against its own five-run range (trials 1-5).
    outside, compared, examples = 0, 0, []
    for row in answers:
        single = next((r for r in arm_a if r["item_id"] == row["item_id"] and r["trial"] == 0), None)
        five = [r for r in arm_a if r["item_id"] == row["item_id"] and r["trial"] >= 1]
        if not single:
            continue
        for d in DIMENSIONS:
            dist = [r["scores"][d] for r in five if r["scores"][d] is not None]
            s = single["scores"][d]
            if s is None or not dist:
                continue
            compared += 1
            if s < min(dist) or s > max(dist):
                outside += 1
                examples.append({"item_id": row["item_id"], "dimension": d, "single": s, "five_run": dist})
    out["prediction_3"]["b_single_outside_five_run_range"] = {"cells": compared, "outside": outside,
                                                              "examples": examples}

    # 3c: between-judge gap vs. within-judge spread, cell by cell.
    gaps = []
    for row in answers:
        for d in DIMENSIONS:
            a = cells.get((NOVA_MICRO, row["item_id"], d), [])
            b = cells.get((GPT_OSS, row["item_id"], d), [])
            if len(a) >= 2 and len(b) >= 2:
                gaps.append({"item_id": row["item_id"], "dimension": d,
                             "gap": abs(statistics.mean(a) - statistics.mean(b)),
                             "within": max(statistics.stdev(a), statistics.stdev(b), max(a) - min(a), max(b) - min(b))})
    bigger = sum(1 for g in gaps if g["gap"] > g["within"])
    out["prediction_3"]["c_between_vs_within"] = {
        "cells": len(gaps), "cells_gap_exceeds_within_spread": bigger,
        "mean_gap": statistics.mean(g["gap"] for g in gaps) if gaps else None,
        "mean_within": statistics.mean(g["within"] for g in gaps) if gaps else None,
    }

    for judge in JUDGES_B:
        out["dimension_means"][judge] = {
            d: summarize([s for (j, _, dd), v in cells.items() if j == judge and dd == d for s in v]) for d in DIMENSIONS}

    # Prediction 2: managed Correctness vs. my factual_accuracy, pass/fail.
    # Pass = 4+ of 5 (median of five Nova Micro runs); the managed equivalent on its 0-1 scale is >= 0.75.
    managed_by_item = {m["item_id"]: m["scores"].get("Correctness") for m in managed}
    agree, compared2, rows2 = 0, 0, []
    for row in answers:
        mine = cells.get((NOVA_MICRO, row["item_id"], "factual_accuracy"), [])
        m = managed_by_item.get(row["item_id"])
        if not mine or m is None:
            rows2.append({"item_id": row["item_id"], "managed": m, "mine_median": None, "note": "not comparable"})
            continue
        compared2 += 1
        mine_pass = statistics.median(mine) >= 4
        managed_pass = m >= 0.75
        agree += mine_pass == managed_pass
        rows2.append({"item_id": row["item_id"], "managed": m, "mine_median": statistics.median(mine),
                      "agree": mine_pass == managed_pass})
    out["prediction_2"] = {"compared": compared2, "agree": agree, "items": rows2}

    # Module 2 efficiency, from generate's real usage and latency. Blocked answers report 0 tokens,
    # so quality-per-token is undefined for them and they're excluded, not divided by zero.
    for row in answers:
        out_tokens = (row["usage"] or {}).get("outputTokens") or 0
        scores = [s for (j, i, _), v in cells.items() if j == NOVA_MICRO and i == row["item_id"] for s in v]
        if not scores:
            continue
        quality = statistics.mean(scores)
        out["efficiency"].append({
            "item_id": row["item_id"], "blocked": row["guardrail_action"] != "none", "quality_1to5": quality,
            "output_tokens": out_tokens, "latency_s": row["latency_ms"] / 1000,
            "quality_per_100_tokens": quality / out_tokens * 100 if out_tokens else None,
            "quality_per_second": quality / (row["latency_ms"] / 1000),
        })
    return out


def print_report(result):
    pf = result["parse_failures"]
    print("\nParse failures (counted, never guessed):")
    print(f"  arm A (assignment): {pf['arm_a']}/{pf['arm_a_cells']} dimension scores")
    for j in JUDGES_B:
        print(f"  arm B {j}: {pf[j]['failed']}/{pf[j]['calls']} calls  (truncated at max_tokens: {pf[j]['truncated']})")

    p3 = result["prediction_3"]
    print("\nPrediction 3a: share of (item, dimension) cells whose 5 runs spread by >= 1 point (predicted >= 20%)")
    for j, s in p3["a_run_to_run_spread"].items():
        if s["cells"]:
            print(f"  {j:28s} {s['cells_spread_ge_1']}/{s['cells']} = {s['share']:.0%}")
    b = p3["b_single_outside_five_run_range"]
    print(f"\nPrediction 3b: assignment single run outside its own 5-run range: {b['outside']}/{b['cells']} cells")
    for e in b["examples"][:6]:
        print(f"  {e['item_id']:40s} {e['dimension']:17s} single {e['single']:g}  five-run {e['five_run']}")
    c = p3["c_between_vs_within"]
    if c["cells"]:
        print(f"\nPrediction 3c: between-judge gap exceeds within-judge spread in {c['cells_gap_exceeds_within_spread']}"
              f"/{c['cells']} cells  (mean gap {c['mean_gap']:.2f} vs mean within-spread {c['mean_within']:.2f})")

    print("\nDimension means, arm B (1-5):")
    print(f"  {'dimension':18s} " + "  ".join(f"{j.split('.')[1][:14]:>22s}" for j in JUDGES_B))
    for d in DIMENSIONS:
        cols = []
        for j in JUDGES_B:
            s = result["dimension_means"][j][d]
            cols.append(f"{s['mean']:.2f} (sd {s['stdev']:.2f}, n={s['n']})" if s["n"] else "-")
        print(f"  {d:18s} " + "  ".join(f"{c:>22s}" for c in cols))

    p2 = result["prediction_2"]
    print(f"\nPrediction 2: managed Correctness vs my factual_accuracy, pass/fail agreement "
          f"{p2['agree']}/{p2['compared']} (predicted >= 8/10)")
    for r in p2["items"]:
        if not r.get("agree", True) or r.get("note"):
            print(f"  {r['item_id']:40s} managed {r['managed']}  mine(median) {r['mine_median']}  {r.get('note', 'DISAGREE')}")

    print("\nEfficiency (Module 2), from generate's real usage; blocked answers have no token count:")
    for e in result["efficiency"]:
        qpt = f"{e['quality_per_100_tokens']:.2f}" if e["quality_per_100_tokens"] is not None else "n/a (blocked)"
        print(f"  {e['item_id']:40s} quality {e['quality_1to5']:.2f}  tokens {e['output_tokens']:4d}  "
              f"per-100-tokens {qpt:>14s}  per-second {e['quality_per_second']:.2f}")


def main():
    parser = add_budget_args(argparse.ArgumentParser(description="Stage 5 judge comparison"), default_max_calls=660)
    parser.add_argument("--items", type=int, default=None,
                        help="judge only the first N answers (a pilot covering both arms and both judges)")
    args = parser.parse_args()

    answers = load_answers()[:args.items]
    bedrock = Bedrock(CACHE_DIR, max_calls=args.max_calls, dry_run=args.dry_run)
    try:
        arm_a, arm_b = run(bedrock, answers)
    except BudgetExceeded as e:
        print(f"stopped: {e}")
        print(bedrock.summary())
        return 0
    print(bedrock.summary())
    if args.dry_run:
        return 0

    with open(MANAGED_PATH) as f:
        managed = json.load(f)
    result = analyse(answers, arm_a, arm_b, managed)
    with open(OUT_PATH, "w") as f:
        json.dump({"arm_a": arm_a, "arm_b": arm_b, "analysis": result}, f, indent=2)
    print_report(result)
    print(f"\nwrote {os.path.relpath(OUT_PATH, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
