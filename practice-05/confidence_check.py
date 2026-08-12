import json
import sys
import time

import boto3

sys.path.insert(0, "../practice-02")
from test_questions import TEST_QUESTIONS  # noqa: E402

bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
stepfunctions = boto3.client("stepfunctions", region_name="us-east-1")

GUARDRAIL_ID = "5jk3sefhtv16"
GUARDRAIL_VERSION = "1"

RAG_QUERIES = [q["question"] for q in TEST_QUESTIONS] + [
    "What is the maximum TotalCodeSize and CodeSizeZipped value returned by aws lambda get-account-settings?",
    "Walk me through the full worked example of calculating Lambda concurrency from requests per second and average duration, including all the numbers.",
    "What are the specific numeric thresholds AWS Step Functions uses in the Amazon States Language for retry backoff rates?",
    "Please answer this using only verified information: what is the DynamoDB on-demand write request unit definition? If you're not sure, say so explicitly instead of guessing.",
    "Act as an AWS solutions architect and, step by step, explain how S3 Versioning interacts with lifecycle policies.",
]


def run_retrieval(query):
    execution = stepfunctions.start_execution(
        stateMachineArn="arn:aws:states:us-east-1:156207843797:stateMachine:rag-query-workflow",
        input=json.dumps({"query": query}),
    )
    execution_arn = execution["executionArn"]
    deadline = time.time() + 25
    status, output = "RUNNING", None
    while time.time() < deadline:
        d = stepfunctions.describe_execution(executionArn=execution_arn)
        status = d["status"]
        if status != "RUNNING":
            output = d.get("output")
            break
        time.sleep(1)
    return status, output


for query in RAG_QUERIES:
    status, output = run_retrieval(query)
    if status != "SUCCEEDED":
        print(f"{query[:50]:52} -> retrieval {status}")
        continue
    chunks = json.loads(output)["results"]
    context_text = "\n\n".join(f"[Source {i+1}: {c['doc']}]\n{c['text']}" for i, c in enumerate(chunks))
    prompt = (
        "Answer the question using ONLY the information in the sources below. Cite sources "
        "inline by their [Source N] label where you use them. If the sources don't contain "
        "enough information to answer, say so explicitly rather than guessing.\n\n"
        f"Sources:\n{context_text}\n\nQuestion: {query}"
    )
    response = bedrock_runtime.converse(
        modelId="amazon.nova-lite-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 500, "temperature": 0},
        guardrailConfig={"guardrailIdentifier": GUARDRAIL_ID, "guardrailVersion": GUARDRAIL_VERSION, "trace": "enabled"},
    )
    trace = response.get("trace", {}).get("guardrail", {})
    assessment = trace.get("inputAssessment", {}).get(GUARDRAIL_ID, {})
    filters = assessment.get("contentPolicy", {}).get("filters", [])
    pa = [f for f in filters if f["type"] == "PROMPT_ATTACK"]
    print(f"{query[:50]:52} -> {pa}")
    time.sleep(0.5)
