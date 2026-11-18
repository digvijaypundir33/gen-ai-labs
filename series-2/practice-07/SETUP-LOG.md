# Practice 07 — Setup log

Every AWS change this practice makes, with its idle cost and how to undo it. Region: `us-east-1`.

| # | Stage | Change | How | Idle cost | Undo / teardown |
|---|---|---|---|---|---|
| 1 | 3 | **`generate` (P02 Lambda) redeployed** with two changes. (a) An opt-in `include_debug` flag returns the retrieved chunk text, the answer model's token usage and `subQueries`. (b) The `tier` and `include_debug` overrides are now honoured only on direct invoke (no `requestContext` in the event). Until now, `tier` was reachable from the public `/ask` route. Normal responses are unchanged. | `zip -j generate.zip lambda_function.py && aws lambda update-function-code --function-name generate --zip-file fileb://generate.zip`. Verified by downloading the deployed code and diffing it (identical), then a live check on both paths. | $0 (code change only) | Redeploy the previous version: `git show 2770786:series-1/practice-02/lambda/generate/lambda_function.py > lambda_function.py`, then zip and `update-function-code` as before. That version is identical to what was deployed before (confirmed by the Stage 0 diff). |

| 2 | 4a | **S3 bucket `rag-assistant-eval-156207843797`.** Holds datasets in `datasets/` and job output in `output/`. Public access blocked, SSE-S3, tagged `Practice=practice-07`. This is a new bucket rather than the planned `eval/` prefix in the docs bucket, because that bucket's Knowledge Base data source has no inclusion prefix (see PLAN Stage 4), so golden answers stored there could be indexed into retrieval. | `aws s3api create-bucket`, `put-public-access-block`, `put-bucket-tagging` | ~$0 (KB of JSONL) | `aws s3 rb s3://rag-assistant-eval-156207843797 --force` |
| 3 | 4a | **IAM role `rag-assistant-eval-role`** for Bedrock evaluation jobs. Trusted only by `bedrock.amazonaws.com` for `evaluation-job/*` in this account. The inline policy `EvalJobAccess` allows S3 read on `datasets/*`, write on `output/*`, and `InvokeModel` on Nova Micro and Nova Lite only. | `aws iam create-role` + `put-role-policy`, from `eval-job/*.json` | $0 | `aws iam delete-role-policy --role-name rag-assistant-eval-role --policy-name EvalJobAccess && aws iam delete-role --role-name rag-assistant-eval-role` |
| 4 | 4 | **Evaluation jobs** `p07-smoke-…`, `p07-qa-micro-…`, `p07-qa-lite-…`, `p07-judge-…`. These are metadata records only; their output lives in the bucket above. | `managed_eval.py submit <job>` | $0 idle (inference billed once, at run time) | Deleted with the bucket. The job records themselves can't be deleted, and cost nothing. |

## Spend so far

| Stage | Calls | Cost |
|---|---|---|
| 0 | ~8 one-word "Reply with OK" probe calls | < $0.001 |
| 3 | 2 smoke-test `generate` calls + 30 collection calls | ~$0.061 estimated at P05's $0.0019 per `/ask` request. Measured parts: $0.0065 answer model (34,605 in / 1,815 out tokens) + ~$0.022 grounding (~219 text units) |
| 4 | 4 evaluation jobs: 1 test, 2 Q&A with robustness perturbations, 1 RAG judge over 10 items × 4 metrics | < $0.02 estimated; the jobs don't report token usage. To confirm against Cost Explorer at wrap-up |
