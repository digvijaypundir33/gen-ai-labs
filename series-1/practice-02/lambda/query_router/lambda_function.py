import hashlib
import json
import time

import boto3

bedrock_runtime = boto3.client("bedrock-runtime")
comprehend = boto3.client("comprehend")
dynamodb = boto3.resource("dynamodb")
cache_table = dynamodb.Table("RagQueryCache")

CACHE_TTL_SECONDS = 3600
CLASSIFY_MODEL = "amazon.nova-lite-v1:0"
MIN_PII_SCORE = 0.5


def compute_query_hash(query):
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()


def mask_pii(text):
    """The cached result blob embeds the raw query text verbatim. Bedrock's
    Guardrail input-side check (generate Lambda) never actually redacts PII
    from the query - confirmed live, sensitive-information scanning only
    fires on the OUTPUT side - so without this, PII typed into a query would
    sit in RagQueryCache in plaintext for the cache's full TTL.
    """
    if not text:
        return text
    entities = comprehend.detect_pii_entities(Text=text, LanguageCode="en")["Entities"]
    entities = [e for e in entities if e["Score"] >= MIN_PII_SCORE]
    if not entities:
        return text
    masked = text
    for entity in sorted(entities, key=lambda e: e["BeginOffset"], reverse=True):
        begin, end = entity["BeginOffset"], entity["EndOffset"]
        masked = masked[:begin] + f"[{entity['Type']}]" + masked[end:]
    return masked


def lambda_handler(event, context):
    action = event.get("action", "check")

    if action == "write":
        cached_result = dict(event["result"])
        if cached_result.get("query"):
            cached_result["query"] = mask_pii(cached_result["query"])
        cache_table.put_item(Item={
            "query_hash": event["queryHash"],
            "result": json.dumps(cached_result),
            "expires_at": int(time.time()) + CACHE_TTL_SECONDS,
        })
        return event["result"]

    query = event["query"]
    query_hash = compute_query_hash(query)

    cached = cache_table.get_item(Key={"query_hash": query_hash}).get("Item")
    if cached:
        return {
            "cached": True,
            "query": query,
            "queryHash": query_hash,
            "isComplex": None,  # not computed on this branch, but Step Functions'
                                 # ResultSelector needs every referenced field present
                                 # in every possible response shape, not just the
                                 # branch that goes on to use it
            "result": json.loads(cached["result"]),
        }

    response = bedrock_runtime.converse(
        modelId=CLASSIFY_MODEL,
        messages=[{
            "role": "user",
            "content": [{"text": (
                "Is this question asking about multiple independent things that would need "
                "separate searches to fully answer, or is it a single simple question? "
                'Respond with ONLY valid JSON: {"isComplex": true} or {"isComplex": false}.\n\n'
                f"Question: {query}"
            )}],
        }],
        inferenceConfig={"maxTokens": 50, "temperature": 0},
    )
    output = response["output"]["message"]["content"][0]["text"]

    try:
        parsed = json.loads(output[output.index("{"):output.rindex("}") + 1])
        is_complex = bool(parsed.get("isComplex", False))
    except (ValueError, json.JSONDecodeError):
        is_complex = False  # fail toward the simpler, cheaper path

    return {
        "cached": False,
        "query": query,
        "queryHash": query_hash,
        "isComplex": is_complex,
        "result": None,  # Step Functions' ResultSelector needs this key present either way -
                          # a JSONPath in ResultSelector fails the whole state if it can't
                          # resolve, even when the branch that would use it isn't taken
    }
