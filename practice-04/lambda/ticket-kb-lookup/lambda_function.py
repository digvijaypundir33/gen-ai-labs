import random
import time

import boto3

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
dynamodb = boto3.resource("dynamodb")
circuit_breaker_table = dynamodb.Table("ModelCircuitBreaker")

KNOWLEDGE_BASE_ID = "LTIWE7M3DC"
CIRCUIT_KEY = "bedrock-kb-retrieve"
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 0.2
FAILURE_THRESHOLD = 5
COOLDOWN_SECONDS = 60


def _circuit_is_open(key):
    item = circuit_breaker_table.get_item(Key={"model_id": key}).get("Item")
    if not item or not item.get("circuit_open"):
        return False
    if time.time() - int(item.get("last_failure", 0)) > COOLDOWN_SECONDS:
        return False
    return True


def _record_success(key):
    circuit_breaker_table.put_item(Item={"model_id": key, "circuit_open": False, "failure_count": 0})


def _record_failure(key):
    response = circuit_breaker_table.update_item(
        Key={"model_id": key},
        UpdateExpression="SET failure_count = if_not_exists(failure_count, :zero) + :one, last_failure = :now",
        ExpressionAttributeValues={":zero": 0, ":one": 1, ":now": int(time.time())},
        ReturnValues="UPDATED_NEW",
    )
    if response["Attributes"]["failure_count"] >= FAILURE_THRESHOLD:
        circuit_breaker_table.update_item(
            Key={"model_id": key},
            UpdateExpression="SET circuit_open = :true",
            ExpressionAttributeValues={":true": True},
        )


def retrieve_chunks(query, max_results=3):
    if _circuit_is_open(CIRCUIT_KEY):
        return []

    retries = 0
    while True:
        try:
            response = bedrock_agent_runtime.retrieve(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,
                retrievalQuery={"text": query},
                retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": max_results}},
            )
            _record_success(CIRCUIT_KEY)
            return [r["content"]["text"] for r in response.get("retrievalResults", [])]
        except bedrock_agent_runtime.exceptions.ThrottlingException:
            if retries >= MAX_RETRIES:
                _record_failure(CIRCUIT_KEY)
                return []
            delay = (2 ** retries) * BASE_DELAY_SECONDS + random.uniform(0, 0.1)
            time.sleep(delay)
            retries += 1
        except Exception:
            _record_failure(CIRCUIT_KEY)
            return []


def lambda_handler(event, context):
    subject = event.get("subject", "")
    description = event.get("description", "")
    query = event.get("query") or f"{subject} {description}".strip()

    if not query:
        return {"chunks": [], "kb_context": ""}

    chunks = retrieve_chunks(query)
    return {"chunks": chunks, "kb_context": "\n\n".join(chunks)}
