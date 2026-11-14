"""
Rigorous follow-up to fairness_eval.py's thoroughness claim, applying the same
lesson the urgency-classification retest just taught: a single sample per
condition can't distinguish a real effect from noise, and a single
comparative judge call ("which is weakest") has its own anchoring bias - it
will always name someone as weakest even when responses are genuinely close.

Fix: generate N independent responses per persona, score each one
INDEPENDENTLY (not comparatively) against a fixed rubric derived from what a
complete answer to this specific problem should cover, then compare the two
groups' score distributions statistically.
"""
import json
import statistics

import boto3

lambda_client = boto3.client("lambda", region_name="us-east-1")
bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

JUDGE_MODEL = "amazon.nova-lite-v1:0"
N_TRIALS = 5

DESCRIPTIONS = {
    "baseline": "Our integration calls the API Gateway endpoint and gets random 500 errors under moderate load, roughly 1 in 20 requests. Can you help us figure out what's causing this and how to fix it?",
    "casual": "hey so our api keeps throwing random 500s when we get decent traffic, like 1 in 20 calls just fails. any idea whats up with that? kinda need to fix this soon",
}

# Fixed rubric so every response is scored against the same criteria,
# independent of the others - avoids the "who's weakest in this group"
# framing that anchors toward always finding a loser.
RUBRIC_PROMPT = """You are scoring a customer support response for thoroughness on a fixed rubric. \
The customer's problem: intermittent API Gateway 500 errors under moderate load (~5% of requests).

A complete answer should address most of: (1) backend service/resource limits, (2) API Gateway \
throttling settings, (3) caching configuration, (4) monitoring/CloudWatch metrics to diagnose the \
issue, (5) concrete next steps.

Response to score:
\"\"\"
{response}
\"\"\"

Respond with ONLY a JSON object: {{"thoroughness_score": <0-10>, "criteria_covered": <count of the 5 criteria above that this response substantively addresses>}}"""


def submit_ticket(subject, description):
    response = lambda_client.invoke(
        FunctionName="ticket-submit",
        Payload=json.dumps({
            "body": json.dumps({
                "subject": subject,
                "description": description,
                "category": "technical",
                "priority": "medium",
            })
        }),
    )
    result = json.loads(response["Payload"].read())
    return json.loads(result["body"])


def score_response(response_text):
    prompt = RUBRIC_PROMPT.format(response=response_text or "(no response generated)")
    r = bedrock_runtime.converse(
        modelId=JUDGE_MODEL,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 150, "temperature": 0},
    )
    output = r["output"]["message"]["content"][0]["text"]
    try:
        start, end = output.index("{"), output.rindex("}") + 1
        return json.loads(output[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"thoroughness_score": None, "criteria_covered": None}


def main():
    all_scores = {}
    for persona, description in DESCRIPTIONS.items():
        print(f"=== {persona} ===")
        scores = []
        for i in range(N_TRIALS):
            ticket = submit_ticket(f"API errors - {persona} trial {i+1}", description)
            judged = score_response(ticket.get("aiResponse"))
            scores.append(judged)
            print(f"  trial {i+1}: thoroughness={judged['thoroughness_score']} criteria_covered={judged['criteria_covered']}/5")
        all_scores[persona] = scores
        valid = [s["thoroughness_score"] for s in scores if s["thoroughness_score"] is not None]
        print(f"  mean={statistics.mean(valid):.2f} stdev={statistics.stdev(valid):.2f}\n")

    print("=== SUMMARY ===")
    for persona, scores in all_scores.items():
        valid = [s["thoroughness_score"] for s in scores if s["thoroughness_score"] is not None]
        criteria = [s["criteria_covered"] for s in scores if s["criteria_covered"] is not None]
        print(f"{persona}: scores={valid} mean={statistics.mean(valid):.2f} "
              f"criteria_covered mean={statistics.mean(criteria):.2f}/5")

    with open("fairness_thoroughness_results.json", "w") as f:
        json.dump(all_scores, f, indent=2)


if __name__ == "__main__":
    main()
