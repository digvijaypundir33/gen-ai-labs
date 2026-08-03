import json
import random
import time

import boto3

agent_runtime = boto3.client("bedrock-agent-runtime")
bedrock_runtime = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")
circuit_breaker_table = dynamodb.Table("ModelCircuitBreaker")

KNOWLEDGE_BASE_ID = "LTIWE7M3DC"
RERANK_MODEL = "amazon.nova-lite-v1:0"
RESULTS_PER_QUERY = 3
RERANK_CANDIDATES = 5
FINAL_TOP_K = 3

# Sentinel key in the ModelCircuitBreaker table (built for Practice 03's resilience
# layer, reused here) - this isn't a model, but the table's schema is generic enough
# to track any resource's circuit state.
RETRIEVAL_CIRCUIT_KEY = "bedrock-kb-retrieve"
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 0.2
FAILURE_THRESHOLD = 5
COOLDOWN_SECONDS = 60


def _circuit_is_open():
    item = circuit_breaker_table.get_item(Key={"model_id": RETRIEVAL_CIRCUIT_KEY}).get("Item")
    if not item or not item.get("circuit_open"):
        return False
    if time.time() - int(item.get("last_failure", 0)) > COOLDOWN_SECONDS:
        return False
    return True


def _record_success():
    circuit_breaker_table.put_item(Item={
        "model_id": RETRIEVAL_CIRCUIT_KEY,
        "circuit_open": False,
        "failure_count": 0,
    })


def _record_failure():
    response = circuit_breaker_table.update_item(
        Key={"model_id": RETRIEVAL_CIRCUIT_KEY},
        UpdateExpression="SET failure_count = if_not_exists(failure_count, :zero) + :one, last_failure = :now",
        ExpressionAttributeValues={":zero": 0, ":one": 1, ":now": int(time.time())},
        ReturnValues="UPDATED_NEW",
    )
    if response["Attributes"]["failure_count"] >= FAILURE_THRESHOLD:
        circuit_breaker_table.update_item(
            Key={"model_id": RETRIEVAL_CIRCUIT_KEY},
            UpdateExpression="SET circuit_open = :true",
            ExpressionAttributeValues={":true": True},
        )


def retrieve_chunks(query, num_results=RESULTS_PER_QUERY):
    """Resilient wrapper around the KB retrieve call: retries transient throttling
    with backoff, and tracks a circuit breaker so a struggling KB fails fast instead
    of being hammered on every query variation. On exhausted retries or an open
    circuit, degrades gracefully to an empty result set rather than crashing the
    whole Lambda - downstream (generate) already handles "no chunks" by saying so
    explicitly instead of guessing.
    """
    if _circuit_is_open():
        return []

    retries = 0
    while True:
        try:
            response = agent_runtime.retrieve(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,
                retrievalQuery={"text": query},
                retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": num_results}},
            )
            _record_success()
            chunks = []
            for r in response["retrievalResults"]:
                uri = r["location"]["s3Location"]["uri"]
                chunks.append({
                    "doc": uri.split("/")[-1],
                    "uri": uri,
                    "text": r["content"]["text"],
                    "score": r["score"],
                })
            return chunks
        except agent_runtime.exceptions.ThrottlingException:
            if retries >= MAX_RETRIES:
                _record_failure()
                return []
            delay = (2 ** retries) * BASE_DELAY_SECONDS + random.uniform(0, 0.1)
            time.sleep(delay)
            retries += 1
        except Exception:
            _record_failure()
            return []


def merge_and_dedup(chunk_lists):
    best_by_text = {}
    for chunks in chunk_lists:
        for c in chunks:
            key = c["text"]
            if key not in best_by_text or c["score"] > best_by_text[key]["score"]:
                best_by_text[key] = c
    return sorted(best_by_text.values(), key=lambda c: -c["score"])


def _extract_score(element):
    if isinstance(element, (int, float)):
        return float(element)
    if isinstance(element, dict):
        for key in ("score", "relevance", "rating", "value"):
            if key in element and isinstance(element[key], (int, float)):
                return float(element[key])
    return 0.0


def nova_rerank(query, chunks):
    if not chunks:
        return []

    prompt = (
        "Score how well each passage answers the question, on a scale of 0-10. "
        "Respond with ONLY a JSON array of integers, one score per passage, in the "
        "same order as the passages below - no other text.\n\n"
        f"Question: {query}\n\n"
    )
    for i, c in enumerate(chunks):
        prompt += f"Passage {i + 1}: {c['text'][:800]}\n\n"

    response = bedrock_runtime.converse(
        modelId=RERANK_MODEL,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 200, "temperature": 0},
    )
    output = response["output"]["message"]["content"][0]["text"]

    try:
        raw = json.loads(output[output.index("["):output.rindex("]") + 1])
        scores = [_extract_score(e) for e in raw]
    except (ValueError, json.JSONDecodeError):
        scores = [0.0] * len(chunks)

    if len(scores) != len(chunks):
        scores = (scores + [0.0] * len(chunks))[:len(chunks)]

    reranked = sorted(zip(chunks, scores), key=lambda x: -x[1])
    return [c for c, _ in reranked]


def lambda_handler(event, context):
    queries = event.get("expandedQueries") or event.get("queries") or [event["query"]]
    primary_query = queries[0]

    chunk_lists = [retrieve_chunks(q) for q in queries]
    merged = merge_and_dedup(chunk_lists)

    reranked = nova_rerank(primary_query, merged[:RERANK_CANDIDATES])
    top = reranked[:FINAL_TOP_K]

    return {
        "query": primary_query,
        "results": [{"doc": c["doc"], "text": c["text"], "uri": c["uri"]} for c in top],
    }
