"""
Stage 8: a quality gate over the golden set.

Event:
  {"mode": "live"}
      Invoke the deployed `generate` on every golden question and score what it
      returns: what a user would get today.
  {"mode": "candidate", "model_id": "...", "max_tokens": N, "label": "..."}
      Score a proposed generation config *before* it ships. Answers are regenerated
      from the stored retrieved passages with generate's exact prompt, then checked
      by the production guardrail (ApplyGuardrail, grounding qualifiers). A block
      counts exactly as it would live, as a refusal.

Each answer is scored by Nova Micro on two anchored 1-5 rubrics (factual accuracy
against the reference; completeness against the question), 3 runs each, with
refusals scored like any other text. The run score is the mean over items. The gate
FAILS when that falls below the threshold stored with the baseline in
EvaluationResults (run p07-s8-baseline, item "#gate"). Every run writes its result
rows to the same table, and a FAIL publishes to SNS.

The scorer is Nova Micro on purpose, despite the halo effect Stage 5 measured: that
halo makes it a cheap, stable detector of the failures that matter here (refusals,
broken or truncated answers). The rubric and parsing are copies of
practice-07/judge_eval.py, so the Lambda deploys as one file plus its dataset.
"""

import json
import os
import re
import statistics
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3

REGION = "us-east-1"
TABLE = os.environ.get("RESULTS_TABLE", "EvaluationResults")
TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN")
GENERATE_FUNCTION = os.environ.get("GENERATE_FUNCTION", "generate")
GUARDRAIL_ID, GUARDRAIL_VERSION = "5jk3sefhtv16", "5"
SCORER = "amazon.nova-micro-v1:0"
DIMENSIONS = ("factual_accuracy", "completeness")
SCORE_RUNS = 3
BLOCKED_MESSAGE = "I'm not able to provide that response. Please rephrase your question or contact support for further assistance."

RUBRICS = {
    "factual_accuracy": "Are the response's facts correct, judged against the reference answer? "
                        "5 = every fact agrees with the reference and nothing is false; 3 = mostly right with a "
                        "minor error or an unsupported extra claim; 1 = contradicts the reference, or states no facts.",
    "completeness": "Does the response cover every part of the question asked (not everything the reference "
                    "mentions)? 5 = all parts; 3 = some parts missing; 1 = none.",
}

_clients = {}


def client(name):
    if name not in _clients:
        _clients[name] = boto3.client(name, region_name=REGION)
    return _clients[name]


# ---- scoring (pure apart from the injected converse function) ----

def rubric_prompt(dimension, query, response, reference):
    return f"""You are grading one quality dimension of an answer from a technical-documentation assistant.

Dimension: {dimension.replace('_', ' ')}
Rubric: {RUBRICS[dimension]}

Question:
{query}

Reference answer:
{reference}

Answer to grade:
{response}

Reply with only a JSON object, no other text: {{"score": <integer 1-5>, "reason": "<one sentence>"}}"""


def parse_score(text):
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = float(json.loads(text[start:end + 1]).get("score"))
    except (ValueError, TypeError, json.JSONDecodeError, AttributeError):
        return None
    return value if 1 <= value <= 5 else None


def score_answer(item, answer, converse):
    """Mean of DIMENSIONS x SCORE_RUNS rubric scores, and how many replies failed to parse."""
    scores, failures = [], 0
    for dim in DIMENSIONS:
        for run in range(SCORE_RUNS):
            s = parse_score(converse(SCORER, rubric_prompt(dim, item["question"], answer, item["ground_truth"]),
                                     150, run))
            if s is None:
                failures += 1
            else:
                scores.append(s)
    return (statistics.mean(scores) if scores else 1.0), failures


def decide(run_score, baseline):
    return "PASS" if run_score >= baseline["threshold"] else "FAIL"


# ---- answers ----

def generate_prompt_parts(question, chunks):
    source = "\n\n".join(f"[Source {i + 1}: {c['doc']}]\n{c['text']}" for i, c in enumerate(chunks))
    instruction = (
        "Use the reference material to answer the question below. Include a [Source N] "
        "citation for any fact you use. If the material doesn't cover the answer, state "
        f"that clearly.\n\nQuestion: {question}"
    )
    return source, instruction


def live_answer(item):
    resp = client("lambda").invoke(FunctionName=GENERATE_FUNCTION, Payload=json.dumps({"query": item["question"]}))
    body = json.loads(json.loads(resp["Payload"].read())["body"])
    return body.get("answer", ""), body.get("guardrail_action") != "none"


def candidate_answer(item, model_id, max_tokens):
    source, instruction = generate_prompt_parts(item["question"], item["chunks"])
    resp = client("bedrock-runtime").converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": f"{source}\n\n{instruction}"}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
    )
    answer = "".join(b["text"] for b in resp["output"]["message"]["content"] if "text" in b)
    check = client("bedrock-runtime").apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID, guardrailVersion=GUARDRAIL_VERSION, source="OUTPUT",
        content=[{"text": {"text": source, "qualifiers": ["grounding_source"]}},
                 {"text": {"text": instruction, "qualifiers": ["query"]}},
                 {"text": {"text": answer, "qualifiers": ["guard_content"]}}],
    )
    if check.get("action") == "GUARDRAIL_INTERVENED":
        return BLOCKED_MESSAGE, True
    return answer, False


def bedrock_converse(model_id, prompt, max_tokens, run):
    # `run` is unused here; it exists so the local baseline can pass a cached converse that keys on it.
    resp = client("bedrock-runtime").converse(
        modelId=model_id, messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
    )
    return "".join(b["text"] for b in resp["output"]["message"]["content"] if "text" in b)


# ---- storage and alerting ----

def to_dynamo(value):
    if isinstance(value, float):
        return Decimal(str(round(value, 6)))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items() if v is not None}
    return value


def load_baseline():
    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    item = table.get_item(Key={"run_id": "p07-s8-baseline", "item_metric": "#gate"}).get("Item")
    if not item:
        raise RuntimeError("no baseline stored: run gate_baseline.py first")
    return {"score": float(item["score"]), "threshold": float(item["threshold"])}


def store(run_id, summary, items):
    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    with table.batch_writer() as batch:
        batch.put_item(Item=to_dynamo({"run_id": run_id, "item_metric": "#run", "stage": 8, **summary}))
        for it in items:
            batch.put_item(Item=to_dynamo({"run_id": run_id, "item_metric": f"{it['item_id']}#gate_score",
                                           "stage": 8, **it}))


def alert(summary):
    if not TOPIC_ARN:
        return None
    msg = (f"Quality gate FAILED for {summary['mode']} ({summary.get('label') or 'deployed generate'}): "
           f"score {summary['score']:.2f} < threshold {summary['threshold']:.2f} "
           f"(baseline {summary['baseline']:.2f}). Blocked {summary['blocked']}/{summary['items']}. "
           f"Rows: EvaluationResults run_id={summary['run_id']}")
    return client("sns").publish(TopicArn=TOPIC_ARN, Subject="RAG assistant quality gate FAILED",
                                 Message=msg)["MessageId"]


def load_dataset():
    with open(os.path.join(os.path.dirname(__file__), "gate_dataset.json")) as f:
        return json.load(f)


def lambda_handler(event, context):
    mode = event.get("mode", "live")
    if mode not in ("live", "candidate"):
        return {"error": f"unknown mode {mode!r}"}
    baseline = load_baseline()
    dataset = load_dataset()

    items, parse_failures = [], 0
    started = time.time()
    for item in dataset:
        if mode == "live":
            answer, blocked = live_answer(item)
        else:
            answer, blocked = candidate_answer(item, event["model_id"], int(event["max_tokens"]))
        score, failures = score_answer(item, answer, bedrock_converse)
        parse_failures += failures
        items.append({"item_id": item["item_id"], "score": score, "blocked": blocked, "answer": answer[:500]})

    run_score = statistics.mean(i["score"] for i in items)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = {
        "run_id": f"p07-s8-gate-{mode}-{stamp}", "mode": mode, "label": event.get("label"),
        "model_id": event.get("model_id"), "max_tokens": event.get("max_tokens"),
        "score": run_score, "baseline": baseline["score"], "threshold": baseline["threshold"],
        "decision": decide(run_score, baseline), "items": len(items),
        "blocked": sum(1 for i in items if i["blocked"]), "parse_failures": parse_failures,
        "seconds": round(time.time() - started, 1),
    }
    store(summary["run_id"], summary, items)
    if summary["decision"] == "FAIL":
        summary["sns_message_id"] = alert(summary)
    print(json.dumps(summary))
    return summary
