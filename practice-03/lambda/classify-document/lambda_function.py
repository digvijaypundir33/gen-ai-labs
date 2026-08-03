import time

import boto3

bedrock_runtime = boto3.client("bedrock-runtime")

CLASSIFIER_MODEL = "amazon.nova-micro-v1:0"
VALID_TYPES = ["legal", "technical", "feedback", "general"]


def classify_type(document_text):
    prompt = (
        "Classify this document into exactly one of these categories: "
        "legal, technical, feedback, general. Respond with only the category word.\n\n"
        f"{document_text[:1000]}"
    )

    response = bedrock_runtime.converse(
        modelId=CLASSIFIER_MODEL,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 10, "temperature": 0.0},
    )
    raw = response["output"]["message"]["content"][0]["text"].strip().lower()

    for candidate in VALID_TYPES:
        if candidate in raw:
            return candidate
    return "general"


def classify_complexity(document_text):
    length = len(document_text)
    if length > 5000:
        return "high"
    if length > 1000:
        return "medium"
    return "low"


def lambda_handler(event, context):
    start_time = time.time()
    document_text = event["document"]

    document_type = classify_type(document_text)
    complexity = classify_complexity(document_text)

    return {
        "type": document_type,
        "complexity": complexity,
        "processing_time": time.time() - start_time,
    }
