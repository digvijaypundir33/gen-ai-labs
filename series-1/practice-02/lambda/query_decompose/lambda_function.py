import json

import boto3

bedrock_runtime = boto3.client("bedrock-runtime")

DECOMPOSE_MODEL = "amazon.nova-lite-v1:0"


def lambda_handler(event, context):
    query = event["query"]

    response = bedrock_runtime.converse(
        modelId=DECOMPOSE_MODEL,
        messages=[{
            "role": "user",
            "content": [{"text": (
                "Break this question down into independent sub-questions that, if each "
                "answered separately, would together fully answer the original question. "
                "If the question is already simple and doesn't need breaking down, return "
                "a single-item array containing just the original question. "
                'Respond with ONLY a JSON array of strings, no other text.\n\n'
                f"Question: {query}"
            )}],
        }],
        inferenceConfig={"maxTokens": 400, "temperature": 0},
    )
    output = response["output"]["message"]["content"][0]["text"]

    try:
        sub_queries = json.loads(output[output.index("["):output.rindex("]") + 1])
        sub_queries = [q for q in sub_queries if isinstance(q, str)]
    except (ValueError, json.JSONDecodeError):
        sub_queries = []

    if not sub_queries:
        sub_queries = [query]  # fail toward treating it as a single question

    return {
        "query": query,
        "subQueries": sub_queries,
    }
