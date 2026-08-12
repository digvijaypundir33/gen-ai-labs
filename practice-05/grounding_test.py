"""
Stage 7: run test_questions.py's 10 benign, corpus-grounded questions through
the live generate Lambda with contextual grounding enabled - none should be
blocked as ungrounded, since they're all verified-answerable from the corpus.
Also tests one deliberately hallucination-prone question (a specific detail
NOT present in any corpus doc) to confirm grounding actually catches
fabrication rather than just theoretically existing.
"""
import json
import sys

import boto3

sys.path.insert(0, "../practice-02")
from test_questions import TEST_QUESTIONS  # noqa: E402

lambda_client = boto3.client("lambda", region_name="us-east-1")

HALLUCINATION_PROBE = (
    "What is the exact millisecond value of Lambda SnapStart's cold start "
    "improvement, as stated in the documentation?"
)


def invoke(query):
    resp = lambda_client.invoke(
        FunctionName="generate",
        Payload=json.dumps({"query": query}),
    )
    payload = json.loads(resp["Payload"].read())
    body = json.loads(payload["body"])
    return body


def main():
    print("=== test_questions.py corpus (should all be grounded) ===")
    results = []
    for q in TEST_QUESTIONS:
        body = invoke(q["question"])
        results.append({"question": q["question"], "guardrail_action": body["guardrail_action"], "answer": body["answer"][:150]})
        print(f"{body['guardrail_action']:30} | {q['question'][:60]}")

    ungrounded = [r for r in results if "ungrounded" in r["guardrail_action"]]
    print(f"\n{len(ungrounded)}/{len(results)} benign questions blocked as ungrounded")

    print("\n=== Hallucination probe (detail not in any corpus doc) ===")
    body = invoke(HALLUCINATION_PROBE)
    print(f"guardrail_action: {body['guardrail_action']}")
    print(f"answer: {body['answer']}")

    with open("grounding_test_results.json", "w") as f:
        json.dump({
            "test_questions_results": results,
            "ungrounded_count": len(ungrounded),
            "hallucination_probe": {"query": HALLUCINATION_PROBE, "response": body},
        }, f, indent=2)


if __name__ == "__main__":
    main()
