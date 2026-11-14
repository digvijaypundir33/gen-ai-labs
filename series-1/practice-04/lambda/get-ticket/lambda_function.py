import json
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
tickets_table = dynamodb.Table("SupportTickets")


def lambda_handler(event, context):
    ticket_id = (event.get("pathParameters") or {}).get("ticketId")
    if not ticket_id:
        return _response(400, {"error": "ticketId is required"})

    item = tickets_table.get_item(Key={"ticket_id": ticket_id}).get("Item")
    if not item:
        return _response(404, {"error": "Ticket not found"})

    return _response(200, _decimal_safe(item))


def _decimal_safe(value):
    if isinstance(value, list):
        return [_decimal_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _decimal_safe(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return value


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
