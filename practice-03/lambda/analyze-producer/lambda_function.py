import json
import uuid

import boto3

sqs = boto3.client("sqs")

QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/156207843797/document-analysis-queue"


def _response(status_code, body_dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body_dict),
    }


def lambda_handler(event, context):
    body = event.get("body")
    if body and isinstance(body, str):
        body = json.loads(body)
    payload = body or event

    document_text = payload.get("document")
    document_type = payload.get("type", "general")

    if not document_text:
        return _response(400, {"error": "missing 'document'"})

    job_id = str(uuid.uuid4())

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            "job_id": job_id,
            "document": document_text,
            "type": document_type,
        }),
    )

    return _response(202, {
        "message": "Document queued for processing",
        "job_id": job_id,
    })
