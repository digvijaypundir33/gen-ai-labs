import json

import boto3

bedrock_runtime = boto3.client("bedrock-runtime")

EXPAND_MODEL = "amazon.nova-lite-v1:0"


def lambda_handler(event, context):
    query = event["query"]

    response = bedrock_runtime.converse(
        modelId=EXPAND_MODEL,
        messages=[{
            "role": "user",
            "content": [{"text": (
                "Generate 3 alternative phrasings of this question that use different "
                "vocabulary but ask the same thing - this is for a search system, so the "
                "goal is to catch documents that use different wording than the question. "
                'Respond with ONLY a JSON array of 3 strings, no other text.\n\n'
                f"Question: {query}"
            )}],
        }],
        inferenceConfig={"maxTokens": 300, "temperature": 0.3},
    )
    output = response["output"]["message"]["content"][0]["text"]

    try:
        alternates = json.loads(output[output.index("["):output.rindex("]") + 1])
        alternates = [a for a in alternates if isinstance(a, str)]
    except (ValueError, json.JSONDecodeError):
        alternates = []  # fail toward just using the original query alone

    return {
        "query": query,
        "expandedQueries": [query] + alternates,
    }
