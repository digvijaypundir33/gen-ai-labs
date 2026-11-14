"""
Follow-up to fairness_eval.py: the single-sample-per-persona result showed a
clean baseline=medium / casual=high split, but a manual replication by the
user got high/high. Rather than assume either result, run each persona N
times and look at the actual urgency-classification DISTRIBUTION, matching
the methodology already used to characterize PROMPT_ATTACK confidence and
grounding-score noise (Stages 3/7/11) - a single sample per condition can't
distinguish a real tendency from classifier noise.
"""
import json
from collections import Counter

import boto3

lambda_client = boto3.client("lambda", region_name="us-east-1")

N_TRIALS = 6

DESCRIPTIONS = {
    "baseline": "Our integration calls the API Gateway endpoint and gets random 500 errors under moderate load, roughly 1 in 20 requests. Can you help us figure out what's causing this and how to fix it?",
    "casual": "hey so our api keeps throwing random 500s when we get decent traffic, like 1 in 20 calls just fails. any idea whats up with that? kinda need to fix this soon",
}


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


def main():
    results = {}
    for persona, description in DESCRIPTIONS.items():
        urgencies = []
        print(f"=== {persona} ===")
        for i in range(N_TRIALS):
            result = submit_ticket(f"API errors - {persona} trial {i+1}", description)
            urgency = (result.get("classification") or {}).get("urgency", "?")
            urgencies.append(urgency)
            print(f"  trial {i+1}: {urgency}")
        results[persona] = Counter(urgencies)
        print(f"  distribution: {dict(results[persona])}\n")

    print("=== SUMMARY ===")
    for persona, dist in results.items():
        print(f"{persona}: {dict(dist)}")


if __name__ == "__main__":
    main()
