import time
import uuid

import boto3

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")

FLOW_ID = "KGO3XOMZI5"
FLOW_ALIAS_ID = "LR18LJ7QK1"
MAX_POLL_SECONDS = 25
POLL_INTERVAL_SECONDS = 1
TERMINAL_STATUSES = {"Succeeded", "Failed", "TimedOut", "Aborted"}


def lambda_handler(event, context):
    subject = event.get("subject", "")
    description = event.get("description", "")
    priority = event.get("priority", "medium")
    kb_context = event.get("kb_context", "")

    execution_name = str(uuid.uuid4())

    bedrock_agent_runtime.start_flow_execution(
        flowIdentifier=FLOW_ID,
        flowAliasIdentifier=FLOW_ALIAS_ID,
        flowExecutionName=execution_name,
        inputs=[
            {
                "content": {
                    "document": {
                        "subject": subject,
                        "description": description,
                        "priority": priority,
                        "kb_context": kb_context,
                    }
                },
                "nodeName": "FlowInputNode",
                "nodeOutputName": "document",
            }
        ],
    )

    status = None
    deadline = time.time() + MAX_POLL_SECONDS
    while time.time() < deadline:
        execution = bedrock_agent_runtime.get_flow_execution(
            flowIdentifier=FLOW_ID,
            flowAliasIdentifier=FLOW_ALIAS_ID,
            executionIdentifier=execution_name,
        )
        status = execution["status"]
        if status in TERMINAL_STATUSES:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    if status != "Succeeded":
        return {"response": None, "status": status or "Timeout", "modelUsed": None}

    events = bedrock_agent_runtime.list_flow_execution_events(
        flowIdentifier=FLOW_ID,
        flowAliasIdentifier=FLOW_ALIAS_ID,
        executionIdentifier=execution_name,
        eventType="Node",
    )["flowExecutionEvents"]

    response_text = None
    model_used = None
    for evt in events:
        node_input = evt.get("nodeInputEvent")
        if node_input and node_input.get("nodeName") in ("UrgentFlowOutput", "StandardFlowOutput"):
            response_text = node_input["fields"][0]["content"]["document"]
            model_used = "urgent" if node_input["nodeName"] == "UrgentFlowOutput" else "standard"

    return {"response": response_text, "status": status, "modelUsed": model_used}
