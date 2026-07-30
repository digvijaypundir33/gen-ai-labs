import json
import time

import boto3

stepfunctions = boto3.client("stepfunctions")
bedrock_runtime = boto3.client("bedrock-runtime")

STATE_MACHINE_ARN = "arn:aws:states:us-east-1:156207843797:stateMachine:rag-query-workflow"
GENERATE_MODEL = "amazon.nova-lite-v1:0"
MAX_WAIT_SECONDS = 25
POLL_INTERVAL_SECONDS = 1


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


def build_prompt(query, chunks):
    context_text = "\n\n".join(
        f"[Source {i + 1}: {c['doc']}]\n{c['text']}" for i, c in enumerate(chunks)
    )
    return (
        "Answer the question using ONLY the information in the sources below. Cite sources "
        "inline by their [Source N] label where you use them. If the sources don't contain "
        "enough information to answer, say so explicitly rather than guessing.\n\n"
        f"Sources:\n{context_text}\n\n"
        f"Question: {query}"
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

    status, output = run_retrieval(query)
    if status != "SUCCEEDED":
        send({"error": f"retrieval did not complete in time (status={status})"})
        return {"statusCode": 504}

    retrieval = json.loads(output)
    chunks = retrieval.get("results", [])

    if not chunks:
        send({"token": "I don't have enough information in the knowledge base to answer that."})
        send({"done": True, "sources": []})
        return {"statusCode": 200}

    prompt = build_prompt(query, chunks)

    try:
        response = bedrock_runtime.converse_stream(
            modelId=GENERATE_MODEL,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 500, "temperature": 0},
        )
        for stream_event in response["stream"]:
            if "contentBlockDelta" in stream_event:
                text = stream_event["contentBlockDelta"]["delta"].get("text")
                if text:
                    send({"token": text})

        send({
            "done": True,
            "sources": [{"doc": c["doc"], "uri": c["uri"]} for c in chunks],
        })
    except apigw.exceptions.GoneException:
        pass  # client disconnected mid-stream - nothing left to send to

    return {"statusCode": 200}
