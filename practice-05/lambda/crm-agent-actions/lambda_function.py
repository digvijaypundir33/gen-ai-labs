import time
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
tickets_table = dynamodb.Table("SupportTickets")

VALID_PRIORITIES = {"low", "medium", "high", "critical"}


def _decimal_safe(value):
    if isinstance(value, list):
        return [_decimal_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _decimal_safe(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return value


def _params_to_dict(parameters):
    return {p["name"]: p["value"] for p in parameters or []}


def get_ticket_status(params):
    ticket_id = params.get("ticket_id")
    item = tickets_table.get_item(Key={"ticket_id": ticket_id}).get("Item")
    if not item:
        return f"No ticket found with ticket_id {ticket_id}."
    item = _decimal_safe(item)
    return (
        f"Ticket {ticket_id}: status={item.get('status')}, "
        f"category={item.get('category')}, priority={item.get('priority')}, "
        f"urgency={item.get('urgency', 'not yet classified')}."
    )


def update_ticket_priority(params):
    ticket_id = params.get("ticket_id")
    priority = (params.get("priority") or "").lower()
    if priority not in VALID_PRIORITIES:
        return f"'{priority}' is not a valid priority. Must be one of: {', '.join(sorted(VALID_PRIORITIES))}."

    existing = tickets_table.get_item(Key={"ticket_id": ticket_id}).get("Item")
    if not existing:
        return f"No ticket found with ticket_id {ticket_id}."

    tickets_table.update_item(
        Key={"ticket_id": ticket_id},
        UpdateExpression="SET priority = :priority, updated_at = :updated_at",
        ExpressionAttributeValues={":priority": priority, ":updated_at": int(time.time())},
    )
    return f"Ticket {ticket_id} priority updated to {priority}."


FUNCTIONS = {
    "get_ticket_status": get_ticket_status,
    "update_ticket_priority": update_ticket_priority,
}


def lambda_handler(event, context):
    action_group = event["actionGroup"]
    function = event["function"]
    params = _params_to_dict(event.get("parameters"))

    handler = FUNCTIONS.get(function)
    result_text = handler(params) if handler else f"Unknown function: {function}"

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "function": function,
            "functionResponse": {
                "responseBody": {"TEXT": {"body": result_text}}
            },
        },
    }
