import json
import random
import time

import boto3

bedrock_runtime = boto3.client("bedrock-runtime")
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
dynamodb = boto3.resource("dynamodb")
circuit_breaker_table = dynamodb.Table("ModelCircuitBreaker")

KNOWLEDGE_BASE_ID = "LTIWE7M3DC"
KB_CIRCUIT_KEY = "bedrock-kb-retrieve"
PRIMARY_MODEL = "amazon.nova-lite-v1:0"
FALLBACK_MODEL = "amazon.nova-pro-v1:0"

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


def _retrieve_kb_context(query, max_results=3):
    if _circuit_is_open(KB_CIRCUIT_KEY):
        return ""
    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": max_results}},
        )
        _record_success(KB_CIRCUIT_KEY)
        chunks = [r["content"]["text"] for r in response.get("retrievalResults", [])]
        return "\n\n".join(chunks)
    except Exception:
        _record_failure(KB_CIRCUIT_KEY)
        return ""


def _stream_with_retry(model_id, prompt, send):
    retries = 0
    while True:
        try:
            response = bedrock_runtime.converse_stream(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 500, "temperature": 0.6},
            )
            for stream_event in response["stream"]:
                if "contentBlockDelta" in stream_event:
                    text = stream_event["contentBlockDelta"]["delta"].get("text")
                    if text:
                        send({"token": text})
            _record_success(model_id)
            return
        except bedrock_runtime.exceptions.ThrottlingException:
            if retries >= MAX_RETRIES:
                _record_failure(model_id)
                raise
            delay = (2 ** retries) * BASE_DELAY_SECONDS + random.uniform(0, 0.1)
            time.sleep(delay)
            retries += 1
        except Exception:
            _record_failure(model_id)
            raise


def lambda_handler(event, context):
    request_context = event["requestContext"]
    connection_id = request_context["connectionId"]
    endpoint_url = f"https://{request_context['domainName']}/{request_context['stage']}"
    apigw = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint_url)

    def send(payload):
        apigw.post_to_connection(ConnectionId=connection_id, Data=json.dumps(payload).encode("utf-8"))

    body = event.get("body")
    body = json.loads(body) if body else {}
    subject = body.get("subject", "")
    message = body.get("message", "")

    if not message:
        send({"error": "missing 'message'"})
        return {"statusCode": 400}

    kb_context = _retrieve_kb_context(f"{subject} {message}".strip())
    send({"kb_context_found": bool(kb_context)})

    prompt = (
        f"You are a customer support chat agent. Subject: {subject}. "
        f"Customer message: {message}. Relevant internal knowledge: {kb_context}. "
        "Respond conversationally and helpfully."
    )

    model_id = FALLBACK_MODEL if _circuit_is_open(PRIMARY_MODEL) else PRIMARY_MODEL

    try:
        try:
            _stream_with_retry(model_id, prompt, send)
        except Exception:
            if model_id == FALLBACK_MODEL:
                raise
            model_id = FALLBACK_MODEL
            _stream_with_retry(model_id, prompt, send)

        send({"done": True, "model_used": model_id})
    except apigw.exceptions.GoneException:
        pass

    return {"statusCode": 200}
