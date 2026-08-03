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


def _response(status_code, body_dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body_dict),
    }


def _circuit_is_open(model_id):
    item = circuit_breaker_table.get_item(Key={"model_id": model_id}).get("Item")
    if not item or not item.get("circuit_open"):
        return False
    # Half-open: once the cooldown has passed, let one trial request through
    # rather than keeping the circuit open forever.
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


def _invoke_with_retry(model_id, prompt):
    retries = 0
    while True:
        try:
            response = bedrock_runtime.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 500, "temperature": 0.7},
            )
            _record_success(model_id)
            return response["output"]["message"]["content"][0]["text"]
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


def analyze_document(document_text, document_type):
    prompt = f"Analyze the following document and provide key insights:\n\n{document_text}"
    primary_model = MODEL_BY_TYPE.get(document_type, MODEL_BY_TYPE["general"])

    model_id = FALLBACK_MODEL if _circuit_is_open(primary_model) else primary_model

    try:
        analysis = _invoke_with_retry(model_id, prompt)
        return analysis, model_id
    except Exception:
        if model_id == FALLBACK_MODEL:
            raise
        analysis = _invoke_with_retry(FALLBACK_MODEL, prompt)
        return analysis, FALLBACK_MODEL


def lambda_handler(event, context):
    body = event.get("body")
    if body and isinstance(body, str):
        body = json.loads(body)
    payload = body or event

    document_text = payload.get("document")
    document_type = payload.get("type", "general")

    if not document_text:
        return _response(400, {"error": "missing 'document'"})

    analysis, model_used = analyze_document(document_text, document_type)

    return _response(200, {
        "analysis": analysis,
        "model_used": model_used,
    })
