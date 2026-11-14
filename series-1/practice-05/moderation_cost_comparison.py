"""
Stage 6: cost/latency comparison for the tiered moderation workflow vs a
hypothetical "always run the LLM moderator" baseline, using the same 30-prompt
corpus from Stage 3 (guardrail_eval.py) for an apples-to-apples comparison.

IMPORTANT CAVEAT (found while building this, not assumed going in): the cheap
tier's risk scoring (Comprehend sentiment + PII, exactly as specified in the
reference assignment) is not a safe stand-in for content-safety classification.
2 of 5 adversarial categories in this corpus - calmly-phrased violence content
and topic-based policy violations (financial/legal advice) - score LOW risk
and skip the expensive tier entirely, because sentiment analysis measures
emotional tone, not harm. The same 5 categories are caught 100% by the
Bedrock Guardrail built in Stages 1-3. This script still measures the cost
delta the assignment asks for, but the tiered design should not be read as
"as safe as the Guardrail, but cheaper" - see the write-up for the full verdict.
"""
import json
import sys
import time

import boto3

sys.path.insert(0, ".")
from guardrail_eval import ALL_PROMPTS  # noqa: E402

lambda_client = boto3.client("lambda", region_name="us-east-1")

# amazon.nova-lite-v1:0 pricing (per 1K tokens) - moderation-llm-check's prompt
# is short (~150 input tokens + up to 300 output tokens per the maxTokens cap).
NOVA_LITE_INPUT_PER_1K = 0.00006
NOVA_LITE_OUTPUT_PER_1K = 0.00024
EST_INPUT_TOKENS = 150
EST_OUTPUT_TOKENS = 100  # actual moderation JSON responses are short


def estimate_llm_call_cost():
    return (EST_INPUT_TOKENS / 1000 * NOVA_LITE_INPUT_PER_1K) + (EST_OUTPUT_TOKENS / 1000 * NOVA_LITE_OUTPUT_PER_1K)


def main():
    results = []
    for item in ALL_PROMPTS:
        start = time.time()
        resp = lambda_client.invoke(
            FunctionName="moderation-risk-check",
            Payload=json.dumps({"input": item["prompt"]}),
        )
        elapsed = time.time() - start
        result = json.loads(resp["Payload"].read())
        escalates = result["risk_level"] in ("MEDIUM", "HIGH")
        results.append({
            "category": item["category"],
            "should_block": item["should_block"],
            "risk_level": result["risk_level"],
            "escalates_to_llm": escalates,
            "comprehend_latency_s": round(elapsed, 3),
        })
        print(f"{item['category']:25} risk={result['risk_level']:6} escalates={escalates} "
              f"should_block={item['should_block']}")

    total = len(results)
    escalated = sum(1 for r in results if r["escalates_to_llm"])
    skipped = total - escalated

    tiered_llm_calls = escalated
    baseline_llm_calls = total  # "always moderate with the LLM"

    llm_call_cost = estimate_llm_call_cost()
    tiered_cost = tiered_llm_calls * llm_call_cost
    baseline_cost = baseline_llm_calls * llm_call_cost
    avg_comprehend_latency = sum(r["comprehend_latency_s"] for r in results) / total

    # Safety gap: adversarial prompts (should_block=True) that got skipped
    missed_adversarial = [r for r in results if r["should_block"] and not r["escalates_to_llm"]]

    print(f"\n=== COST/LATENCY DELTA (n={total}) ===")
    print(f"Tiered workflow: {tiered_llm_calls}/{total} escalated to LLM ({skipped} resolved on Comprehend alone)")
    print(f"Estimated LLM cost - tiered:   ${tiered_cost:.6f}")
    print(f"Estimated LLM cost - baseline: ${baseline_cost:.6f} (always-LLM)")
    print(f"Cost reduction: {(1 - tiered_cost / baseline_cost) * 100:.0f}%")
    print(f"Avg Comprehend-only latency: {avg_comprehend_latency:.3f}s (vs an LLM call, typically 0.5-2s)")

    print(f"\n=== SAFETY GAP (the caveat) ===")
    print(f"Adversarial prompts that skipped the LLM tier entirely: {len(missed_adversarial)}/{sum(1 for r in results if r['should_block'])}")
    for r in missed_adversarial:
        print(f"  - [{r['category']}] risk_level={r['risk_level']} (should have escalated)")

    with open("moderation_cost_comparison_results.json", "w") as f:
        json.dump({
            "results": results,
            "summary": {
                "total": total,
                "escalated_to_llm": escalated,
                "skipped_llm": skipped,
                "tiered_cost_usd": tiered_cost,
                "baseline_cost_usd": baseline_cost,
                "cost_reduction_pct": (1 - tiered_cost / baseline_cost) * 100,
                "missed_adversarial_count": len(missed_adversarial),
                "missed_adversarial_categories": [r["category"] for r in missed_adversarial],
            },
        }, f, indent=2)


if __name__ == "__main__":
    main()
