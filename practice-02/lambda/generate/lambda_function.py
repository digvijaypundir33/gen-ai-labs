import json
import time

import boto3

stepfunctions = boto3.client("stepfunctions")
bedrock_runtime = boto3.client("bedrock-runtime")

STATE_MACHINE_ARN = "arn:aws:states:us-east-1:156207843797:stateMachine:rag-query-workflow"
GENERATE_MODEL = "amazon.nova-lite-v1:0"
MAX_WAIT_SECONDS = 25
POLL_INTERVAL_SECONDS = 1


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


def generate_answer(query, chunks):
    if not chunks:
        return "I don't have enough information in the knowledge base to answer that."

    context_text = "\n\n".join(
        f"[Source {i + 1}: {c['doc']}]\n{c['text']}" for i, c in enumerate(chunks)
    )
    prompt = (
        "Answer the question using ONLY the information in the sources below. Cite sources "
        "inline by their [Source N] label where you use them. If the sources don't contain "
        "enough information to answer, say so explicitly rather than guessing.\n\n"
        f"Sources:\n{context_text}\n\n"
        f"Question: {query}"
    )

    response = bedrock_runtime.converse(
        modelId=GENERATE_MODEL,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 500, "temperature": 0},
    )
    return response["output"]["message"]["content"][0]["text"]


def lambda_handler(event, context):
    body = event.get("body")
    if body and isinstance(body, str):
        body = json.loads(body)
    payload = body or event

    query = payload.get("query")
    if not query:
        return _response(400, {"error": "missing 'query'"})

    status, output = run_retrieval(query)

    if status != "SUCCEEDED":
        return _response(504, {"error": f"retrieval did not complete in time (status={status})"})

    retrieval = json.loads(output)
    chunks = retrieval.get("results", [])

    answer = generate_answer(query, chunks)

    return _response(200, {
        "query": query,
        "answer": answer,
        "sources": [{"doc": c["doc"], "uri": c["uri"]} for c in chunks],
    })
