"""
Stage 4d: compare Bedrock's managed scores with P01's hand-rolled one.

Reads the downloaded job outputs in results/managed-eval/ (no AWS calls) and
answers prediction 1: does managed Q&A accuracy (word-level F1 against the
one-line reference) rank Nova Micro and Nova Lite the way P01's word-overlap
score did?

P01's score is copied rather than imported, because benchmark_models.py pulls in
pandas at import time. It is word *recall*: the share of the reference's words
found anywhere in the answer. So it rewards long answers, while F1 also counts
every extra word against precision and penalises them. That makes each answer's
length the variable to report next to both scores.

Run:  .venv/bin/python compare_managed.py
"""

import glob
import json
import os
import sys

from evalkit.stats import summarize

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "results", "managed-eval")
SUMMARY_PATH = os.path.join(OUT_DIR, "qa-summary.json")
QA_JOBS = {"qa-micro": "amazon.nova-micro-v1:0", "qa-lite": "amazon.nova-lite-v1:0"}


def calculate_similarity(output, ground_truth):
    """Verbatim from series-1/practice-01/benchmark_models.py."""
    truth_words = set(ground_truth.lower().split())
    if not truth_words:
        return 0.0
    output_words = set(output.lower().split())
    common_words = output_words & truth_words
    return len(common_words) / len(truth_words)


def spearman(xs, ys):
    """Rank correlation (no tie correction; fine for a direction-of-effect check at n=10)."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for rank, i in enumerate(order):
            r[i] = rank
        return r
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1 - 6 * d2 / (n * (n * n - 1))


def load_job(job):
    paths = glob.glob(os.path.join(OUT_DIR, job, "**", "*_output.jsonl"), recursive=True)
    if not paths:
        return None
    records = []
    for path in paths:
        with open(path) as f:
            records += [json.loads(line) for line in f if line.strip()]
    return records


def main():
    summary = {}
    for job, model in QA_JOBS.items():
        records = load_job(job)
        if records is None:
            print(f"{job}: no output downloaded yet (managed_eval.py fetch {job})")
            continue
        items = []
        for r in records:
            scores = {s["metricName"]: s.get("result") for s in r["automatedEvaluationResult"]["scores"]}
            response = r["modelResponses"][0]["response"]
            ref = r["inputRecord"]["referenceResponse"]
            items.append({
                "category": r["inputRecord"].get("category"),
                "prompt": r["inputRecord"]["prompt"],
                "managed_f1": scores.get("Builtin.Accuracy"),
                "managed_robustness": scores.get("Builtin.Robustness"),
                "managed_toxicity": scores.get("Builtin.Toxicity"),
                "p01_overlap": calculate_similarity(response, ref),
                "response_words": len(response.split()),
            })
        f1 = [i["managed_f1"] for i in items if i["managed_f1"] is not None]
        overlap = [i["p01_overlap"] for i in items]
        words = [i["response_words"] for i in items]
        summary[job] = {
            "model": model,
            "n": len(items),
            "managed_f1": summarize(f1),
            "p01_overlap": summarize(overlap),
            "response_words": summarize(words),
            "spearman_f1_vs_length": spearman(f1, words[:len(f1)]) if len(f1) == len(words) else None,
            "spearman_overlap_vs_length": spearman(overlap, words),
            "items": items,
        }

    if not summary:
        return 1
    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)

    def fmt(s):
        return f"mean {s['mean']:.3f}  sd {s['stdev']:.3f}  [{s['min']:.2f}, {s['max']:.2f}]"

    print("Managed Q&A (bare model, no retrieval) vs. P01 word overlap, same 10 golden questions\n")
    for job, s in summary.items():
        print(f"{job}  ({s['model']}, n={s['n']})")
        print(f"   managed F1     {fmt(s['managed_f1'])}")
        print(f"   P01 overlap    {fmt(s['p01_overlap'])}")
        print(f"   answer length  mean {s['response_words']['mean']:.0f} words  "
              f"[{s['response_words']['min']}, {s['response_words']['max']}]")
        print(f"   rank corr. with length:  F1 {s['spearman_f1_vs_length']:+.2f}   "
              f"overlap {s['spearman_overlap_vs_length']:+.2f}")
        for key in ("managed_robustness", "managed_toxicity"):
            vals = [i[key] for i in s["items"] if i[key] is not None]
            if vals:
                print(f"   {key[8:]:14s} {fmt(summarize(vals))}")
        print()

    if len(summary) == 2:
        m, l = summary["qa-micro"], summary["qa-lite"]
        for key, label in (("managed_f1", "managed F1"), ("p01_overlap", "P01 overlap")):
            gap = m[key]["mean"] - l[key]["mean"]
            noise = max(m[key]["stdev"], l[key]["stdev"])
            leader = "micro" if gap > 0 else "lite"
            verdict = "inside the noise" if abs(gap) <= noise else "clear"
            print(f"{label:12s}: {leader} leads by {abs(gap):.3f}; larger per-item sd {noise:.3f} -> {verdict}")
    print(f"\nwrote {os.path.relpath(SUMMARY_PATH, HERE)}")
    judge_summary()
    return 0


def judge_summary():
    """4c: the managed RAG judge on generate's real answers, next to what Stage 3 recorded."""
    records = load_job("judge")
    if records is None:
        print("\njudge: no output downloaded yet (managed_eval.py fetch judge)")
        return
    with open(os.path.join(HERE, "results", "responses.jsonl")) as f:
        stage3 = {r["question"]: r for r in map(json.loads, f) if r["trial"] == 0}

    rows = []
    for rec in records:
        turn = rec["conversationTurns"][0]
        question = turn["inputRecord"]["prompt"]["content"][0]["text"]
        s3 = stage3[question]
        scores = {m["metricName"].replace("Builtin.", ""): float(m["result"]) if m.get("result") is not None else None
                  for m in turn["results"]}
        explanations = {m["metricName"].replace("Builtin.", ""): (m.get("evaluatorDetails") or [{}])[0].get("explanation")
                        for m in turn["results"]}
        rows.append({"item_id": s3["item_id"], "blocked": s3["guardrail_action"] != "none",
                     "grounding_score": s3["grounding_score"], "scores": scores, "explanations": explanations})
    rows.sort(key=lambda r: r["item_id"])
    with open(os.path.join(OUT_DIR, "judge-summary.json"), "w") as f:
        json.dump(rows, f, indent=2)

    metrics = sorted({m for r in rows for m in r["scores"]})
    print("\nManaged RAG judge (Nova Micro) on generate's real answers, trial 0\n")
    print(f"{'item':42s} {'blocked':>7s} {'grnd':>5s} " + " ".join(f"{m[:11]:>11s}" for m in metrics))
    print("-" * (57 + 12 * len(metrics)))
    for r in rows:
        cells = " ".join(f"{r['scores'][m]:11.2f}" if r["scores"].get(m) is not None else f"{'-':>11s}" for m in metrics)
        print(f"{r['item_id']:42s} {('yes' if r['blocked'] else ''):>7s} {r['grounding_score'] or 0:5.2f} {cells}")
    for m in metrics:
        vals = [r["scores"][m] for r in rows if r["scores"].get(m) is not None]
        print(f"   {m:14s} mean {summarize(vals)['mean']:.2f} over {len(vals)} items")


if __name__ == "__main__":
    sys.exit(main())
