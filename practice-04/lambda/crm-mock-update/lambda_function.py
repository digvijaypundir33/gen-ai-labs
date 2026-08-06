import time
import uuid

import boto3

dynamodb = boto3.resource("dynamodb")
tickets_table = dynamodb.Table("SupportTickets")


def lambda_handler(event, context):
    ticket_id = event["ticket_id"]
    classification = event.get("classification") or {}
    ai_response = event.get("ai_response")
    model_used = event.get("model_used")

    crm_update_id = f"crm-{ticket_id}"

    tickets_table.update_item(
        Key={"ticket_id": ticket_id},
        UpdateExpression=(
            "SET #status = :status, category = :category, urgency = :urgency, "
            "ai_response = :ai_response, model_used = :model_used, "
            "crm_update_id = :crm_update_id, updated_at = :updated_at"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "responded",
            ":category": classification.get("category", "other"),
            ":urgency": classification.get("urgency", "medium"),
            ":ai_response": ai_response,
            ":model_used": model_used,
            ":crm_update_id": crm_update_id,
            ":updated_at": int(time.time()),
        },
    )

    return {"ticket_id": ticket_id, "crm_update_id": crm_update_id, "status": "responded"}
