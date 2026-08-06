# Practice 04 — AI-Powered Support Ticket System

An end-to-end support ticket pipeline on Amazon Bedrock: submit a ticket → an AWS Strands
Agent classifies it → a Knowledge Base lookup grounds the response in real documentation →
a Bedrock Prompt Flow drafts the reply, branching on priority → a mock CRM records the
result — all chained by a Step Functions Express workflow, plus a live WebSocket chat mode
and a separate Bedrock Data Automation path for customer feedback documents. Reference
spec: [ASSIGNMENT.md](./ASSIGNMENT.md).

## Why this reuses Practice 02/03's infrastructure instead of starting fresh

Same discipline as practice-03 against practice-02: this project does **not** stand up its
own IAM user, Lambda execution role, or API Gateways. [Practice 02](../practice-02/README.md)'s
`rag-assistant-project-user`, `rag-assistant-lambda-role`, `rag-assistant-api` (REST), and
`rag-assistant-ws-ap` (WebSocket) are all still live — confirmed by a Stage 1 live audit —
plus [Practice 03](../practice-03/README.md)'s `ModelCircuitBreaker` table and
`rag-assistant-stepfunctions-role`. New routes/resources get added on top, and the shared
role's inline policy gets widened incrementally, exactly when a stage needs it. Only
genuinely new resources (one DynamoDB table, ten Lambdas, a Lambda Layer, a Bedrock Prompt
Flow, a Bedrock Data Automation project, an Express state machine, new REST/WS routes) get
created from scratch — see [SETUP-LOG.md](./SETUP-LOG.md) for the full resource-by-resource
record.

## Scope decisions

The assignment as written is considerably larger than what's built here. Three things were
deliberately cut, with reasons:

1. **Amazon Q Business → substituted with the existing Bedrock Knowledge Base.** Q Business
   is a standing per-user subscription ($3/mo Lite, $20/mo Pro) — the only service in this
   assignment that isn't pay-per-use, breaking every prior practice's $0-idle cost
   discipline. `rag-assistant-kb-2` fills the "internal knowledge for support agents" role
   instead, at zero extra cost.
2. **AWS Amplify Hosting → not deployed.** The React frontend genuinely uses
   `@aws-amplify/ui-react` declarative components, matching the assignment's own reference
   code, but runs via `npm run dev` locally rather than being hosted on AWS — no hosting
   cost, same "local UI" convention as every prior practice, just with a real build step
   this time since the assignment specifically named the framework.
3. **AWS Agent Squad → skipped entirely.** Its "specialist agents" are the same underlying
   Bedrock model with a different system prompt per category — no separate infrastructure,
   and its actual value (routing + a chained refine pass) is already covered by Strands'
   classification (Stage 7) + the Prompt Flow's branching (Stage 4/6) + Step Functions
   chaining it all together (Stage 9). Adding it would have been a redundant "same model,
   different prompt" layer on top of capability already demonstrated elsewhere.

## A real design problem in the assignment itself

"Implement token limit management using Lambda authorizers" doesn't work as literally
written: REST API Lambda REQUEST authorizers never receive the parsed request body — only
headers, query string, path, and identity context. There is no way for an authorizer to
count tokens in a JSON field it structurally cannot see. The assignment's own reference code
confirms this gap: its `check_token_limits()` is a plain helper called from inside a
WebSocket handler, never wired to an authorizer at all.

**Resolution built here:** `ticket-request-authorizer` does a legitimate coarse pre-check on
something it *can* see — the `Content-Length` header, denying anything over ~40KB before a
Lambda invocation is even billed. Precise tiktoken-based counting still happens inside the
handler (`ticket-submit`), matching what the reference code actually does. Verified live:
an oversized request was denied with exactly 1 `ticket-submit` invocation (the earlier valid
request) vs. 2 authorizer invocations in the same CloudWatch Logs window — proof the
oversized request never reached the handler, not just a plausible-sounding claim.

## Cost

Everything already established as $0-idle/pay-per-use in practices 02-03 (Lambda, API
Gateway, DynamoDB On-Demand, S3, X-Ray, WebSocket) stays that way here. What's genuinely new
in this assignment, with real figures:

| Service | Pricing | Idle cost |
|---|---|---|
| Bedrock Prompt Flows | $0.035 per 1,000 node transitions + underlying model cost per prompt node | $0 |
| Bedrock Data Automation | $0.010/page standard output (this project stays on standard output — custom blueprints would be $0.040/page) | $0 |
| Lambda authorizer | Billed as an ordinary Lambda invocation; API Gateway caches the Allow/Deny decision (300s TTL here) | $0 |
| Strands Agents SDK | Apache-2.0 open source, zero license cost — only the Bedrock/Lambda calls it makes cost anything | $0 |
| Step Functions Express (2nd workflow) | $1.00/1M requests + $0.00001667/GB-second — **no free tier at all** for Express, unlike Standard's 4,000 free state transitions/month | $0 |
| Lambda Layer | No separate charge — bundled into the attached functions' deployment size | $0 |

**Amazon Q Business, priced at $3-20/user/month regardless of usage, is the only service in
this assignment that isn't $0-idle — it's also the one substituted out.** Total real spend
across every live test in this build (a dozen-plus ticket submissions, several Prompt Flow
executions on both branches, one BDA job, one full WebSocket chat session) comes to
fractions of a cent.

## Build stages

### Stage 1 — Live audit (confirmed, no new resources)

Verified the shared IAM role, both API Gateways, the Knowledge Base, `ModelCircuitBreaker`,
and the Step Functions role were all still active before touching anything.

### Stage 2 — Ticket data layer (built and verified live)

New `SupportTickets` DynamoDB table (PK `ticket_id`, On-Demand). Widened
`rag-assistant-lambda-role` with `SupportTicketsAccess`.

### Stage 3 — Token-limit authorizer + ticket submission skeleton (built and verified live)

`ticket-request-authorizer` (Content-Length coarse check) on new `POST /tickets`, reusing
practice-03's existing "Validate body" validator for the new `TicketRequest` model.
`ticket-submit` + `get-ticket` Lambdas. Verified the authorizer genuinely blocks oversized
requests before the handler runs (CloudWatch invocation counts, not just the HTTP response).
Hit the same API Gateway propagation-delay behavior practice-03 documented (bugs table #1/#5
there) — retried after a longer wait, same non-issue.

### Stage 4 — Bedrock Prompt Flow (built via CLI, verified live on both branches)

Built `support-agent-response-flow` via `bedrock-agent create-flow` + a hand-written JSON
definition rather than the console — the console's Flow-input node turned out to expose
only a single field literally named `document`, and reconciling that with multiple named
downstream prompt inputs hit enough real friction (see bugs #2-#4) that driving it via the
documented API schema (`--generate-cli-skeleton`, not memory) was faster and more precise.
Final shape: Input (single `document` output, type Object) → Condition (`Critical` /
`default`) → two Prompt nodes (Nova Pro "urgent" / Nova Lite "standard") → two separate
Output nodes, since an Output node's input can only take one incoming connection — one
shared Output for both branches fails flow preparation outright.

Both branches verified independently via `start-flow-execution`: a `critical` ticket
produced exactly one Nova Pro call and routed to `UrgentFlowOutput`; a `low` ticket produced
exactly one Nova Lite call and routed to `StandardFlowOutput`. The other branch's prompt
node never fired in either case — confirmed from the actual execution events, not assumed.

### Stage 5 — KB-backed internal-knowledge lookup (built and verified live)

`ticket-kb-lookup` — one `retrieve()` call against `rag-assistant-kb-2`, reusing practice-03
Stage 7's exact retry/circuit-breaker pattern under the already-established
`bedrock-kb-retrieve` sentinel key. Zero new circuit-breaker infrastructure. Verified live:
a ticket about Lambda concurrency correctly pulled the Lambda concurrency doc from the
existing corpus.

### Stage 6 — Response generation wrapper (built and verified live)

`ticket-generate-response` calls the Prompt Flow. This API version exposes no synchronous
streaming `invoke_flow` — only an async `start_flow_execution` → poll `get_flow_execution` →
read `list_flow_execution_events` pattern, discovered by testing directly rather than
assuming the older API shape still applied. Two real bugs here (table #3/#4) before it
worked cleanly: a request-name length limit, and Output nodes surfacing data via
`nodeInputEvent` rather than `nodeOutputEvent`.

### Stage 7 — Strands intent classification (built and verified live)

First third-party pip dependency this repo has ever bundled into a Lambda. Inspected the
real `strands-agents` API directly (`inspect.signature`) rather than guessing at import
paths, built a dedicated Lambda Layer with the correct cross-platform pip flags, and wrote
`ticket-classify` using a Strands `Agent` + `BedrockModel` with a Pydantic
`structured_output_model`. Verified live against two different ticket types — correctly
returned `technical`/`high` and `billing`/`medium` with sensible reasoning.

Worth being honest about: for pure classification with no tools, no memory, and no
multi-step decisions, Strands is heavier than the task strictly needs — a plain `converse()`
call would do the same job without a 27MB layer. It's built this way because the assignment
explicitly names Strands as a requirement to demonstrate, not because this specific step
needs agentic capability. Discussed at length mid-build; kept as pure classification rather
than extended with tool-calling, to stay in scope.

### Stage 8 — Mock CRM (built and verified live)

`crm-mock-update` reads/writes `SupportTickets` directly — a more genuine "mock CRM" than
the reference's bare `print()`. Verified the real DynamoDB record updates with status,
category, urgency, the drafted response, and a fake CRM ID.

### Stage 9 — Ticket processing workflow (built and verified live end-to-end)

New **Express** state machine `support-ticket-workflow`: Classify → Query KB → Generate
Response → Update CRM. Same Express justification as practice-03's
`document-routing-workflow` — strictly linear, single blocking caller. Needed the vended log
group created *before* the state machine (`InvalidLoggingConfiguration` otherwise), and
generalized the Step Functions role's log-delivery scope to a wildcard to preempt a second
instance of practice-03 bug #8.

`ticket-submit` rewired to call `start_sync_execution` and return the real result. Verified
twice through the actual public API end-to-end — a DynamoDB-throttling ticket and an API
500-errors ticket — both correctly classified, both pulled the specifically relevant existing
doc (`dynamodb-on-demand-capacity.md`, API Gateway caching), both drafted a genuinely useful
fix, both persisted to DynamoDB.

### Stage 10 — Real-time WebSocket chat (built and verified live)

`ticket-chat-stream` + new `ticket-chat` route on the existing WebSocket API. Reused
`ManageConnections`/`InvokeModelWithResponseStream` grants — zero new IAM. Hit the
already-known `AutoDeploy`-off trap from practice-03 and handled it the same way (explicit
deployment). Verified over a real `wss://` connection with a Python `websockets` test
script: KB grounding found, tokens streamed live, correct model reported at completion.

### Stage 11 — Agent Squad orchestration (skipped)

See "Scope decisions" above.

### Stage 12 — Bedrock Data Automation for feedback (built and verified live)

New BDA project `support-feedback-bda-project` (standard output only). `feedback-submit`
(base64 upload + `invoke_data_automation_async`) / `get-feedback-result` (same
`list_objects_v2`-based 202/200 polling shape as practice-03's `get-analysis-result`). Two
real, non-obvious things hit here — bugs #5/#6: plain `.txt` isn't a supported BDA input
format (needed `.docx`), and the `us.data-automation-v1` profile is **cross-region** — it
silently routed the actual invocation to `us-east-2` while the IAM policy only granted
`us-east-1`, producing an `AccessDeniedException` naming a region never specified anywhere
in the code. Verified live end-to-end through the real public API: uploaded a feedback
document, polled for completion, got back a genuine generative summary and description.

### Stage 13 — OpenAPI specification (written)

`practice-04/openapi/support-ticket-api.yaml` documents the actual deployed surface (4
endpoints) rather than the assignment reference's 2-path sketch — a real upgrade, consistent
with this project's "docs reflect what I actually built" ethos. Validated with a local YAML
parse.

### Stage 14 — React + Amplify frontend (built, local-only)

`practice-04/ui-react/` (Vite + `@aws-amplify/ui-react`), four modes behind a
`ToggleButtonGroup`: submit ticket, look up ticket, live chat, feedback upload. Verified
Amplify's real v6 REST API surface (`get`/`post` from `@aws-amplify/api`) directly from the
installed package's type definitions rather than assuming the older v5 `API.post(...)`
syntax the reference code uses. Build compiles clean; dev server serves without runtime
errors. **Not clicked through in an actual browser** — no browser tool available in this
environment. Worth doing before calling this stage fully proven, the same way every other
stage here was proven against the real deployed system rather than just "should work."

### Stage 15 — Monitoring (built and verified live)

X-Ray active tracing on all 10 new Lambdas + the state machine — zero new IAM
(`XRayWrite` already granted account-wide). Confirmed real traces captured via
`xray get-trace-summaries` after generating fresh traffic. One CloudWatch Logs Insights
query across four of the new Lambdas' log groups produced genuinely useful output: average
duration per stage (`ticket-generate-response` ~7.4s dominates the workflow's latency,
vs. ~1.1s classify / ~0.6s KB lookup / ~0.3s CRM update) — not just a query that runs, an
actual answer to "where does the time go."

### Stage 16 — Tests (written and passing)

First pytest suite in this repo: 26 tests across the authorizer's size-check logic,
`ticket-submit`'s validation/defaulting/token-limit/workflow-result branches, the circuit
breaker's closed/open/half-open state transitions, and `get-ticket`'s Decimal-safety helper.
Zero real AWS calls — every DynamoDB/Bedrock/Step Functions interaction is mocked via
`unittest.mock`, matching the plan's "pure-logic, offline-testable slice" scope rather than
introducing a CI harness this repo doesn't otherwise have.

---

## Bugs found

| # | Where | Issue → fix |
|---|---|---|
| 1 | `ticket-submit` Lambda packaging (mine) | `tiktoken.get_encoding("cl100k_base")` normally fetches its BPE vocab file from a public blob URL on first call — a hidden runtime dependency on an external endpoint at cold start, and also un-fetchable from the manylinux-targeted build environment used for the deployment package (the wheel is for Linux, but the fetch script needs to actually run to produce the cache file). Fixed by installing a *native* tiktoken separately just to run the fetch once, then bundling the resulting platform-independent cache blob alongside the manylinux wheels, with `TIKTOKEN_CACHE_DIR` set to point at it |
| 2 | Bedrock Flow definition, Stage 4 (mine) | First `create-flow` attempt failed `prepare-flow` with 8 validation errors at once: `FlowInputNode` only supports a single output literally named `document` (my attempt used 4 named outputs); a Condition node needs an explicit `default` condition defined on itself, not just a connection referencing that keyword; and an Output node's input can only have one incoming connection, so two prompt branches can't share one Output node → redesigned with `document` as a single Object-typed field, added an explicit `default` condition, and split into `UrgentFlowOutput`/`StandardFlowOutput` |
| 3 | Bedrock Flow definition, Stage 4 (mine) | Second attempt failed with one more validation error: `Default condition must not have an expression` — I'd set `expression: "true"` on the `default` condition, which is invalid; the reserved condition needs no expression field at all → removed it, flow prepared cleanly |
| 4 | `ticket-generate-response` Lambda, Stage 6 (mine) | Two bugs before this worked: (a) `flowExecutionName` has a strict ≤36-character, alphanumeric-and-hyphen-only constraint — a `ticket-` prefix on a UUID pushed it over, fixed by using the bare UUID; (b) Output nodes surface their received data via a `nodeInputEvent`, not a `nodeOutputEvent` — my code checked the wrong event type and silently returned `None` for every response despite the execution reporting `Succeeded`, found by inspecting the raw event list directly rather than assuming the event shape |
| 5 | IAM, Stage 6 (mine) | `GetFlowExecution`/`ListFlowExecutionEvents` calls failed `AccessDeniedException` even after granting the flow and alias ARNs — these two actions check permissions against the **execution**-level ARN (`.../execution/<id>`), a third distinct resource level `StartFlowExecution` doesn't need → widened the resource list to include `.../execution/*` |
| 6 | `feedback-submit`, Stage 12 (mine, or arguably AWS's error message) | `invoke_data_automation_async` failed `AccessDeniedException` naming resource `arn:aws:bedrock:us-east-2:...` — a region I never specified anywhere. Root cause: the `us.data-automation-v1` profile is a **cross-region** profile, and Bedrock silently routed the actual invocation to `us-east-2` while my IAM policy only granted `us-east-1` → widened the profile/invocation ARNs in the policy to a wildcard region |
| 7 | `feedback-submit` input format, Stage 12 (mine) | First live test uploaded a plain `.txt` file and got `The format of the input file isn't supported` — Bedrock Data Automation's document processing doesn't accept plain text, only real document formats → converted the test fixture to `.docx` via macOS's `textutil`; the API itself already validates `fileExtension` against a supported-formats list |

---

_Part of [Gen AI Practice](../README.md)._
