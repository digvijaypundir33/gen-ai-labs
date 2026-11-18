"""
Stage 4: Amazon Bedrock Model Evaluations (managed), driven from one script.

  build              write the JSONL datasets into results/eval-datasets/ (offline)
  submit <job>       upload that job's dataset and create the evaluation job
  status             list this practice's jobs and their state
  fetch <job>        download a finished job's output into results/managed-eval/<job>/

Jobs:
  smoke      1 prompt, Nova Micro, accuracy only. It exists to prove the account
             can run evaluation jobs at all (P05 found Bedrock Agents Classic
             blocked at account level, so this is a real risk).
  qa-micro   programmatic Q&A over the 10 golden questions: accuracy, robustness,
  qa-lite    toxicity. One job per model, since an automatic job takes exactly one
             model. The job sends the *bare question*, with no retrieval, so it
             scores the model's own knowledge, not the RAG system.
  judge      LLM-as-judge on Stage 3's real `generate` answers, as a *RAG*
             evaluation with bring-your-own responses: Bedrock skips inference
             and only judges. Nova Micro judges correctness, completeness,
             faithfulness and refusal. First built as a model-evaluation job with
             the chunks pasted into the prompt, it would have been rejected: the
             prompt quota is 4 KB, and these prompts are 5-13 KB. The RAG job
             type takes the retrieved passages as their own field.

Run:  .venv/bin/python managed_eval.py build
      .venv/bin/python managed_eval.py submit smoke
"""

import argparse
import json
import os
import sys
import time

from evalkit.bedrock import REGION
from evalkit.golden import load_golden_set

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(HERE, "results", "eval-datasets")
OUTPUT_DIR = os.path.join(HERE, "results", "managed-eval")
RESPONSES_PATH = os.path.join(HERE, "results", "responses.jsonl")

ACCOUNT = "156207843797"
BUCKET = f"rag-assistant-eval-{ACCOUNT}"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/rag-assistant-eval-role"
JOB_PREFIX = "p07"
BYO_SOURCE = "rag-assistant-generate"  # names the precomputed responses inside the judge dataset

# maxTokens matches generate's 500 budget, so the bare models get the same room as the RAG answers.
INFERENCE_PARAMS = json.dumps({"inferenceConfig": {"maxTokens": 500}})

JOBS = {
    "smoke": {"dataset": "smoke.jsonl", "task": "QuestionAndAnswer",
              "metrics": ["Builtin.Accuracy"], "model": "amazon.nova-micro-v1:0"},
    "qa-micro": {"dataset": "qa.jsonl", "task": "QuestionAndAnswer",
                 "metrics": ["Builtin.Accuracy", "Builtin.Robustness", "Builtin.Toxicity"],
                 "model": "amazon.nova-micro-v1:0"},
    "qa-lite": {"dataset": "qa.jsonl", "task": "QuestionAndAnswer",
                "metrics": ["Builtin.Accuracy", "Builtin.Robustness", "Builtin.Toxicity"],
                "model": "amazon.nova-lite-v1:0"},
    "judge": {"dataset": "judge-rag-byo.jsonl", "task": "General", "rag": True,
              "metrics": ["Builtin.Correctness", "Builtin.Completeness", "Builtin.Faithfulness",
                          "Builtin.Refusal"],
              "evaluator": "amazon.nova-micro-v1:0"},
}


def rag_record(row):
    # Format from the Bedrock user guide, "Creating a prompt dataset for
    # retrieve-and-generate RAG evaluation jobs", bring-your-own section.
    return {"conversationTurns": [{
        "prompt": {"content": [{"text": row["question"]}]},
        "referenceResponses": [{"content": [{"text": row["ground_truth"]}]}],
        "output": {
            "text": row["answer"],
            "modelIdentifier": row["model_id"] or "amazon.nova-lite-v1:0",
            "knowledgeBaseIdentifier": BYO_SOURCE,
            "retrievedPassages": {"retrievalResults": [
                {"name": c["doc"], "content": {"text": c["text"]}} for c in row["chunks"]
            ]},
        },
    }]}


def build():
    os.makedirs(DATASET_DIR, exist_ok=True)
    golden = load_golden_set()
    qa = [{"prompt": q["question"], "referenceResponse": q["ground_truth"], "category": q["expected_doc"]}
          for q in golden]
    write_jsonl("smoke.jsonl", qa[:1])
    write_jsonl("qa.jsonl", qa)

    # Trial 0 of each question: one answer per item. A blocked answer stays in, as the
    # refusal text the user actually saw, so the judge scores the system rather than the
    # model's hidden draft.
    with open(RESPONSES_PATH) as f:
        rows = [r for r in map(json.loads, f) if r["trial"] == 0]
    write_jsonl("judge-rag-byo.jsonl", [rag_record(r) for r in sorted(rows, key=lambda r: r["item_id"])])


def write_jsonl(name, records):
    path = os.path.join(DATASET_DIR, name)
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(records):2d} records -> {os.path.relpath(path, HERE)}")


def clients():
    import boto3
    return boto3.client("s3", region_name=REGION), boto3.client("bedrock", region_name=REGION)


def submit(job):
    spec = JOBS[job]
    s3, bedrock = clients()
    key = f"datasets/{spec['dataset']}"
    s3.upload_file(os.path.join(DATASET_DIR, spec["dataset"]), BUCKET, key)

    automated = {"datasetMetricConfigs": [{
        "taskType": spec["task"],
        "dataset": {"name": job, "datasetLocation": {"s3Uri": f"s3://{BUCKET}/{key}"}},
        "metricNames": spec["metrics"],
    }]}
    if spec.get("rag"):
        automated["evaluatorModelConfig"] = {"bedrockEvaluatorModels": [{"modelIdentifier": spec["evaluator"]}]}
        application_type = "RagEvaluation"
        # ragSourceIdentifier must match every record's output.knowledgeBaseIdentifier.
        inference_config = {"ragConfigs": [{"precomputedRagSourceConfig": {
            "retrieveAndGenerateSourceConfig": {"ragSourceIdentifier": BYO_SOURCE}}}]}
    else:
        application_type = "ModelEvaluation"
        inference_config = {"models": [{"bedrockModel": {
            "modelIdentifier": spec["model"], "inferenceParams": INFERENCE_PARAMS}}]}

    name = f"{JOB_PREFIX}-{job}-{time.strftime('%Y%m%d-%H%M%S')}"
    resp = bedrock.create_evaluation_job(
        jobName=name,
        roleArn=ROLE_ARN,
        applicationType=application_type,
        evaluationConfig={"automated": automated},
        inferenceConfig=inference_config,
        outputDataConfig={"s3Uri": f"s3://{BUCKET}/output/{job}/"},
        jobTags=[{"key": "Practice", "value": "practice-07"}],
    )
    print(f"created {name}\n  {resp['jobArn']}")


def status():
    _, bedrock = clients()
    jobs = bedrock.list_evaluation_jobs(nameContains=JOB_PREFIX, sortBy="CreationTime", sortOrder="Descending")
    for j in jobs["jobSummaries"]:
        print(f"{j['jobName']:40s} {j['status']:12s} {j['creationTime']:%Y-%m-%d %H:%M}")
        if j["status"] == "Failed":
            detail = bedrock.get_evaluation_job(jobIdentifier=j["jobArn"])
            print("   failure:", detail.get("failureMessages"))


def fetch(job):
    s3, _ = clients()
    dest = os.path.join(OUTPUT_DIR, job)
    os.makedirs(dest, exist_ok=True)
    paginator = s3.get_paginator("list_objects_v2")
    n = 0
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"output/{job}/"):
        for obj in page.get("Contents", []):
            local = os.path.join(dest, os.path.relpath(obj["Key"], f"output/{job}"))
            os.makedirs(os.path.dirname(local), exist_ok=True)
            s3.download_file(BUCKET, obj["Key"], local)
            n += 1
    print(f"downloaded {n} files -> {os.path.relpath(dest, HERE)}")


def main():
    parser = argparse.ArgumentParser(description="Stage 4: managed Bedrock evaluation jobs")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("status")
    for cmd in ("submit", "fetch"):
        p = sub.add_parser(cmd)
        p.add_argument("job", choices=sorted(JOBS))
    args = parser.parse_args()
    if args.cmd == "build":
        build()
    elif args.cmd == "submit":
        submit(args.job)
    elif args.cmd == "status":
        status()
    else:
        fetch(args.job)
    return 0


if __name__ == "__main__":
    sys.exit(main())
