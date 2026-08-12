"""
Stage 9: measure the actual latency cost of each defense-in-depth layer wired
into the live generate and ticket-submit/ticket-generate-response paths, and
estimate the $ cost per request. Each component is timed directly (5 runs,
averaged) rather than trusting a single sample, given Stages 3/7 already
proved these APIs have real run-to-run latency/score variance.
"""
import json
import statistics
import time

import boto3

bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")
lambda_client = boto3.client("lambda", region_name="us-east-1")
stepfunctions = boto3.client("stepfunctions", region_name="us-east-1")

GUARDRAIL_ID = "5jk3sefhtv16"
GUARDRAIL_VERSION = "5"
MODEL_ID = "amazon.nova-lite-v1:0"

SAMPLE_QUERY = "What is the default cache TTL for API Gateway?"
SAMPLE_TICKET_TEXT = "My API Gateway cache keeps returning stale data after 5 minutes, is that expected?"


def timed(fn, n=5):
    times = []
    result = None
    for _ in range(n):
        start = time.time()
        result = fn()
        times.append(time.time() - start)
    return statistics.mean(times), statistics.stdev(times) if n > 1 else 0.0, result


def run_retrieval(query):
    execution = stepfunctions.start_execution(
        stateMachineArn="arn:aws:states:us-east-1:156207843797:stateMachine:rag-query-workflow",
        input=json.dumps({"query": query}),
    )
    execution_arn = execution["executionArn"]
    deadline = time.time() + 25
    while time.time() < deadline:
        d = stepfunctions.describe_execution(executionArn=execution_arn)
        if d["status"] != "RUNNING":
            return json.loads(d.get("output"))
        time.sleep(1)
    raise TimeoutError


def main():
    print("=== Component latency (mean of 5 calls, seconds) ===\n")

    # 1. Standalone apply_guardrail (INPUT check, used in check_input_safety)
    mean, stdev, _ = timed(lambda: bedrock_runtime.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID, guardrailVersion=GUARDRAIL_VERSION,
        source="INPUT", content=[{"text": {"text": SAMPLE_QUERY}}],
    ))
    print(f"apply_guardrail (standalone INPUT check):  {mean:.3f}s (+/-{stdev:.3f})")
    apply_guardrail_latency = mean

    # 2. Retrieval baseline (not a guardrail cost - for context)
    retrieval_result = run_retrieval(SAMPLE_QUERY)
    chunks = retrieval_result["results"]
    context_text = "\n\n".join(f"[Source {i+1}: {c['doc']}]\n{c['text']}" for i, c in enumerate(chunks))
    instruction = (
        "Use the reference material to answer the question below. Include a [Source N] "
        "citation for any fact you use. If the material doesn't cover the answer, state "
        f"that clearly.\n\nQuestion: {SAMPLE_QUERY}"
    )

    # 3. Converse WITHOUT guardrailConfig (baseline generation cost)
    mean_no_gr, stdev_no_gr, _ = timed(lambda: bedrock_runtime.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": f"{instruction}\n\nReference:\n{context_text}"}]}],
        inferenceConfig={"maxTokens": 500, "temperature": 0},
    ))
    print(f"converse WITHOUT guardrailConfig (baseline generation): {mean_no_gr:.3f}s (+/-{stdev_no_gr:.3f})")

    # 4. Converse WITH guardrailConfig (content safety + contextual grounding, inline)
    mean_gr, stdev_gr, _ = timed(lambda: bedrock_runtime.converse(
        modelId=MODEL_ID,
        messages=[{
            "role": "user",
            "content": [
                {"guardContent": {"text": {"text": context_text, "qualifiers": ["grounding_source"]}}},
                {"guardContent": {"text": {"text": instruction, "qualifiers": ["query"]}}},
            ],
        }],
        inferenceConfig={"maxTokens": 500, "temperature": 0},
        guardrailConfig={"guardrailIdentifier": GUARDRAIL_ID, "guardrailVersion": GUARDRAIL_VERSION, "trace": "enabled"},
    ))
    print(f"converse WITH guardrailConfig (content safety + grounding): {mean_gr:.3f}s (+/-{stdev_gr:.3f})")
    inline_guardrail_overhead = mean_gr - mean_no_gr
    print(f"  -> inline guardrail overhead: {inline_guardrail_overhead:+.3f}s")

    # 5. Comprehend detect_sentiment + detect_pii_entities, combined, measured via
    # the actual deployed moderation-risk-check Lambda (its execution role has
    # comprehend:DetectPiiEntities/DetectSentiment; the local CLI profile running
    # this script does not - Stage 4 only granted that to the Lambda role, and
    # this is the more production-representative measurement anyway: a real
    # Lambda invoke, not a bare boto3 call with no cold-start/init overhead).
    mean_comprehend, stdev_comprehend, _ = timed(lambda: lambda_client.invoke(
        FunctionName="moderation-risk-check",
        Payload=json.dumps({"input": SAMPLE_TICKET_TEXT}),
    ))
    print(f"\nmoderation-risk-check Lambda (detect_sentiment + detect_pii_entities, combined): "
          f"{mean_comprehend:.3f}s (+/-{stdev_comprehend:.3f})")
    mean_pii = mean_comprehend  # single Comprehend call's worth, per field, for the cost math below

    print("\n=== Per-request totals for the two LIVE paths ===\n")

    ask_total = apply_guardrail_latency + mean_gr
    print(f"/ask (generate Lambda): apply_guardrail INPUT ({apply_guardrail_latency:.3f}s) "
          f"+ converse-with-guardrail ({mean_gr:.3f}s) = {ask_total:.3f}s guardrail-touching total")
    print(f"  guardrail-attributable overhead vs a guardrail-free baseline: "
          f"{apply_guardrail_latency + inline_guardrail_overhead:.3f}s")

    # ticket-submit: 2x detect_pii_entities (subject+description) + ticket-generate-response:
    # 2x apply_guardrail (input+output). mean_pii is approximated from the combined
    # sentiment+PII Lambda invoke above (a single detect_pii_entities call alone should
    # be somewhat faster, since it's doing half the Comprehend work) - directionally
    # correct, not a precise isolated figure.
    ticket_total = (mean_pii * 2) + (apply_guardrail_latency * 2)
    print(f"\n/tickets (ticket-submit + ticket-generate-response): "
          f"~2x Comprehend PII mask (~{mean_pii:.3f}s each, approximated) + 2x apply_guardrail ({apply_guardrail_latency:.3f}s each) "
          f"= ~{ticket_total:.3f}s guardrail-attributable overhead")

    print("\n=== Estimated $ cost per request (list pricing, us-east-1) ===\n")
    # Bedrock Guardrails: $0.15 per 1,000 text units (1 unit = up to 1,000 characters) for
    # content filters + PII + prompt-attack; contextual grounding is billed separately at
    # $0.10 per 1,000 text units. Comprehend: $0.0001 per 100-character unit, 3-unit (300 char) minimum per call.
    GUARDRAIL_TEXT_UNIT_COST = 0.15 / 1000
    GROUNDING_TEXT_UNIT_COST = 0.10 / 1000
    COMPREHEND_UNIT_COST = 0.0001
    COMPREHEND_MIN_UNITS = 3

    query_chars = len(SAMPLE_QUERY)
    context_chars = len(context_text)
    query_units = max(1, -(-query_chars // 1000))
    context_units = max(1, -(-context_chars // 1000))

    ask_guardrail_cost = (query_units * GUARDRAIL_TEXT_UNIT_COST) + (context_units * (GUARDRAIL_TEXT_UNIT_COST + GROUNDING_TEXT_UNIT_COST))
    print(f"/ask: ~${ask_guardrail_cost:.6f} per request (guardrail text-unit charges only, excludes model tokens)")

    ticket_chars = len(SAMPLE_TICKET_TEXT)
    comprehend_units = max(COMPREHEND_MIN_UNITS, -(-ticket_chars // 100))
    ticket_pii_cost = comprehend_units * COMPREHEND_UNIT_COST * 2  # subject + description
    ticket_guardrail_cost = query_units * GUARDRAIL_TEXT_UNIT_COST * 2  # input + output check
    ticket_total_cost = ticket_pii_cost + ticket_guardrail_cost
    print(f"/tickets: ~${ticket_total_cost:.6f} per request "
          f"(${ticket_pii_cost:.6f} Comprehend PII + ${ticket_guardrail_cost:.6f} Guardrail apply_guardrail x2)")

    print("\nNote: pricing figures are AWS list prices as of this session, not verified "
          "against Cost Explorer billing data (too little elapsed time for billing data "
          "to post) - treat as an estimate, not an invoice.")


if __name__ == "__main__":
    main()
