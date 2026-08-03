# Practice 03 — Resilient Document Analysis Pipeline

Five capabilities built on Amazon Bedrock: a synchronous analysis API, an asynchronous SQS
pipeline for large documents, real-time WebSocket streaming, a resilience layer (retry/backoff +
circuit breaker + X-Ray), and intelligent Step Functions-based model routing. Reference spec:
[ASSIGNMENT.md](./ASSIGNMENT.md).

## Why this reuses Practice 02's infrastructure instead of starting fresh

This project deliberately does **not** stand up its own IAM user, Lambda execution role, or API
Gateways. [Practice 02](../practice-02/README.md)'s
`rag-assistant-project-user`, `rag-assistant-lambda-role`, `rag-assistant-api` (REST), and
`rag-assistant-ws-ap` (WebSocket) are all still live, so Stage 1 was a live audit confirming that,
followed by adding new routes/resources on top of them and widening the shared role's inline
policy incrementally — the same "widen exactly when a stage needs it" pattern practice-02 used for
its own Stage 7/8 additions. Only genuinely new resources (DynamoDB table, SQS queue/DLQ, SNS
topic, five new Lambdas) get created from scratch. See
[SETUP-LOG.md](./SETUP-LOG.md) for the full resource-by-resource record.

## Cost

Every service this project touches — Lambda, API Gateway (REST + WebSocket), DynamoDB On-Demand,
SQS, SNS, X-Ray, and (once built) Step Functions — is pay-per-use with **$0 idle cost**, including
the two services genuinely new to this series. X-Ray's 100,000 recorded / 1,000,000 retrieved
traces per month are free *permanently*, not just for new accounts, and at this project's request
volume every invocation falls within X-Ray's default 1-req/sec sampling reservoir, so it traces
effectively 100% of calls while staying nowhere near the free-tier ceiling. SQS's 1M free
requests/month is likewise permanent. The only standing cost risk in the whole account remains the
one already on practice-02's watch-list: CloudWatch custom metrics/dashboards, which bill monthly
just for existing — not used here.

## Build stages

### Stage 1 — Live audit (confirmed, no new resources)

Verified every practice-02 resource this project plans to build on top of was still active before
touching anything: the shared IAM role (all 8 inline-policy statements intact at the time), both
API Gateways, the S3 bucket, the Step Functions role, and all 10 existing Lambdas. Nothing had
drifted or been torn down.

### Stage 2 — Synchronous document analysis API (Part 1, built and verified live)

New `analyze` Lambda + new `/analyze` route on the existing REST API, routing to Nova Lite (legal,
technical) or Nova Micro (general, feedback) — a working substitute for the reference's hardcoded
`anthropic.claude-v2`/`amazon.titan-text-express-v1` pair, both of which are dead models.

The real addition here is **API Gateway request validation** — a JSON Schema model requiring
`document` (min length 10) and an optional `type` enum, attached via a request validator on the
`POST` method. Verified this actually rejects bad input *before* the Lambda runs, not just that the
Lambda itself checks its input: three different invalid requests (missing `document`, an invalid
`type` value, a too-short `document`) all came back `400` from API Gateway directly, and
CloudWatch Logs confirmed zero Lambda invocations for any of them — only the one valid request
produced an invocation.

One real bug on the way: `create-deployment` reported success instantly, but the new route wasn't
actually live for several seconds afterward — confirmed by retrying while `/ask` (already deployed)
kept working the whole time as a control. Propagation delay, not a config error — see bugs table
#1.

### Stage 3 — Resilience layer (Part 4, built and verified live)

Wrapped `analyze`'s Bedrock calls with retry/backoff on `ThrottlingException`, a DynamoDB-tracked
circuit breaker (`ModelCircuitBreaker` table), a distinct fallback model (`amazon.nova-pro-v1:0`,
deliberately different from the `nova-lite`/`nova-micro` already used for type-routing, so the
fallback path is actually testable), and X-Ray active tracing on both the Lambda and the API
Gateway stage.

All three circuit-breaker states proven against real infrastructure, not just read from the code:
closed (uses primary model), forced-open (immediately falls back), and cooldown-expired
(half-open — lets one trial request through to the primary, and correctly resets state on
success). Retry/backoff verified separately via a mocked throttling client (2 throttled calls,
correct exponential delay, success on the 3rd). X-Ray confirmed capturing real traces via
`get-trace-summaries`.

Two real bugs found and fixed here — see bugs table #2 and #3 — including one in my own code
(a `Decimal`/`float` `TypeError` from DynamoDB's number type) and one IAM gap (the fallback model
was never granted `InvokeModel`, caught only because the actual Lambda execution role — not the
broader CLI testing profile — was used for the live test).

### Stage 4 — Asynchronous processing pipeline (Part 2, built and verified live)

New `/analyze-async` route → `analyze-producer` Lambda (always queues; Part 1's `/analyze` already
covers the synchronous case, so this endpoint's entire job is demonstrating the async path, rather
than re-implementing the reference's incomplete `pass`-stub sync branch) → SQS
(`document-analysis-queue`, with a DLQ after 3 failed attempts) → `analyze-consumer` Lambda
(SQS-triggered, batch size 1, reuses Stage 3's exact resilience logic) → result written to
`analysis-results/{job_id}.json` in the existing S3 bucket → SNS notification.

Verified fully end-to-end live: `POST /analyze-async` → `202` + `job_id` → queue automatically
drains to 0 (both visible and in-flight, meaning the consumer processed *and* deleted the message,
which only happens if the whole function — including the SNS publish at the end — completed
without error) → correct analysis in S3 with the right model routing.

Two real things hit — bugs table #4 and #5: AWS's hard 10-managed-policies-per-IAM-user quota (hit
while trying to grant the CLI user SQS/SNS access for local testing — fixed with an inline policy
instead, which doesn't count against that quota), and a second, longer round of the same
propagation-delay behavior from Stage 2 (this time ~25-30 seconds rather than a few).

### Stage 5 — Real-time streaming (Part 3, built and verified live)

New `analyze-stream` Lambda + new `analyze` route on the *existing* WebSocket API (reused directly
from practice-02 Stage 8 — its `$connect`/`$disconnect` no-ops needed no changes at all, since
this is single-request/single-response streaming, not broadcast). Combines Stage 3's resilience
logic with practice-02 Stage 8's `converse_stream` + `post_to_connection` pattern. As predicted
when the reuse plan was first mapped out, this stage needed **zero new IAM** — `ManageConnections`
and `InvokeModelWithResponseStream` were already granted from earlier stages.

Verified live over a real `wss://` connection: both the normal streaming path and the
forced-circuit-open fallback path, confirmed with real per-token output (183 tokens for the
production test).

Two real, non-trivial bugs here — bugs table #6 and #7 — both invisible from reading the code and
only found by comparing against the known-working `ask` route byte-for-byte: the console created
this route's integration as **non-proxy** (`AWS` instead of `AWS_PROXY`) with a stale
content-handling override, requiring the integration to be deleted and recreated from scratch
rather than patched; and the WebSocket API's `prod` stage has **`AutoDeploy` off**, meaning every
route/integration change made today — including the original console-created route — was never
actually live until an explicit deployment was pushed. This is the WebSocket-API equivalent of the
REST API propagation delay from Stages 2/4, except here nothing takes effect *at all* without it,
not just a delay.

### Stage 6 — Intelligent model routing (Part 5, built and verified live)

A Step Functions workflow: `classify-document` (Nova Micro infers the document's type and a
length-based complexity score) → `ProcessDocument` (reuses the existing `analyze` Lambda directly,
rather than duplicating the reference's 4 near-identical processor Lambdas — `analyze` already
does its own type-based model routing internally) → `record-metrics` (writes type, complexity,
model used, and classification time to a new `RoutingMetrics` table). A new `analyze-router`
Lambda fronts it: calls `start_sync_execution()` and returns the whole result as one response.

The distinct value here versus Part 1's `/analyze`: that endpoint trusts whatever `type` the
*caller* states. This one has the system classify the document itself — no caller has to already
know or declare what kind of document it's looking at.

**Chose Express over Standard deliberately** — unlike practice-02's `rag-query-workflow` (which
needed Standard for its Map-state fan-out over sub-questions), this workflow is strictly linear,
which is exactly the shape Express's synchronous `StartSyncExecution` fits best: one blocking call,
no start-and-poll loop needed in the front-door Lambda.

Verified live for two different document types (technical, legal), both correctly classified and
routed, with the resulting `RoutingMetrics` row confirmed directly in DynamoDB — not just trusting
the API response.

One real, non-obvious bug getting the state machine created at all — bugs table #8: Express
workflows *require* CloudWatch Logs (they have no separate execution-history API the way Standard
does), and the reused `rag-assistant-stepfunctions-role` had never been granted the specific
`logs:CreateLogDelivery`/`GetLogDelivery`/`UpdateLogDelivery`/etc. permission set this needs — a
different, more specific set than ordinary `logs:CreateLogStream`/`PutLogEvents`. The error
(`AccessDeniedException: The state machine IAM Role is not authorized to access the Log
Destination`) gives no hint of which specific actions are missing.

### Stage 7 — Retrofitting resilience onto Practice 02's retrieval path (built and verified live)

The first six stages built new capabilities alongside Practice 02's RAG pipeline, reusing its
infrastructure but never actually changing its behavior. This stage is different: it modifies
Practice 02's own `search` Lambda — the thing that's actually running in production, not a new
parallel Lambda — because the gap it fixes is a real one. `search`'s `bedrock_agent_runtime
.retrieve()` call had **zero resilience**: no retry, no circuit breaker, nothing. If the Knowledge
Base API throttled or errored, the whole Lambda crashed with an unhandled exception, taking down
the entire query with it.

Applied Stage 3's exact pattern (retry/backoff on throttling, DynamoDB-tracked circuit breaker,
graceful degradation) directly to `retrieve_chunks()`, reusing the same `ModelCircuitBreaker` table
Stage 3 already built — under a sentinel key (`bedrock-kb-retrieve`) rather than a model ID, since
the table's schema (`circuit_open`/`failure_count`/`last_failure`) is generic enough to track any
resource's health, not just a Bedrock model's. `search`'s execution role already had both
`bedrock:Retrieve` and the `CircuitBreakerAccess` statement from Stage 3 (it shares
`rag-assistant-lambda-role` with every other Lambda in this project) — **zero new IAM needed**.

One deliberate scope decision: on an open circuit or exhausted retries, this degrades to an
**empty result set**, not a secondary retrieval strategy (e.g. a BM25 fallback). Practice 02's
`generate` Lambda already handles zero chunks correctly — it says "I don't have enough
information" rather than guessing — so failing to an empty list composes cleanly with behavior
that already existed, rather than building a whole parallel retrieval mechanism for a failure mode
this account has never actually hit in practice.

Verified live end-to-end through the real deployed pipeline, not just the modified Lambda in
isolation: a normal query returns the correct grounded answer with sources as before; forcing the
circuit open via DynamoDB and asking a **genuinely new** question (first attempt accidentally
reused an already-cached query, which returned the correct cached answer without ever touching
retrieval at all — a good reminder that `query-router`'s cache sits in front of anything this stage
changes) correctly degrades to "I don't have enough information in the knowledge base to answer
that," with empty sources, instead of crashing.

This change is recorded here rather than in Practice 02's docs, since the motivation and design
came from this project — but Practice 02's setup log and Stage 5 write-up both carry a one-line
pointer back here, so anyone reading them isn't misled into thinking `search` is still the
original unprotected implementation.

### Testing it end to end (a local UI)

One self-contained page (`practice-03/ui/index.html`, same style as practice-02's) covering all
four request paths behind a single mode switcher: Sync, Async, Streaming, Smart routing. Smart
routing hides the type dropdown entirely, since the whole point is that the system infers it. The
async mode needed one small addition to be genuinely testable from a browser: a new
`get-analysis-result` Lambda + `GET /analyze-async/{job_id}` route, since the result otherwise only
ever lands in S3 with no way for a UI to check it.

Two more real bugs surfaced getting this working — bugs table #9 and #10 — one a browser-specific
quirk, one a genuinely interesting piece of S3 IAM behavior worth knowing regardless of this
project.

---

## Bugs found

| # | Where | Issue → fix |
|---|---|---|
| 1 | API Gateway deployment, Stage 2 (mine) | `create-deployment` reported success instantly but the new `/analyze` route returned `Missing Authentication Token` (API Gateway's actual "route not found on this stage" error) for several seconds afterward. Confirmed via a working control (`/ask`, already deployed, responding correctly throughout) that this was propagation delay, not a config error → retried after a short wait |
| 2 | `analyze` Lambda, Stage 3 (mine) | `TypeError: unsupported operand type(s) for -: 'float' and 'decimal.Decimal'` in the circuit-breaker cooldown check. DynamoDB's boto3 resource API returns numeric attributes as `Decimal`, not native Python types, so `time.time() - item['last_failure']` fails → cast with `int()` on read |
| 3 | IAM, Stage 3 (mine) | Live test of the forced-fallback path failed: `AccessDeniedException` on `bedrock:InvokeModel` for `amazon.nova-pro-v1:0` — the new fallback model was never granted access (only `nova-micro`/`nova-lite` were, from practice-02). Local testing hadn't caught this because it ran under the broad `rag-assistant` CLI profile (`AmazonBedrockFullAccess`), not the Lambda's actual narrow execution role — the gap only surfaces under the real deployed permissions → widened `BedrockNovaInvoke`'s resource list |
| 4 | IAM, Stage 4 (mine) | `LimitExceeded: Cannot exceed quota for PoliciesPerUser: 10` when attaching `AmazonSQSFullAccess`/`AmazonSNSFullAccess` to the CLI user — already at exactly 10 managed policies. Inline policies don't count against this quota → granted `sqs:*`/`sns:*` scoped to the specific new resource ARNs as an inline policy instead (same pattern as the pre-existing `S3VectorsAccess` inline policy) |
| 5 | API Gateway deployment, Stage 4 (mine) | Same propagation-delay behavior as #1, but longer this time (~25-30 seconds vs. a few) — confirms the delay is genuinely variable, not a fixed short constant |
| 6 | WebSocket API integration, Stage 5 (mine, or the console) | The `analyze` route's integration was created as `AWS` (non-proxy) with a stale `ContentHandlingStrategy: CONVERT_TO_TEXT` override, causing every invocation to fail with `KeyError: 'requestContext'` since the raw WebSocket event never reached the Lambda in proxy shape. `update-integration` couldn't clear the content-handling override once set (empty string was silently ignored) → deleted the integration and created a fresh one matching the known-working `ask` route's exact shape, then repointed the route at it |
| 7 | WebSocket API stage, Stage 5 (mine) | Even after fixing #6, invocations still failed identically. Root cause: the API's `prod` stage has `AutoDeploy: null` (off) — none of today's route/integration changes, including the *original* console-created route, were ever actually deployed to the live stage. This is the WebSocket-API equivalent of the REST API propagation delay (#1, #5), except here changes don't take effect *at all*, not just after a delay, without an explicit `create-deployment` + `update-stage` |
| 8 | Step Functions IAM role, Stage 6 (mine) | Creating the `document-routing-workflow` Express state machine failed: `AccessDeniedException: The state machine IAM Role is not authorized to access the Log Destination`. Express workflows require CloudWatch Logs — there's no separate execution-history API the way Standard has — and the reused `rag-assistant-stepfunctions-role` had only ever been granted plain `lambda:InvokeFunction`. The fix needs a specific, easy-to-miss action set (`logs:CreateLogDelivery`, `GetLogDelivery`, `UpdateLogDelivery`, `DeleteLogDelivery`, `ListLogDeliveries`, `PutResourcePolicy`, `DescribeResourcePolicies`, `DescribeLogGroups` — all `Resource: "*"`, since they're account-level log-delivery-management operations, not scoped to one log group — plus `CreateLogStream`/`PutLogEvents` scoped to the specific vended log group) — ordinary `logs:CreateLogStream`/`PutLogEvents` alone, which most Lambda-adjacent IAM examples assume is sufficient, does not cover it |
| 9 | UI, local testing (mine) | The async mode's polling `fetch()` call — a plain, no-header `GET`, the first of its kind anywhere in this project's UI — was blocked by the browser with a CORS error when the page was opened directly via `file://`, even though curl confirmed the API's actual CORS headers (both the direct `GET` and the `OPTIONS` preflight) were correct. Every prior working UI call was either a `POST` with an explicit `Content-Type` header or a WebSocket connection — neither hits the same `file://`-origin edge case a bare `GET` does. Fixed by serving the page through a trivial local HTTP server instead of opening the file directly, sidestepping the whole `file://`-origin quirk category rather than chasing the exact browser behavior |
| 10 | `get-analysis-result` Lambda, S3 IAM (mine) | Polling a job that hadn't finished yet returned `502 Bad Gateway` — the Lambda was crashing on an unhandled `AccessDenied` from `s3.get_object()`. The real cause: **S3 returns `AccessDenied`, not `NoSuchKey`, for a nonexistent object if the caller lacks `s3:ListBucket`** — without list permission, S3 won't confirm to the caller whether the object genuinely doesn't exist or access is merely denied, so it masks the distinction as a blanket `AccessDenied`. My code only had a special case for `NoSuchKey`. Fixed by granting `s3:ListBucket` scoped to the `analysis-results/*` prefix — a real, generally-applicable S3 lesson: `GetObject`-only permissions are not enough to reliably distinguish "not found" from "not allowed" |

---

_Part of [Gen AI Practice](../README.md)._
