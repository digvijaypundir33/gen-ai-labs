"""
Compares a few Bedrock models on a small set of financial Q&A questions:
response quality (word overlap vs. ground truth), latency, and cost per
request. Writes model_evaluation_results.csv and model_selection_strategy.json.

Run:
    python benchmark_models.py

Requires the "ai-assistant" AWS CLI profile to be configured and boto3 +
pandas installed.
"""

import json
import time

import boto3
import pandas as pd

AWS_PROFILE = "ai-assistant"
AWS_REGION = "us-east-1"

# Verified against `aws bedrock list-foundation-models` / `list-inference-profiles`
# at the time this was written - re-check before trusting these months later.
MODELS = [
    "amazon.nova-micro-v1:0",
    "amazon.nova-lite-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
]

# Approx on-demand USD price per 1,000 tokens. VERIFY against the current
# Bedrock pricing page (https://aws.amazon.com/bedrock/pricing/) before
# trusting the cost numbers this script produces - pricing changes over time
# and these are illustrative, not authoritative.
PRICING_PER_1K_TOKENS = {
    "amazon.nova-micro-v1:0": {"input": 0.000035, "output": 0.00014},
    "amazon.nova-lite-v1:0": {"input": 0.00006, "output": 0.00024},
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.001, "output": 0.005},
}

TEST_CASES = [
    {
        "question": "What is a 401(k) retirement plan?",
        "ground_truth": (
            "A 401(k) is a tax-advantaged retirement savings plan offered by "
            "employers, allowing employees to contribute pre-tax income that "
            "grows tax-deferred until withdrawal."
        ),
    },
    {
        "question": "How does compound interest work?",
        "ground_truth": (
            "Compound interest is calculated on both the initial principal and "
            "the accumulated interest from previous periods, so your money "
            "grows faster over time compared to simple interest."
        ),
    },
    {
        "question": "What is the difference between APR and APY?",
        "ground_truth": (
            "APR (annual percentage rate) is the yearly cost of borrowing "
            "without compounding, while APY (annual percentage yield) includes "
            "the effect of compounding, so APY is typically higher than APR "
            "for the same nominal rate."
        ),
    },
    {
        "question": "What is a Roth IRA?",
        "ground_truth": (
            "A Roth IRA is a retirement account funded with after-tax dollars, "
            "where qualified withdrawals in retirement, including investment "
            "growth, are completely tax-free."
        ),
    },
    {
        "question": "What is an index fund?",
        "ground_truth": (
            "An index fund is a type of mutual fund or ETF designed to track "
            "the performance of a specific market index, offering "
            "diversification and typically lower fees than actively managed "
            "funds."
        ),
    },
]


def get_bedrock_client():
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return session.client("bedrock-runtime")


def invoke_model(client, model_id, prompt, max_tokens=500):
    """Call Converse and return output text + real latency/token/cost metrics."""
    start = time.time()
    try:
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.7, "topP": 0.9},
        )
    except Exception as e:  # noqa: BLE001 - benchmark records failures, doesn't crash
        return {"success": False, "error": str(e), "latency": time.time() - start}

    latency = time.time() - start
    output = response["output"]["message"]["content"][0]["text"]
    usage = response.get("usage", {})
    input_tokens = usage.get("inputTokens", 0)
    output_tokens = usage.get("outputTokens", 0)

    price = PRICING_PER_1K_TOKENS.get(model_id, {"input": 0, "output": 0})
    cost_usd = (input_tokens / 1000) * price["input"] + (output_tokens / 1000) * price["output"]

    return {
        "success": True,
        "output": output,
        "latency": latency,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }


def calculate_similarity(output, ground_truth):
    """Word-overlap similarity vs. ground truth (deliberately simple for v1)."""
    truth_words = set(ground_truth.lower().split())
    if not truth_words:
        return 0.0
    output_words = set(output.lower().split())
    common_words = output_words & truth_words
    return len(common_words) / len(truth_words)


def evaluate_models(client):
    rows = []
    for test_case in TEST_CASES:
        for model_id in MODELS:
            print(f"Evaluating {model_id} on: {test_case['question']}")
            result = invoke_model(client, model_id, test_case["question"])

            if result["success"]:
                rows.append({
                    "model_id": model_id,
                    "question": test_case["question"],
                    "output": result["output"],
                    "latency": result["latency"],
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "cost_usd": result["cost_usd"],
                    "similarity_score": calculate_similarity(result["output"], test_case["ground_truth"]),
                })
            else:
                rows.append({
                    "model_id": model_id,
                    "question": test_case["question"],
                    "error": result["error"],
                    "latency": result["latency"],
                })
    return pd.DataFrame(rows)


def summarize_models(results_df):
    """Per-model stats: success rate from all calls, quality/latency/cost from successes only."""
    success_rate = results_df.groupby("model_id")["output"].apply(
        lambda s: s.notna().mean()
    ).rename("success_rate")

    successes = results_df[results_df["output"].notna()]
    agg = successes.groupby("model_id").agg(
        latency=("latency", "mean"),
        similarity_score=("similarity_score", "mean"),
        cost_usd=("cost_usd", "mean"),
    )
    return success_rate.to_frame().join(agg, how="left").reset_index()


def create_model_selection_strategy(results_df):
    """Weighted score: 50% quality, 30% latency, 20% cost -> primary + fallbacks.

    Models with zero successful calls are excluded entirely (can't be a
    primary/fallback if they never returned a usable response) rather than
    being sorted based on their failure latency.
    """
    agg = summarize_models(results_df)
    agg = agg[agg["success_rate"] > 0].copy()

    agg["latency_score"] = 1 - (agg["latency"] / agg["latency"].max())
    max_cost = agg["cost_usd"].max()
    agg["cost_score"] = 1 - (agg["cost_usd"] / max_cost) if max_cost > 0 else 1.0

    agg["overall_score"] = (
        0.5 * agg["similarity_score"] + 0.3 * agg["latency_score"] + 0.2 * agg["cost_score"]
    )
    agg = agg.sort_values("overall_score", ascending=False)

    return {
        "primary_model": agg.iloc[0]["model_id"],
        "fallback_models": agg.iloc[1:]["model_id"].tolist(),
        "use_case_models": {},
        "model_scores": agg.to_dict(orient="records"),
    }


if __name__ == "__main__":
    bedrock_client = get_bedrock_client()

    results_df = evaluate_models(bedrock_client)
    results_df.to_csv("model_evaluation_results.csv", index=False)

    print("\nEvaluation summary (success rate; latency/quality/cost from successful calls only):")
    print(summarize_models(results_df).to_string(index=False))

    strategy = create_model_selection_strategy(results_df)
    with open("model_selection_strategy.json", "w") as f:
        json.dump(strategy, f, indent=2, default=str)

    print("\nModel selection strategy written to model_selection_strategy.json:")
    print(json.dumps(strategy, indent=2, default=str))
