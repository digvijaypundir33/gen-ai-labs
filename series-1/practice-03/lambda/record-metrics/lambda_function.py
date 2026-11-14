import json
import time
import uuid
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
metrics_table = dynamodb.Table("RoutingMetrics")

# On-demand USD per 1,000 tokens, us-east-1. Re-verified against the Bedrock
# pricing page 2026-08-18 (practice-06 Stage 8). Duplicated here rather than
# shared via a Layer, matching this repo's existing convention for small
# helpers (mask_pii and friends are copy-pasted across Lambdas too; the one
# Layer in the repo is for a third-party dependency, not business logic).
#
# nova-pro is ~13x nova-lite on both input and output - the reason this table
# needed a new entry at all is that practice-06 Stage 4 now routes decomposed
# queries to it, so cost per request is no longer uniform.
PRICING_PER_1K_TOKENS = {
    "amazon.nova-micro-v1:0": {"input": 0.000035, "output": 0.00014},
    "amazon.nova-lite-v1:0": {"input": 0.00006, "output": 0.00024},
    "amazon.nova-pro-v1:0": {"input": 0.0008, "output": 0.0032},
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.001, "output": 0.005},
}


def estimate_cost(model_id, input_tokens, output_tokens):
    """Real billed token counts x published rate. Returns None rather than 0
    when either the model or the token counts are unknown - a missing cost and
    a genuinely free request must not look identical in the table, or any
    average computed downstream is silently wrong.
    """
    price = PRICING_PER_1K_TOKENS.get(model_id)
    if price is None or input_tokens is None or output_tokens is None:
        return None
    return (input_tokens / 1000.0) * price["input"] + (output_tokens / 1000.0) * price["output"]


def lambda_handler(event, context):
    classification = event["classification"]
    result_body = json.loads(event["result_body"])

    request_id = str(uuid.uuid4())
    model_used = result_body["model_used"]
    input_tokens = result_body.get("input_tokens")
    output_tokens = result_body.get("output_tokens")
    cost = estimate_cost(model_used, input_tokens, output_tokens)

    item = {
        "request_id": request_id,
        "document_type": classification["type"],
        "complexity": classification["complexity"],
        "classification_time_seconds": Decimal(str(classification["processing_time"])),
        "model_used": model_used,
        "timestamp": int(time.time()),
    }
    # Only write the cost fields when they're genuinely known, so rows written
    # before Stage 8 and rows where usage was unavailable stay distinguishable
    # from rows that really cost nothing.
    if input_tokens is not None:
        item["input_tokens"] = int(input_tokens)
    if output_tokens is not None:
        item["output_tokens"] = int(output_tokens)
    if cost is not None:
        item["estimated_cost_usd"] = Decimal(str(round(cost, 8)))

    metrics_table.put_item(Item=item)

    return {"recorded": True, "request_id": request_id}
