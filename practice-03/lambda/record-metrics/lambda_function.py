import json
import time
import uuid
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
metrics_table = dynamodb.Table("RoutingMetrics")


def lambda_handler(event, context):
    classification = event["classification"]
    result_body = json.loads(event["result_body"])

    request_id = str(uuid.uuid4())

    metrics_table.put_item(Item={
        "request_id": request_id,
        "document_type": classification["type"],
        "complexity": classification["complexity"],
        "classification_time_seconds": Decimal(str(classification["processing_time"])),
        "model_used": result_body["model_used"],
        "timestamp": int(time.time()),
    })

    return {"recorded": True, "request_id": request_id}
