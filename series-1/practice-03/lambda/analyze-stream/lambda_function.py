import json
import random
import time

import boto3

bedrock_runtime = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")
circuit_breaker_table = dynamodb.Table("ModelCircuitBreaker")

MODEL_BY_TYPE = {
    "legal": "amazon.nova-lite-v1:0",
    "technical": "amazon.nova-lite-v1:0",
    "feedback": "amazon.nova-micro-v1:0",
    "general": "amazon.nova-micro-v1:0",
}
FALLBACK_MODEL = "amazon.nova-pro-v1:0"

MAX_RETRIES = 3
BASE_DELAY_SECONDS = 0.2
FAILURE_THRESHOLD = 5
COOLDOWN_SECONDS = 60


def _circuit_is_open(model_id):
    item = circuit_breaker_table.get_item(Key={"model_id": model_id}).get("Item")
    if not item or not item.get("circuit_open"):
        return False
    if time.time() - int(item.get("last_failure", 0)) > COOLDOWN_SECONDS:
        return False
    return True


def _record_success(model_id):
    circuit_breaker_table.put_item(Item={
        "model_id": model_id,
        "circuit_open": False,
        "failure_count": 0,
    })


def _record_failure(model_id):
    response = circuit_breaker_table.update_item(
        Key={"model_id": model_id},
        UpdateExpression="SET failure_count = if_not_exists(failure_count, :zero) + :one, last_failure = :now",
        ExpressionAttributeValues={":zero": 0, ":one": 1, ":now": int(time.time())},
        ReturnValues="UPDATED_NEW",
    )
    if response["Attributes"]["failure_count"] >= FAILURE_THRESHOLD:
        circuit_breaker_table.update_item(
            Key={"model_id": model_id},
            UpdateExpression="SET circuit_open = :true",
            ExpressionAttributeValues={":true": True},
        )


def _stream_with_retry(model_id, prompt, send):
    retries = 0
    while True:
        try:
            response = bedrock_runtime.converse_stream(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 500, "temperature": 0.7},
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
    document_text = body.get("document")
    document_type = body.get("type", "general")

    if not document_text:
        send({"error": "missing 'document'"})
        return {"statusCode": 400}

    prompt = f"Analyze the following document and provide key insights:\n\n{document_text}"
    primary_model = MODEL_BY_TYPE.get(document_type, MODEL_BY_TYPE["general"])
    model_id = FALLBACK_MODEL if _circuit_is_open(primary_model) else primary_model

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
        pass  # client disconnected mid-stream

    return {"statusCode": 200}
