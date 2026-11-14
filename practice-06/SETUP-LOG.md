# Setup Log — Practice 06

Everything actually created or changed on AWS for this practice, with what it costs and how to
undo it. **Region: us-east-1** throughout, account `156207843797`.

This practice creates almost nothing new. It is mostly *modifications to existing practice-02/03/05
Lambdas*, plus one new Lambda and one scheduled rule. Everything foundational — the shared IAM role
(`rag-assistant-lambda-role`), the CLI user/profile (`rag-assistant`), both API Gateways, the S3
bucket, the Knowledge Base, and the `RoutingMetrics`/`SupportTickets`/`RagQueryCache` tables — is
reused from earlier practices and untouched. Stage 0 was a live audit confirming that, including
**downloading the deployed Lambda packages and diffing them against the repo** rather than assuming
they matched (they did, byte for byte).

**Status:** Stages 0-8 built and verified live. **Stage 9 deferred, never built.** The scheduled
rule (row 2) was deliberately **left DISABLED** at wrap-up.

## New resources created

| # | Resource | Notes | Made with | Cost while it exists | To delete |
|---|---|---|---|---|---|
| 1 | Lambda: `token-anomaly-check` | Stage 7. Scheduled token-usage anomaly detector. Reads a trailing `TokenCount` window back from CloudWatch (rather than the reference code's in-memory dict, which cannot accumulate anything on Lambda), computes mean/stdev, emits `TokenUsageAnomaly` beyond 2σ. Guards: refuses to judge below 5 baseline points; handles zero-variance baselines explicitly. python3.12, 30s timeout, 128MB, X-Ray active. | CLI (`lambda create-function`) | $0 idle, pay-per-invocation | `aws lambda delete-function --function-name token-anomaly-check --profile rag-assistant --region us-east-1` |
| 2 | EventBridge **Rule**: `rag-assistant-token-anomaly-schedule` | Stage 7. `rate(1 hour)` → `token-anomaly-check`. Deliberately a **classic EventBridge Rule** (`events.amazonaws.com`), matching P02's proven `rag-assistant-doc-sync-schedule` pattern — *not* EventBridge **Scheduler**, which P02 documented as a different product with a different principal. **Currently `DISABLED`** — enable with `aws events enable-rule --name rag-assistant-token-anomaly-schedule`. | CLI (`events put-rule` + `put-targets`) | $0 — EventBridge rules are free; invocations bill as Lambda | `aws events remove-targets --rule rag-assistant-token-anomaly-schedule --ids token-anomaly-check` then `aws events delete-rule --name rag-assistant-token-anomaly-schedule --profile rag-assistant --region us-east-1` |
| 3 | Lambda resource policy: `AllowEventBridgeAnomalySchedule` on `token-anomaly-check` | Stage 7. Grants `events.amazonaws.com` invoke permission, scoped to the rule ARN. | CLI (`lambda add-permission`) | Free | `aws lambda remove-permission --function-name token-anomaly-check --statement-id AllowEventBridgeAnomalySchedule --profile rag-assistant --region us-east-1` |
| 4 | CloudWatch custom metrics namespace: `RagAssistant/Ops` | Stage 6/7. `InputTokens`, `OutputTokens`, `TokenCount`, `Latency`, `ErrorCount` (all dimensioned by `ModelId` only), plus `TokenUsageAnomaly` from row 1. **11 series maximum** — the ceiling is the model-tier count, not the request count. | Emitted via `cloudwatch.put_metric_data` from Lambda code | **Custom-metric storage bills per metric per month regardless of use** — the one standing cost this practice adds. At ≤11 low-cardinality series it is a few cents/month. See watch-list. | Stop emitting (revert the `generate` code changes below); metrics age out of active-metric billing once no new datapoints are written |

## Existing IAM modified (not new resources)

| # | Role | Statement | Change | To revert |
|---|---|---|---|---|
| 5 | `rag-assistant-lambda-role` | `CloudWatchPutMetrics` | Stage 1. `cloudwatch:namespace` condition widened from the single string `"RagAssistant/Guardrails"` to the list `["RagAssistant/Guardrails", "RagAssistant/Ops", "RagAssistant/BusinessImpact"]`. (`RagAssistant/BusinessImpact` was pre-authorised for the deferred Stage 9 and is currently unused but harmless.) | Restore the condition to the single string |
| 6 | `rag-assistant-lambda-role` | `CloudWatchReadMetrics` | Stage 7. **New statement** — `cloudwatch:GetMetricStatistics`, `GetMetricData`, `ListMetrics`. Note these read APIs **do not support a resource ARN or a `cloudwatch:namespace` condition** (unlike `PutMetricData`), so this is necessarily `Resource: "*"`, scoped to metric reads only. | Delete the statement. Role goes 26 → 25 statements |
| 7 | `rag-assistant-agent-loop-role` | `AgentInvokeModel` | Stage 4. `Resource` widened from Nova Lite only to **Nova Lite + Nova Pro**. Required because `support-agent-loop` runs under this narrower role, not the shared one — see bugs below. | Remove the nova-pro ARN from the `Resource` list |

## Existing Lambdas modified (not new resources)

| Lambda | Stage(s) | What changed |
|---|---|---|
| `generate` (P02) | 4, 6 | Complexity-tiered model selection (`MODEL_TIERS`, `select_tier()`, reading `subQueries` off the workflow output); a direct-invoke-only `tier` override for A/B testing; `_emit_ops_metrics()` publishing token/latency/error metrics to `RagAssistant/Ops`; `generate_answer()` now also returns the Converse `usage` block; `model_tier`/`model_id` added to the response body |
| `support-agent-loop` (P05) | 4 | Complexity-tiered model selection computed once before the tool loop and held fixed across all iterations; `model_tier` added to all three return paths |
| `analyze` (P03) | 8 | `_invoke_with_retry()` now returns `(text, usage)` instead of discarding the `usage` block; `analyze_document()` and the handler carry it through; `input_tokens`/`output_tokens` added to the response body |
| `record-metrics` (P03) | 8 | `PRICING_PER_1K_TOKENS` table added (incl. the new `nova-pro` entry); `estimate_cost()`; writes `input_tokens`/`output_tokens`/`estimated_cost_usd` to `RoutingMetrics` — omitted entirely rather than zeroed when unknown |

`RoutingMetrics` (DynamoDB) gained three new attributes but **no schema change** was needed — it is
schemaless beyond its `request_id` key, and rows written before Stage 8 simply lack the fields.

## Real bugs hit

1. **P01's IAM lesson repeated verbatim.** Routing to nova-pro crashed `support-agent-loop` with
   `AccessDeniedException` on `bedrock:InvokeModel`. I had verified nova-pro access against
   `rag-assistant-lambda-role` — but that Lambda runs under **`rag-assistant-agent-loop-role`**, a
   separate, narrower role P05 scoped to Nova Lite only. Exactly the failure P01 documented
   ("invisible in local testing because that ran under the broad CLI profile, not the Lambda's
   narrow execution role — always test under the real execution role"). Only the live invoke caught
   it. Fixed by row 7.
2. **CloudWatch custom-metric ingestion lag is ~2-3 minutes, not seconds.** Two consecutive live
   anomaly checks returned `no_recent_data` for traffic generated 30s earlier, which read exactly
   like a broken query path. Direct `get_metric_statistics` confirmed the data simply wasn't
   queryable yet. Worth knowing before trusting any "the metric didn't fire" conclusion — and a
   reason an hourly schedule is safe where a per-minute one would race ingestion.
3. **`analyze` was silently discarding the Converse `usage` block**, making per-request cost
   unknowable downstream. Not a crash — just a return statement that kept the text and dropped the
   billing data. Found only by trying to compute cost in Stage 8.

## Standing cost watch-list

Same theme as practices 02-05, carried forward: **CloudWatch custom metrics are the one thing here
that bills for existing, not just for use.** This practice adds one new namespace,
`RagAssistant/Ops` (row 4), at up to 11 low-cardinality series — a few cents/month.

The cardinality discipline is deliberate and is the substance of Stage 6: the bonus assignment's
reference `track_request()` dimensions every metric by `RequestId`, which would mint a **new billable
metric per request** — converting a fixed, negligible cost into an unbounded one that grows with
traffic and never shrinks. Dimensioning by `ModelId` caps the series count at the size of the tier
set. The same fix was applied pre-emptively to the deferred Stage 9 design (dimension by ticket
`category`, never `ConversationId`).

Everything else this practice adds is $0 idle: the new Lambda, the EventBridge rule (free, and
currently disabled anyway), and all the Lambda code changes.

## Final teardown

Work rows 1-4 in order, then revert the IAM changes (rows 5-7) and the Lambda code changes. Do
**not** delete anything owned by practices 02-05: `rag-assistant-lambda-role`,
`rag-assistant-agent-loop-role`, `rag-assistant-project-user`, either API Gateway, the S3 bucket,
`rag-assistant-kb-2`, or the `RoutingMetrics`/`SupportTickets`/`RagQueryCache` tables. For IAM,
remove only the specific statements/conditions listed in rows 5-7; don't delete the policies
themselves. The four Lambda modifications are code changes, not resources with a delete command —
revert them from git if a full rollback to pre-practice-06 behaviour is wanted.

`RoutingMetrics` rows written during this practice carry extra attributes; they're harmless to
leave, and removing them means deleting rows, not altering a schema.

---

_Part of [Gen AI Practice](../README.md)._
