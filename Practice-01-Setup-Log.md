# Practice 01 — Build Log & Cleanup Checklist

Everything I actually created on AWS for [Practice 01](./Practice-01-Resilient-Multi-Model-Bedrock-Assistant.md),
roughly in the order I created it, with what it cost and how to delete it again. I'm keeping
this mostly so that when I'm done experimenting I can tear the whole thing down without
missing something — the Cleanup column is meant to be run top to bottom at the end.

Region: **us-east-1** throughout. I skipped the cross-region part of the design (see the main
write-up), so nothing lives in a second region.

## Everything created

| # | Resource | Notes | Made with | Cost while it exists | To delete |
|---|---|---|---|---|---|
| 1 | IAM user | `ai-assistant-project-user` — scoped policies: `AmazonBedrockFullAccess`, `AWSLambda_FullAccess`, `AmazonAPIGatewayAdministrator`, `AWSStepFunctionsFullAccess`, `AWSCloudFormationFullAccess`, plus an inline policy for `iam:*Role` scoped to `ai-assistant-*` role names. Made this instead of using my admin login so I could tear the whole project down without touching anything else in the account. | IAM console | Free | IAM → Users → delete `ai-assistant-project-user` (remove access keys + attached policies first) |
| 2 | CLI profile | `ai-assistant` profile, region `us-east-1`. Local only, not an AWS resource. | `aws configure --profile ai-assistant` | Free | Remove the `[ai-assistant]` blocks from `~/.aws/credentials` and `~/.aws/config` by hand |
| 3 | Bedrock model access | Turns out the old manual "Model access" page is gone — models auto-enable on first invocation now, account-wide. Nothing to actually set up here. | automatic | Free | nothing to clean up |
| 3a | IAM policy fix | Found out `AmazonBedrockFullAccess` and a few other policies I thought I'd attached in step 1 hadn't actually stuck — only the inline role policy had landed. Had to go back and re-attach them properly. | IAM console | Free | covered by row 1's cleanup |
| 3b | IAM inline policy for AppConfig | There's no attachable managed policy for AppConfig at all — searching for one only turns up a reserved service-linked-role policy you can't put on a regular user. Added a custom inline policy instead (`appconfig:*`). Also worth noting: `appconfigdata:*` isn't a real IAM action namespace, even though it's a separate boto3 client — both the control-plane and data-plane AppConfig actions live under plain `appconfig:`. IAM's own policy validator told me this when it rejected my first attempt. | IAM console | Free | covered by row 1 |
| 3c | Settled on a real model lineup | `amazon.nova-micro-v1:0`, `amazon.nova-lite-v1:0`, and `us.anthropic.claude-haiku-4-5-20251001-v1:0` — the last one needs its cross-region inference profile ID, the bare model ID gets rejected. Titan Text Express, which the assignment actually tells you to use, is fully retired now (`ResourceNotFoundException`). | `aws bedrock-runtime converse` test calls | ~$0.01 in test calls | nothing to delete, these are just model IDs |
| 4 | Benchmarking script | `practice-01/benchmark_models.py`, running in its own venv inside `practice-01/` — kept it separate from my Anaconda base environment after a numpy/pyarrow version conflict showed up there. Outputs `model_evaluation_results.csv` and `model_selection_strategy.json`. | written together, run locally | free, local only | delete the `practice-01/` folder if you want, no AWS resource involved |
| 4a | Part 1 results | Nova Micro and Nova Lite both worked fine — around 2.3-2.6s latency, well under a tenth of a cent per request. Claude Haiku was blocked the whole time: first a `ResourceNotFoundException` about a use-case form, then after going through the Playground, an `AccessDeniedException` about a missing payment instrument (Anthropic models go through an AWS Marketplace subscription that needs its own valid payment method — separate from general account billing, and something Amazon's own Nova models don't need at all). Decided to move on with the 2 working models and add Claude back later. | local script run | ~$0.02 total | n/a |
| 5 | AppConfig application | `oxbb9l1` ("AIAssistantApp") | `aws appconfig create-application` | free at this scale | `aws appconfig delete-application --application-id oxbb9l1 --profile ai-assistant --region us-east-1` — also removes its environment and profile |
| 5a | AppConfig environment | `3zvv85d` ("Production") | `aws appconfig create-environment` | included above | goes with row 5 |
| 5b | AppConfig configuration profile | `3vjasfk` ("ModelSelectionStrategy"), type `AWS.Freeform` — the assignment's example uses `AWS.AppConfig.FeatureFlags`, which expects a different schema and isn't right for plain config like this | `aws appconfig create-configuration-profile` | included above | goes with row 5 |
| 5c | First hosted config version + deployment | Version 1 = the Part 1 strategy (primary `amazon.nova-micro-v1:0`, fallback `amazon.nova-lite-v1:0`), deployed with the `AppConfig.AllAtOnce` strategy | CLI | included above | goes with row 5 |
| 6 | Lambda execution role | `ai-assistant-lambda-execution-role` — basic Lambda logging plus an inline policy scoped to exactly the model/inference-profile ARNs I'm using, and `appconfig:*` | `aws iam create-role` / `put-role-policy` | free | detach + delete the role policies, then delete the role |
| 7 | model-abstraction Lambda | `ai-assistant-model-abstraction`, Python 3.12. Reads the AppConfig strategy, invokes Bedrock, raises on failure instead of swallowing the error (the reference code returns an error string as a 200, which quietly breaks Step Functions' fallback logic later). Test-invoked and got a real Nova Micro response back. | `aws lambda create-function` | free at this scale | `aws lambda delete-function --function-name ai-assistant-model-abstraction ...` |
| 7a | REST API + resource + method | `AIAssistantAPI` (`48njmlr1zk`), `/generate` (`dptga5`), `POST`, with `apiKeyRequired: true` | CLI | free | `aws apigateway delete-rest-api --rest-api-id 48njmlr1zk` — takes everything under it with it |
| 7b | Lambda integration + deploy | Pointed at `ai-assistant-model-abstraction`, deployed to a `prod` stage. Did this part through the console, which handles the Lambda invoke permission automatically when you save the integration. | API Gateway console | included above | goes with 7a |
| 7c | Usage plan + API key | `AIAssistantUsagePlan` linked to the `prod` stage, plus an API key. Ended up rotating the key once — the value got pasted into chat during troubleshooting, not because anything was actually wrong with it. | API Gateway console | free | delete the usage plan (detaches the key), then delete the key |
| 7d | Bug I found: AppConfig + warm Lambdas | `get_latest_configuration` returns empty content when nothing's changed since the last poll — that's documented, expected behavior, not an error. But my Lambda caches its polling token across warm invocations, and my first version treated that empty response as a failure. Cold start worked fine; every single call after that returned a 502. Found this by accident, using the API Gateway console's Test button while chasing an unrelated API-key issue — that button skips auth entirely, which is exactly what let this bug surface. Fixed by caching the last good config and only erroring if nothing's ever been cached. | found via console Test, fixed via redeploy | n/a | n/a |

**On the API key `Forbidden` issue:** I never actually found the root cause. Everything checked
out — key enabled, correctly linked to the usage plan, usage plan scoped to the right stage, no
resource policy in the way. Best guess is a propagation delay specific to EDGE/CloudFront-fronted
APIs, since it started working with no further changes once enough time had passed.

| # | Resource | Notes | Made with | Cost while it exists | To delete |
|---|---|---|---|---|---|
| 8 | DynamoDB table | `ai-assistant-circuit-breaker`, partition key `breaker_id`, On-Demand billing specifically so it doesn't cost anything while idle | DynamoDB console | $0 idle | `aws dynamodb delete-table --table-name ai-assistant-circuit-breaker ...` |
| 8a | Execution role update | Added `dynamodb:GetItem`/`PutItem` (scoped to the table above) to the same role from row 6, rather than making a new one per function | `aws iam put-role-policy` | free | goes with row 6 |
| 9 | circuit-breaker Lambda | `ai-assistant-circuit-breaker`, Python 3.12. Tracks CLOSED/OPEN/HALF_OPEN per *role* (primary/fallback), not per model ID — the model behind a role can change via AppConfig, but the question "has this slot been failing" stays meaningful regardless. 3 failures to open, 60s cooldown before a half-open trial. | Lambda console, reused role from row 6 | free at this scale | `aws lambda delete-function --function-name ai-assistant-circuit-breaker ...` |
| 10 | graceful-degradation Lambda | `ai-assistant-graceful-degradation`, canned safe responses, no AWS calls beyond logging | Lambda console, same role | free at this scale | `aws lambda delete-function --function-name ai-assistant-graceful-degradation ...` |
| 10a | model-abstraction Lambda update | Added an `attempt` field (primary/fallback) so Step Functions can call the same Lambda for both attempts; handler now accepts both API Gateway's proxy shape and a direct Step Functions invocation | Lambda console inline editor | included in row 7 | goes with row 7 |
| 11 | Step Functions state machine | `ai-assistant-resilience-workflow`, Express type (needed for the synchronous API Gateway call later). Pasted the whole thing as raw ASL rather than clicking through Workflow Studio state by state — too many fiddly fields to risk typing them all in one at a time. Execution role auto-generated by the console based on which Lambdas the definition references. | Step Functions console | bills per invocation, $0 idle | delete the state machine, and probably the auto-generated execution role too (named something like `StepFunctions-ai-assistant-resilience-workflow-role-*`) |
| 11a | Proved the circuit breaker actually works | Deliberately deployed a broken `primary_model` via AppConfig to force failures. First 3 runs: primary fails, gets caught, fallback picks it up, real answer every time. 4th run, after the failure count crossed the threshold: the breaker was open, and the execution graph shows it skipping the primary attempt entirely, straight to fallback. Reverted the config, waited out the cooldown, ran it again — one half-open trial, success, back to closed. Full lifecycle, actually observed, not just assumed from reading the code. | Step Functions console, AppConfig console | ~$0.02 in test calls | n/a |
| 12 | IAM role for API Gateway → Step Functions | `ai-assistant-apigw-sfn-role`, trusts `apigateway.amazonaws.com`, scoped to `states:StartSyncExecution` on just this one state machine | `aws iam create-role` / `put-role-policy` | free | delete the role policy, then the role |
| 13 | API Gateway rewired to Step Functions | Changed the `/generate` integration from Lambda-proxy to a direct AWS Service integration calling Step Functions' `StartSyncExecution`. Needed a Method Response (200) added first — proxy integrations don't need one, so it didn't exist yet. Request/response VTL mapping templates convert between the client's JSON and what Step Functions expects. Hit the classic `$util.escapeJavaScript` bug where apostrophes turn into an invalid `\'` — fixed with `.replaceAll("\\'","'")` on both templates. Confirmed working end to end with a real curl request, including a response that had an apostrophe in it. | API Gateway console | included in row 7a | switch the integration back to Lambda-proxy, or just delete the whole API during teardown |

### Billing guard
- [x] AWS Budget set up

## What I skipped

- Cross-region CloudFormation + Route 53 failover — this was the one part of the design with
  a genuine recurring cost (a hosted zone and health checks bill monthly regardless of use),
  and I'd already proven the resilience story with the circuit breaker, so I left it as
  documented-only.
- SageMaker fine-tuning / endpoint for Part 4 — a deployed endpoint bills hourly whether you're
  using it or not, which is the one real "forgot about it, got a bill" risk in this whole
  project. Also, as covered in the main write-up, the reference's own SageMaker approach
  doesn't even connect to the Bedrock-based architecture I actually built. Documented only.
- Adding Claude Haiku back into the benchmark — still blocked on the AWS Marketplace payment
  method issue above. Will come back to this once that's sorted.

## Final teardown

When I'm actually done with this project, work through the delete column above, roughly bottom
to top (newest/most-dependent resources first), then double-check in the console that Lambda,
API Gateway, Step Functions, DynamoDB, AppConfig, and IAM are all actually clear — nothing here
uses CloudFormation, so there's no single stack delete that sweeps everything at once.
