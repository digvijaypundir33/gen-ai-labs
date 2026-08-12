import time
import uuid

import boto3

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
bedrock_runtime = boto3.client("bedrock-runtime")

FLOW_ID = "KGO3XOMZI5"
FLOW_ALIAS_ID = "LR18LJ7QK1"
MAX_POLL_SECONDS = 25
POLL_INTERVAL_SECONDS = 1
TERMINAL_STATUSES = {"Succeeded", "Failed", "TimedOut", "Aborted"}

GUARDRAIL_ID = "5jk3sefhtv16"
GUARDRAIL_VERSION = "4"
BLOCKED_MESSAGE = (
    "I'm sorry, but I can't help with that request. If you believe this is an "
    "error, please contact support directly."
)


def _is_hard_block(assessment):
    """GUARDRAIL_INTERVENED fires both for a real block (topic/content/word
    policy, or a PII entity configured to BLOCK) and for a successful PII
    ANONYMIZE (content redacted, not rejected). Only the former should discard
    the response - the latter already has safe, usable text in outputs.
    """
    topic = assessment.get("topicPolicy") or {}
    if any(e.get("action") == "BLOCKED" for e in topic.get("topics", [])):
        return True
    content = assessment.get("contentPolicy") or {}
    if any(e.get("action") == "BLOCKED" for e in content.get("filters", [])):
        return True
    word = assessment.get("wordPolicy") or {}
    if any(e.get("action") == "BLOCKED" for e in word.get("words", []) + word.get("managedWordLists", [])):
        return True
    sensitive = assessment.get("sensitiveInformationPolicy") or {}
    if any(e.get("action") == "BLOCKED" for e in sensitive.get("piiEntities", []) + sensitive.get("regexes", [])):
        return True
    return False


def apply_guardrail(text, source):
    """Standalone apply_guardrail, used on both sides of the flow invocation.
    start_flow_execution has no guardrailConfig parameter - Prompt Flows attach
    guardrails at the node level inside the flow definition, not on the invoke
    call - so unlike the direct converse() case in practice-02's generate
    Lambda, this needs two explicit round trips instead of one inline check.
    """
    if not text:
        return False, text
    response = bedrock_runtime.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source=source,
        content=[{"text": {"text": text}}],
    )
    assessment = (response.get("assessments") or [{}])[0]
    blocked = response["action"] == "GUARDRAIL_INTERVENED" and _is_hard_block(assessment)
    outputs = response.get("outputs") or []
    filtered = outputs[0]["text"] if outputs else text
    return blocked, filtered


def lambda_handler(event, context):
    subject = event.get("subject", "")
    description = event.get("description", "")
    priority = event.get("priority", "medium")
    kb_context = event.get("kb_context", "")

    # Checked as one combined blob (fail-fast signal only - the flow still gets
    # the original, unfiltered subject/description fields below, since it needs
    # them as separate structured inputs rather than a single merged string).
    input_blocked, _ = apply_guardrail(f"{subject}\n{description}", "INPUT")
    if input_blocked:
        return {"response": BLOCKED_MESSAGE, "status": "GuardrailBlocked", "modelUsed": None}

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

    output_blocked, filtered_response = apply_guardrail(response_text, "OUTPUT")
    if output_blocked:
        return {"response": BLOCKED_MESSAGE, "status": "GuardrailBlocked", "modelUsed": model_used}

    return {"response": filtered_response, "status": status, "modelUsed": model_used}
