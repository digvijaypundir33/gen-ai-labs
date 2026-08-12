import json
import time

import boto3

stepfunctions = boto3.client("stepfunctions")
bedrock_runtime = boto3.client("bedrock-runtime")
cloudwatch = boto3.client("cloudwatch")

STATE_MACHINE_ARN = "arn:aws:states:us-east-1:156207843797:stateMachine:rag-query-workflow"
GENERATE_MODEL = "amazon.nova-lite-v1:0"
MAX_WAIT_SECONDS = 25
POLL_INTERVAL_SECONDS = 1

GUARDRAIL_ID = "5jk3sefhtv16"
GUARDRAIL_VERSION = "5"
BLOCKED_MESSAGE = (
    "I'm sorry, but I can't help with that request. If you believe this is an "
    "error, please contact support directly."
)


def _response(status_code, body_dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body_dict),
    }


def run_retrieval(query):
    execution = stepfunctions.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        input=json.dumps({"query": query}),
    )
    execution_arn = execution["executionArn"]

    deadline = time.time() + MAX_WAIT_SECONDS
    status = "RUNNING"
    output = None
    while time.time() < deadline:
        description = stepfunctions.describe_execution(executionArn=execution_arn)
        status = description["status"]
        if status != "RUNNING":
            output = description.get("output")
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    return status, output


def _is_hard_block(assessment):
    """GUARDRAIL_INTERVENED fires both for a real block (topic/content/word
    policy, or a PII entity configured to BLOCK) and for a successful PII
    ANONYMIZE (content redacted, not rejected). Only the former should discard
    the answer - the latter already has safe, usable text in outputs/content.
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


def _grounding_failed(assessment):
    """Contextual grounding/relevance are their own policy type - action is
    always BLOCKED on failure (no ANONYMIZE-equivalent), but it's a distinct
    failure mode from safety (hallucination/off-topic, not harmful content)
    worth reporting separately.
    """
    grounding = assessment.get("contextualGroundingPolicy") or {}
    return any(f.get("action") == "BLOCKED" for f in grounding.get("filters", []))


def _grounding_score(assessment):
    """The GROUNDING filter's score is present whenever the policy ran, whether
    or not it crossed the block threshold - a genuine confidence signal, not
    just a pass/fail bit. Returns None when the policy never ran (e.g. the
    turn was blocked before generation, or grounding isn't configured).
    """
    grounding = assessment.get("contextualGroundingPolicy") or {}
    for f in grounding.get("filters", []):
        if f.get("type") == "GROUNDING":
            return f.get("score")
    return None


def _emit_metrics(guardrail_action, grounding_score):
    metric_data = [{
        "MetricName": "GuardrailAction",
        "Dimensions": [{"Name": "Action", "Value": guardrail_action}],
        "Value": 1,
        "Unit": "Count",
    }]
    if grounding_score is not None:
        metric_data.append({
            "MetricName": "GroundingScore",
            "Value": grounding_score,
            "Unit": "None",
        })
    try:
        cloudwatch.put_metric_data(Namespace="RagAssistant/Guardrails", MetricData=metric_data)
    except Exception:
        pass  # metrics are observability, not a reason to fail the request


def check_input_safety(query):
    """Standalone apply_guardrail on the raw query, before any retrieval work
    happens. Blocking here means an unsafe query never reaches Step Functions,
    the KB retrieve call, or the rerank model - failing fast saves the cost of
    a full retrieval pipeline run on input we're going to refuse anyway.
    """
    response = bedrock_runtime.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source="INPUT",
        content=[{"text": {"text": query}}],
    )
    assessment = (response.get("assessments") or [{}])[0]
    blocked = response["action"] == "GUARDRAIL_INTERVENED" and _is_hard_block(assessment)
    outputs = response.get("outputs") or []
    filtered_query = outputs[0]["text"] if outputs else query
    return blocked, filtered_query


def generate_answer(query, chunks):
    if not chunks:
        return "I don't have enough information in the knowledge base to answer that.", False, None, None

    context_text = "\n\n".join(
        f"[Source {i + 1}: {c['doc']}]\n{c['text']}" for i, c in enumerate(chunks)
    )
    # Deliberately phrased as reference-material-plus-citation rather than
    # "answer using ONLY... say so explicitly rather than guessing" - the
    # original imperative-instruction wording measurably tripped the
    # PROMPT_ATTACK guardrail filter on benign RAG content (Stage 3 finding);
    # this wording keeps the same grounding behavior without the trigger words.
    instruction = (
        "Use the reference material to answer the question below. Include a [Source N] "
        "citation for any fact you use. If the material doesn't cover the answer, state "
        f"that clearly.\n\nQuestion: {query}"
    )

    # guardContent qualifiers tell the contextual grounding/relevance filters
    # which block is the source-of-truth (grounding_source) vs the actual ask
    # (query) - a single flat text block (the old shape) skips grounding
    # scoring entirely, since the guardrail has no way to tell what the answer
    # is supposed to be grounded against.
    response = bedrock_runtime.converse(
        modelId=GENERATE_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"guardContent": {"text": {"text": context_text, "qualifiers": ["grounding_source"]}}},
                {"guardContent": {"text": {"text": instruction, "qualifiers": ["query"]}}},
            ],
        }],
        inferenceConfig={"maxTokens": 500, "temperature": 0},
        guardrailConfig={
            "guardrailIdentifier": GUARDRAIL_ID,
            "guardrailVersion": GUARDRAIL_VERSION,
            "trace": "enabled",
        },
    )
    # Bedrock already substitutes blockedOutputsMessaging on a real block, and
    # already returns PII-redacted text on a successful anonymization - safe
    # to use in both cases without a separate override here.
    answer = response["output"]["message"]["content"][0]["text"]

    # Trace is populated whenever trace="enabled" was set, regardless of
    # whether the guardrail actually intervened - grounding score is a
    # confidence signal available on every passing answer too, not just blocks.
    guardrail_trace = response.get("trace", {}).get("guardrail", {})
    output_assessments = (guardrail_trace.get("outputAssessments") or {}).get(GUARDRAIL_ID, [])
    grounding_score = next((_grounding_score(a) for a in output_assessments if _grounding_score(a) is not None), None)

    hard_blocked = False
    intervention_side = None
    if response.get("stopReason") == "guardrail_intervened":
        input_assessment = (guardrail_trace.get("inputAssessment") or {}).get(GUARDRAIL_ID, {})
        if _is_hard_block(input_assessment):
            hard_blocked, intervention_side = True, "input"
        elif any(_is_hard_block(a) for a in output_assessments):
            hard_blocked, intervention_side = True, "output"
        elif any(_grounding_failed(a) for a in output_assessments):
            hard_blocked, intervention_side = True, "ungrounded"
        else:
            intervention_side = "anonymized"

    return answer, hard_blocked, intervention_side, grounding_score


def lambda_handler(event, context):
    body = event.get("body")
    if body and isinstance(body, str):
        body = json.loads(body)
    payload = body or event

    query = payload.get("query")
    if not query:
        return _response(400, {"error": "missing 'query'"})

    input_blocked, filtered_query = check_input_safety(query)
    if input_blocked:
        _emit_metrics("input_blocked", None)
        return _response(200, {
            "query": query,
            "answer": BLOCKED_MESSAGE,
            "sources": [],
            "guardrail_action": "input_blocked",
        })

    status, output = run_retrieval(filtered_query)

    if status != "SUCCEEDED":
        return _response(504, {"error": f"retrieval did not complete in time (status={status})"})

    retrieval = json.loads(output)
    chunks = retrieval.get("results", [])

    answer, hard_blocked, intervention_side, grounding_score = generate_answer(filtered_query, chunks)

    if hard_blocked:
        guardrail_action = f"converse_{intervention_side}_intervened"
    elif intervention_side == "anonymized":
        guardrail_action = "converse_anonymized"
    else:
        guardrail_action = "none"

    _emit_metrics(guardrail_action, grounding_score)

    return _response(200, {
        "query": query,
        "answer": answer,
        "sources": [] if hard_blocked else [{"doc": c["doc"], "uri": c["uri"]} for c in chunks],
        "guardrail_action": guardrail_action,
        "confidence": grounding_score,
    })
