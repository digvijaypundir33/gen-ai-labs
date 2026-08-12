import json
import os
import time
import uuid

os.environ.setdefault("TIKTOKEN_CACHE_DIR", os.path.join(os.path.dirname(__file__), "tiktoken_cache"))

import boto3
import tiktoken

dynamodb = boto3.resource("dynamodb")
tickets_table = dynamodb.Table("SupportTickets")
stepfunctions = boto3.client("stepfunctions")
comprehend = boto3.client("comprehend")

WORKFLOW_ARN = "arn:aws:states:us-east-1:156207843797:stateMachine:support-ticket-workflow"

VALID_CATEGORIES = {"technical", "billing", "feature", "other"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}
MAX_TOKENS = 8000

_encoding = tiktoken.get_encoding("cl100k_base")

MIN_PII_SCORE = 0.5


def mask_pii(text):
    """Comprehend-based masking for what gets persisted to DynamoDB - a
    different layer than the Bedrock Guardrail on ticket-generate-response:
    that one protects the model's input/output boundary, this one protects
    data at rest, which the guardrail's INPUT-side check never actually
    covers (confirmed live: sensitiveInformationPolicyUnits stayed 0 on every
    INPUT-side check we tested - it only ever fired on OUTPUT).
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
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    subject = (body.get("subject") or "").strip()
    description = (body.get("description") or "").strip()
    category = body.get("category") if body.get("category") in VALID_CATEGORIES else "other"
    priority = body.get("priority") if body.get("priority") in VALID_PRIORITIES else "medium"

    if not subject or len(description) < 10:
        return _response(400, {"error": "subject is required and description must be at least 10 characters"})

    token_count = len(_encoding.encode(description))
    if token_count > MAX_TOKENS:
        return _response(413, {"error": f"description exceeds {MAX_TOKENS} token limit ({token_count} tokens)"})

    ticket_id = str(uuid.uuid4())
    now = int(time.time())

    # Masked copy goes to storage; the workflow below still gets the original
    # text, since a masked description would lose context the model needs to
    # help (e.g. "my SSN isn't showing correctly in the billing export") - the
    # generation step's own output is independently protected by the Bedrock
    # Guardrail already wired into ticket-generate-response.
    tickets_table.put_item(
        Item={
            "ticket_id": ticket_id,
            "subject": mask_pii(subject),
            "description": mask_pii(description),
            "category": category,
            "priority": priority,
            "status": "received",
            "created_at": now,
            "updated_at": now,
        }
    )

    execution = stepfunctions.start_sync_execution(
        stateMachineArn=WORKFLOW_ARN,
        input=json.dumps(
            {
                "ticket_id": ticket_id,
                "subject": subject,
                "description": description,
                "priority": priority,
            }
        ),
    )

    if execution["status"] != "SUCCEEDED":
        return _response(
            502,
            {"ticketId": ticket_id, "status": "workflow_failed", "tokenCount": token_count},
        )

    result = json.loads(execution["output"])

    return _response(
        200,
        {
            "ticketId": ticket_id,
            "status": result.get("crm", {}).get("status", "received"),
            "tokenCount": token_count,
            "classification": result.get("classification"),
            "aiResponse": result.get("generation", {}).get("response"),
            "modelUsed": result.get("generation", {}).get("modelUsed"),
        },
    )


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
