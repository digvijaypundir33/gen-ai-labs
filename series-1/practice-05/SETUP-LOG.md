# Setup Log — Practice 05

Everything actually created on AWS for this practice, in the order it was created, with what it
costs and how to delete it again. **Region: us-east-1** throughout.

This project reuses practice-02/04's foundational infrastructure — the shared IAM role
(`rag-assistant-lambda-role`), the CLI user/profile (`rag-assistant-project-user` /
`rag-assistant`), both API Gateways, the S3 bucket, the Step Functions role
(`rag-assistant-stepfunctions-role`), the Knowledge Base (`rag-assistant-kb-2`), and the
`SupportTickets` DynamoDB table — rather than provisioning anything foundational from scratch.
Stage 0 was a live audit confirming all of that was still active before touching anything.

**Status:** Stages 0-12, 14 built and verified live; Stage 13 skipped. Everything still running —
and unlike practices 02-04, nothing here is a standing/idle cost (see the README's Cost section).

## New resources created

| # | Resource | Notes | Made with | Cost while it exists | To delete |
|---|---|---|---|---|---|
| 1 | Bedrock Guardrail: `rag-assistant-guardrail` (`5jk3sefhtv16`) | Stage 1, tuned through Stages 3/7. Content filters, denied topics, PII policy, prompt-attack detection, contextual grounding. 5 published versions (v3 is a dead publish from a failed `update-guardrail` call — see bugs #3; v4/v5 are the real, live-tuned versions). | CLI (`bedrock create-guardrail`/`create-guardrail-version`) | ~$0.15/1,000 text units for content/PII/prompt-attack policies, ~$0.10/1,000 text units for contextual grounding — pay-per-invocation, $0 idle | `aws bedrock delete-guardrail --guardrail-identifier 5jk3sefhtv16 --profile rag-assistant --region us-east-1` |
| 2 | IAM policy statement: `BedrockApplyGuardrail` | Stage 2. Widened `rag-assistant-lambda-role` — `bedrock:ApplyGuardrail` scoped to the guardrail ARN, needed for both standalone `apply_guardrail` calls and inline `guardrailConfig` on `Converse`. | CLI (`iam put-role-policy`) | Free | Remove this statement from the role's inline `Policy` |
| 3 | IAM policy statement: `ComprehendPii` | Stage 4, widened in Stage 6. `comprehend:DetectPiiEntities` (Stage 4), then `comprehend:DetectSentiment` added (Stage 6) for `moderation-risk-check`. | CLI (`iam put-role-policy`) | Free | Remove this statement |
| 4 | Lambda: `moderation-risk-check` | Stage 6. Cheap first-pass Comprehend sentiment+PII risk scoring for the (not-deployed) tiered moderation workflow. | CLI (`lambda create-function`) | $0 idle, pay-per-invocation | `aws lambda delete-function --function-name moderation-risk-check --profile rag-assistant --region us-east-1` |
| 5 | Lambda: `moderation-llm-check` | Stage 6, schema-validated in Stage 8. LLM-based harm classification, only reached on MEDIUM/HIGH risk. `jsonschema`-validated, fail-closed. | CLI | $0 idle | `aws lambda delete-function --function-name moderation-llm-check --profile rag-assistant --region us-east-1` |
| 6 | Lambda Layer: `jsonschema-layer` | Stage 8. `jsonschema` + pinned deps (`referencing==0.35.1`, `rpds-py==0.20.0`, `attrs==24.2.0`) — later `referencing` releases require Python 3.13+ typing syntax, incompatible with this function's `python3.12` runtime (bugs #6). Version 1 is broken/unused; version 2 is live. | CLI (`lambda publish-layer-version`) | No separate charge — bundled into function deployment size | `aws lambda delete-layer-version --layer-name jsonschema-layer --version-number 2 --profile rag-assistant --region us-east-1` (and `--version-number 1` for the broken one) |
| 7 | Step Functions state machine: `moderation-workflow` (Express) | Stage 6. `AnalyzeContent` → Choice → `ModerateContent` (shared by both MEDIUM/HIGH branches, fixing the assignment's reference-CDK state-reuse bug) → `ModerationDecision` → Approve/Reject. Built and measured, **deliberately not wired into the live request path** — see README Stage 6. | CLI (`stepfunctions create-state-machine`) | $1.00/1M requests + duration — $0 idle | `aws stepfunctions delete-state-machine --state-machine-arn arn:aws:states:us-east-1:156207843797:stateMachine:moderation-workflow --profile rag-assistant --region us-east-1` |
| 8 | IAM policy update: `rag-assistant-stepfunctions-role` `LambdaInvoke` | Stage 6. Widened to add `moderation-risk-check`/`moderation-llm-check` ARNs. | CLI | Free | Remove the two ARNs from the statement's `Resource` list |
| 9 | Lambda: `crm-agent-actions` | Stage 10. Thin adapter speaking the Bedrock Agent action-group protocol natively, reading/writing the same `SupportTickets` table `crm-mock-update`/`get-ticket` already use — built as a new Lambda rather than modifying those, to avoid any risk to P04's already-verified Step-Functions/API-Gateway-shaped event handling. Two functions: `get_ticket_status`, `update_ticket_priority`. | CLI | $0 idle | `aws lambda delete-function --function-name crm-agent-actions --profile rag-assistant --region us-east-1` |
| 10 | Lambda resource policy: `AllowBedrockAgentInvoke` on `crm-agent-actions` | Stage 10. Grants `bedrock.amazonaws.com` invoke permission — added for a classic Bedrock Agent action group before discovering Classic Agents is blocked for this account (see README Stage 10). **Vestigial**: `support-agent-loop` invokes this Lambda directly via its own IAM role, not via Bedrock's service-linked invocation, so this permission is currently unused but harmless (scoped to this account only). | CLI (`lambda add-permission`) | Free | `aws lambda remove-permission --function-name crm-agent-actions --statement-id AllowBedrockAgentInvoke --profile rag-assistant --region us-east-1` |
| 11 | IAM role: `rag-assistant-agent-loop-role` | Stage 10. Trust: `lambda.amazonaws.com`. Permissions: `bedrock:InvokeModel` (Nova Lite), `bedrock:Retrieve` (KB), `lambda:InvokeFunction` (`crm-agent-actions`), `bedrock:ApplyGuardrail`. **Note:** an earlier role, `rag-assistant-agent-role`, was created first with `bedrock.amazonaws.com` trust for the (blocked) classic Agent attempt, then deleted outright rather than repurposed — `iam:UpdateAssumeRolePolicy` on a role this CLI user itself created was denied (a real, consistent self-escalation restriction, hit again in Stage 14), so a clean delete + recreate was the only path. | CLI (`iam create-role` + `put-role-policy` + `attach-role-policy` for `AWSLambdaBasicExecutionRole`) | Free | `aws iam detach-role-policy` (basic execution) + `aws iam delete-role-policy` (inline) + `aws iam delete-role --role-name rag-assistant-agent-loop-role` |
| 12 | Lambda: `support-agent-loop` | Stage 10. Hand-rolled Converse tool-use loop (3 tools: `search_knowledge_base`, `get_ticket_status`, `update_ticket_priority`), self-logged trace, inline `guardrailConfig`. Built after Classic Bedrock Agents was found blocked and AgentCore was evaluated and found not worth its adoption cost for this scope. | CLI | $0 idle | `aws lambda delete-function --function-name support-agent-loop --profile rag-assistant --region us-east-1` |
| 13 | IAM policy statement: `CloudWatchPutMetrics` | Stage 11. Widened `rag-assistant-lambda-role` — `cloudwatch:PutMetricData` scoped via a `cloudwatch:namespace` condition to `RagAssistant/Guardrails` only. | CLI | Free | Remove this statement |
| 14 | CloudWatch custom metrics namespace: `RagAssistant/Guardrails` | Stage 11. `GuardrailAction` (dimensioned by action type) and `GroundingScore`, emitted from `generate` on every request. No dashboard built (Stage 13 skipped) — the data is live in CloudWatch if picked up later. | Emitted via `cloudwatch.put_metric_data` from Lambda code | Metric ingestion is free at this volume; **custom-metric storage bills per metric per month regardless of use** — the one real standing-cost risk in this practice, see watch-list below | Stop emitting (revert the Lambda code) — metrics with no new data points age out of the free tier's active-metric billing after they stop being written |
| 15 | SageMaker Model Card: `rag-assistant-support-system` | Stage 14. Documents the whole system, including the Stage 12 retraction and the Stage 6 workflow that was evaluated and not deployed. Status: `Approved`. | CLI (`sagemaker create-model-card` + `update-model-card`) | Free — no compute/storage provisioned, it's pure metadata | `aws sagemaker delete-model-card --model-card-name rag-assistant-support-system --profile rag-assistant --region us-east-1` |
| 16 | IAM user policy: `SageMakerModelCardAccess` | Stage 14. Added manually via console to `rag-assistant-project-user` (the CLI user couldn't grant this to itself — bugs #11) — `sagemaker:CreateModelCard`/`UpdateModelCard`/`DescribeModelCard`/`DeleteModelCard`/`ListModelCards`/`ListModelCardVersions`, scoped to `model-card/*`. | Console (user-granted) | Free | Remove the inline policy from `rag-assistant-project-user` via IAM console |

## Existing Lambdas modified (not new resources)

| Lambda | Stage(s) | What changed |
|---|---|---|
| `generate` (P02) | 2, 3, 7, 11 | Guardrail input check + inline `guardrailConfig`, softened prompt template, `guardContent` qualifiers for grounding, `confidence`/CloudWatch metrics |
| `ticket-generate-response` (P04) | 2 | Standalone `apply_guardrail` on both sides of the Prompt Flow call |
| `ticket-submit` (P04) | 4 | Comprehend PII masking before the `SupportTickets` write |
| `query_router` / `query-router` (P02) | 4 | Comprehend PII masking on the cached query text before the `RagQueryCache` write |
| `ws_ask` / `ws-ask` (P02) | 11 | Full guardrail wiring added from scratch (input check, inline `guardrailConfig`, grounding, retract-on-block, robust error handling) — this Lambda had **none** of Stage 2/3/7's protection before Stage 11 |

## Standing cost watch-list

Same watch-list theme as practices 02-04, carried forward: **CloudWatch custom metrics are the one
thing in this account that bills for existing, not just for use.** `RagAssistant/Guardrails`
(row 14) is the only new standing item this practice adds, and at two low-cardinality metrics it's
negligible, but it's the one line item here that isn't purely pay-per-invocation like everything
else. Everything else genuinely new in this practice (the Guardrail, Comprehend, the Lambda Layer,
the Express state machine, the SageMaker Model Card) is either free or billed strictly
per-invocation with zero idle cost, confirmed with real figures in the README's Cost section.

## Final teardown

Work the delete column bottom-to-top (row 16 → row 1) — newest/most-dependent resources first.
Do **not** delete anything owned by practices 02-04: `rag-assistant-lambda-role`,
`rag-assistant-project-user`, `rag-assistant-stepfunctions-role`, either API Gateway, the S3
bucket, `rag-assistant-kb-2`, or `SupportTickets` — those remain practice-02/04's to manage. When
reverting IAM, remove only the specific statements listed in rows 2, 3, 8, 13 from
`rag-assistant-lambda-role`'s/`rag-assistant-stepfunctions-role`'s inline policies; don't delete
the policies themselves. Also revert the five existing-Lambda modifications listed above if a full
rollback to pre-practice-05 behavior is wanted — those are code changes, not resources with a
delete command.

---

_Part of [Gen AI Practice](../README.md)._
