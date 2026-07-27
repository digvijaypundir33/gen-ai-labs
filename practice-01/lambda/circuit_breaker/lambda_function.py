"""
Circuit breaker state, invoked directly by Step Functions (not via API Gateway).

Tracks failure state per logical role (primary/fallback) rather than per
model ID, since the actual Bedrock model behind a role can change via
AppConfig - the question this answers is "has this slot been failing
lately," independent of which model currently occupies it.

Actions: "check" (should we try this role right now?), "record_success"
(reset to CLOSED), "record_failure" (bump the count, open past threshold).
"""

import os
import time

import boto3

TABLE_NAME = os.environ.get("BREAKER_TABLE", "ai-assistant-circuit-breaker")
FAILURE_THRESHOLD = int(os.environ.get("FAILURE_THRESHOLD", "3"))
COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "60"))

table = boto3.resource("dynamodb").Table(TABLE_NAME)


def get_breaker(breaker_id):
    response = table.get_item(Key={"breaker_id": breaker_id})
    item = response.get("Item")
    if item is None:
        return {"breaker_id": breaker_id, "state": "CLOSED", "failure_count": 0, "opened_at": 0}
    return item


def lambda_handler(event, context):
    breaker_id = event["breaker_id"]
    action = event["action"]
    breaker = get_breaker(breaker_id)
    now = int(time.time())

    if action == "check":
        if breaker["state"] == "OPEN":
            if now - int(breaker["opened_at"]) >= COOLDOWN_SECONDS:
                table.put_item(Item={
                    "breaker_id": breaker_id, "state": "HALF_OPEN",
                    "failure_count": breaker["failure_count"], "opened_at": breaker["opened_at"],
                })
                return {"allow": True, "state": "HALF_OPEN"}
            return {"allow": False, "state": "OPEN"}
        return {"allow": True, "state": breaker["state"]}

    if action == "record_success":
        table.put_item(Item={"breaker_id": breaker_id, "state": "CLOSED", "failure_count": 0, "opened_at": 0})
        return {"state": "CLOSED"}

    if action == "record_failure":
        new_count = int(breaker["failure_count"]) + 1
        new_state = "OPEN" if new_count >= FAILURE_THRESHOLD else breaker["state"]
        opened_at = now if new_state == "OPEN" else breaker.get("opened_at", 0)
        table.put_item(Item={
            "breaker_id": breaker_id, "state": new_state,
            "failure_count": new_count, "opened_at": opened_at,
        })
        return {"state": new_state, "failure_count": new_count}

    raise ValueError(f"Unknown action: {action}")
