import json
import time

import boto3

stepfunctions = boto3.client("stepfunctions")
bedrock_runtime = boto3.client("bedrock-runtime")

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


def _is_hard_block(assessment):
    """Mirrors generate/lambda_function.py - this Lambda had none of the
    guardrail wiring that was added there in Stages 2/3/7 (input check, inline
    guardrailConfig, contextual grounding) - the streaming path (default-on in
    the UI) was unprotected while the REST path was fully covered.
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
    grounding = assessment.get("contextualGroundingPolicy") or {}
    return any(f.get("action") == "BLOCKED" for f in grounding.get("filters", []))


def _grounding_score(assessment):
    grounding = assessment.get("contextualGroundingPolicy") or {}
    for f in grounding.get("filters", []):
        if f.get("type") == "GROUNDING":
            return f.get("score")
    return None


def check_input_safety(query):
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


def build_instruction(query):
    # Matches generate/lambda_function.py's Stage 3 wording fix - the original
    # imperative "answer using ONLY... say so explicitly rather than guessing"
    # phrasing measurably tripped the PROMPT_ATTACK filter on benign content.
    return (
        "Use the reference material to answer the question below. Include a [Source N] "
        "citation for any fact you use. If the material doesn't cover the answer, state "
        f"that clearly.\n\nQuestion: {query}"
    )


def lambda_handler(event, context):
    request_context = event["requestContext"]
    connection_id = request_context["connectionId"]
    endpoint_url = f"https://{request_context['domainName']}/{request_context['stage']}"
    apigw = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint_url)

    def send(payload):
        apigw.post_to_connection(ConnectionId=connection_id, Data=json.dumps(payload).encode("utf-8"))

    body = event.get("body")
    body = json.loads(body) if body else {}
    query = body.get("question")

    if not query:
        send({"error": "missing 'question'"})
        return {"statusCode": 400}

    input_blocked, filtered_query = check_input_safety(query)
    if input_blocked:
        send({"token": BLOCKED_MESSAGE})
        send({"done": True, "sources": [], "guardrail_action": "input_blocked"})
        return {"statusCode": 200}

    status, output = run_retrieval(filtered_query)
    if status != "SUCCEEDED":
        send({"error": f"retrieval did not complete in time (status={status})"})
        return {"statusCode": 504}

    retrieval = json.loads(output)
    chunks = retrieval.get("results", [])

    if not chunks:
        send({"token": "I don't have enough information in the knowledge base to answer that."})
        send({"done": True, "sources": []})
        return {"statusCode": 200}

    context_text = "\n\n".join(
        f"[Source {i + 1}: {c['doc']}]\n{c['text']}" for i, c in enumerate(chunks)
    )
    instruction = build_instruction(filtered_query)

    try:
        response = bedrock_runtime.converse_stream(
            modelId=GENERATE_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"guardContent": {"text": {"text": context_text, "qualifiers": ["grounding_source"]}}},
                    {"guardContent": {"text": {"text": instruction, "qualifiers": ["query"]}}},
                ],
            }],
            guardrailConfig={"guardrailIdentifier": GUARDRAIL_ID, "guardrailVersion": GUARDRAIL_VERSION, "trace": "enabled"},
            inferenceConfig={"maxTokens": 500, "temperature": 0},
        )
        stop_reason = None
        guardrail_trace = None
        for stream_event in response["stream"]:
            if "contentBlockDelta" in stream_event:
                text = stream_event["contentBlockDelta"]["delta"].get("text")
                if text:
                    send({"token": text})
            elif "messageStop" in stream_event:
                stop_reason = stream_event["messageStop"].get("stopReason")
            elif "metadata" in stream_event:
                guardrail_trace = stream_event["metadata"].get("trace", {}).get("guardrail")

        hard_blocked = False
        ungrounded = False
        grounding_score = None
        if guardrail_trace:
            output_assessments = (guardrail_trace.get("outputAssessments") or {}).get(GUARDRAIL_ID, [])
            grounding_score = next((_grounding_score(a) for a in output_assessments if _grounding_score(a) is not None), None)
            if stop_reason == "guardrail_intervened":
                input_assessment = (guardrail_trace.get("inputAssessment") or {}).get(GUARDRAIL_ID, {})
                ungrounded = any(_grounding_failed(a) for a in output_assessments)
                hard_blocked = (
                    _is_hard_block(input_assessment)
                    or any(_is_hard_block(a) for a in output_assessments)
                    or ungrounded
                )

        if hard_blocked:
            guardrail_action = "ungrounded_intervened" if ungrounded else "output_intervened"
        elif stop_reason == "guardrail_intervened":
            guardrail_action = "anonymized"
        else:
            guardrail_action = "none"

        # Tokens are forwarded live as they're generated, before the guardrail
        # verdict is known - grounding in particular can only be scored once
        # enough text exists, so a chunk of the (possibly ungrounded) answer
        # may have already reached the client by the time we learn it should
        # have been withheld. "retract" tells the frontend to discard whatever
        # partial text it's displaying and show `answer` instead of appending
        # the blocked message onto it - fixes the garbled display, but doesn't
        # undo the fact that partial content was already visible for a moment;
        # only a fully-buffered (non-streaming) response can prevent that.
        send({
            "done": True,
            "retract": hard_blocked,
            "answer": BLOCKED_MESSAGE if hard_blocked else None,
            "sources": [] if hard_blocked else [{"doc": c["doc"], "uri": c["uri"]} for c in chunks],
            "guardrail_action": guardrail_action,
            "confidence": grounding_score,
        })
    except apigw.exceptions.GoneException:
        pass  # client disconnected mid-stream - nothing left to send to
    except Exception as e:
        # A transient Bedrock-side error (e.g. internalServerException mid-stream)
        # otherwise crashes the Lambda unhandled - the client never gets a "done"
        # or "error" message and just hangs waiting for a response that never
        # comes. Surface it explicitly instead.
        try:
            send({"error": f"generation failed: {e}"})
        except apigw.exceptions.GoneException:
            pass

    return {"statusCode": 200}
