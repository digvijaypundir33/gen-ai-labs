"""
Stage 10 (revised): hand-rolled Converse tool-use loop, standing in for classic
Bedrock Agents (blocked - account-level maintenance-mode policy) and AgentCore
(evaluated, doesn't earn its weight for a two-tool/single-KB scope). This
Lambda owns the full request/tool/response loop itself and logs every step,
which is exactly the transparency behavior Stage 10 set out to get - we just
get there without adopting a managed agent platform.
"""
import json

import boto3

bedrock_runtime = boto3.client("bedrock-runtime")
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
lambda_client = boto3.client("lambda")

# Complexity-tiered model selection (practice-06 Stage 4). Unlike `generate`,
# this Lambda has no upstream classifier output to read - there's no Step
# Functions workflow in front of it - so the tier is derived from the message
# itself. Deliberately a keyword/length heuristic rather than an LLM
# classification call: spending a model call to choose a model would eat the
# saving the tiering exists to create.
#
# The tier is computed ONCE, before the loop, and held fixed across all
# MAX_TOOL_ITERATIONS rounds. Re-picking mid-loop would mean a tool-use
# conversation whose modelId changes between turns, with the same toolConfig
# and message history - an inconsistency that isn't worth the marginal saving.
# nova-micro is deliberately absent. It was built as a third tier here too,
# then dropped on `generate`'s measurement (practice-06 Stage 4,
# tier_quality_check.py): on a corpus-answerable query, n=10, nova-micro's
# grounding scores sat at mean 0.741 against a 0.75 block threshold and got
# BLOCKED 8/10, where nova-lite scored 0.917 and was blocked 0/10. That is a
# model-level quality result, not a `generate`-specific one, so it applies
# here without re-deriving it.
MODEL_TIERS = {
    "lite": {"modelId": "amazon.nova-lite-v1:0", "maxTokens": 600},
    "pro": {"modelId": "amazon.nova-pro-v1:0", "maxTokens": 600},
}
DEFAULT_TIER = "lite"  # unchanged from pre-Stage-4 behavior
# Multi-step asks - the agent will likely need several tool round-trips, which
# is exactly where a weaker model loops or gives up early.
COMPLEX_MARKERS = (
    "and then", "after that", "compare", "both", "all of", "each of",
    "why", "explain", "troubleshoot", "diagnose", "update", "change",
)

KNOWLEDGE_BASE_ID = "LTIWE7M3DC"
CRM_ACTIONS_FUNCTION = "crm-agent-actions"
GUARDRAIL_ID = "5jk3sefhtv16"
GUARDRAIL_VERSION = "5"
MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = (
    "You are a transparent AWS technical support agent. You can search AWS "
    "documentation and look up or update support ticket records. Always "
    "explain what you're checking before you check it, cite which tool "
    "produced each fact, and be explicit when something isn't covered by "
    "what you found rather than guessing."
)

TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "search_knowledge_base",
                "description": "Search the AWS technical documentation knowledge base.",
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                }},
            }
        },
        {
            "toolSpec": {
                "name": "get_ticket_status",
                "description": "Look up a support ticket's current status, category, and priority.",
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {"ticket_id": {"type": "string"}},
                    "required": ["ticket_id"],
                }},
            }
        },
        {
            "toolSpec": {
                "name": "update_ticket_priority",
                "description": "Update a support ticket's priority level.",
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    },
                    "required": ["ticket_id", "priority"],
                }},
            }
        },
    ]
}


def search_knowledge_base(tool_input):
    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": tool_input["query"]},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 3}},
    )
    results = [
        {"doc": r["location"]["s3Location"]["uri"].split("/")[-1], "text": r["content"]["text"]}
        for r in response["retrievalResults"]
    ]
    return json.dumps(results)


def _invoke_crm_action(function_name, params):
    payload = {
        "actionGroup": "CrmActions",
        "function": function_name,
        "parameters": [{"name": k, "value": str(v)} for k, v in params.items()],
    }
    response = lambda_client.invoke(FunctionName=CRM_ACTIONS_FUNCTION, Payload=json.dumps(payload))
    result = json.loads(response["Payload"].read())
    return result["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]


def get_ticket_status(tool_input):
    return _invoke_crm_action("get_ticket_status", tool_input)


def update_ticket_priority(tool_input):
    return _invoke_crm_action("update_ticket_priority", tool_input)


TOOL_HANDLERS = {
    "search_knowledge_base": search_knowledge_base,
    "get_ticket_status": get_ticket_status,
    "update_ticket_priority": update_ticket_priority,
}


def select_tier(user_message):
    """Pure function of the incoming message - no model call, see MODEL_TIERS."""
    lowered = user_message.lower()
    if any(marker in lowered for marker in COMPLEX_MARKERS):
        return "pro"
    return DEFAULT_TIER


def lambda_handler(event, context):
    user_message = event.get("message")
    if not user_message:
        return {"error": "missing 'message'"}

    tier = select_tier(user_message)
    tier_config = MODEL_TIERS[tier]
    print(json.dumps({
        "tier": tier,
        "modelId": tier_config["modelId"],
        "maxTokens": tier_config["maxTokens"],
        "messageWords": len(user_message.split()),
    }))

    messages = [{"role": "user", "content": [{"text": user_message}]}]
    trace = []

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = bedrock_runtime.converse(
            modelId=tier_config["modelId"],
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,
            toolConfig=TOOL_CONFIG,
            inferenceConfig={"maxTokens": tier_config["maxTokens"], "temperature": 0},
            guardrailConfig={"guardrailIdentifier": GUARDRAIL_ID, "guardrailVersion": GUARDRAIL_VERSION, "trace": "enabled"},
        )
        stop_reason = response["stopReason"]
        assistant_message = response["output"]["message"]

        trace.append({
            "iteration": iteration,
            "stopReason": stop_reason,
            "assistantContent": [
                {"type": "text", "text": c["text"]} if "text" in c
                else {"type": "toolUse", "name": c["toolUse"]["name"], "input": c["toolUse"]["input"]}
                for c in assistant_message["content"]
            ],
        })

        if stop_reason == "guardrail_intervened":
            return {
                "answer": assistant_message["content"][0]["text"],
                "trace": trace,
                "iterations": iteration + 1,
                "model_tier": tier,
            }

        if stop_reason != "tool_use":
            final_text = next((c["text"] for c in assistant_message["content"] if "text" in c), "")
            return {"answer": final_text, "trace": trace, "iterations": iteration + 1, "model_tier": tier}

        messages.append(assistant_message)
        tool_results = []
        for block in assistant_message["content"]:
            if "toolUse" not in block:
                continue
            tool_use = block["toolUse"]
            handler = TOOL_HANDLERS.get(tool_use["name"])
            result_text = handler(tool_use["input"]) if handler else f"Unknown tool: {tool_use['name']}"
            trace.append({
                "iteration": iteration,
                "toolCall": tool_use["name"],
                "toolInput": tool_use["input"],
                "toolResult": result_text,
            })
            tool_results.append({
                "toolResult": {
                    "toolUseId": tool_use["toolUseId"],
                    "content": [{"text": result_text}],
                }
            })
        messages.append({"role": "user", "content": tool_results})

    return {"answer": "Reached max tool iterations without a final answer.", "trace": trace, "iterations": MAX_TOOL_ITERATIONS, "model_tier": tier}
