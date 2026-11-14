# Practice 05 — Safe & Responsible AI Assistant

Defense-in-depth safety and responsible-AI governance layered onto the existing
[Practice 02](../practice-02/) RAG assistant and [Practice 04](../practice-04/) support ticket
system. Two of the four bonus assignments in [ASSIGNMENT.md](./ASSIGNMENT.md) — Bonus 01 (safe
GenAI assistant) and Bonus 04 (responsible AI / transparency / governance) — with Bonus 02
(VPC-based network isolation) and Bonus 03 (data-lineage governance for FM *training* data, which
doesn't apply here since nothing in this project trains a model) scoped out; see the scope
rationale that was worked out before any building started.

## Why this reuses Practice 02/04's infrastructure instead of starting fresh

Same discipline as every prior practice: no new IAM user, no new API Gateway, no duplicate
Knowledge Base. The existing `rag-assistant-lambda-role`, `rag-assistant-api` (REST),
`rag-assistant-ws-ap` (WebSocket), `rag-assistant-kb-2`, and `SupportTickets` are all still live —
confirmed by a Stage 0 audit — and every stage here either widens that shared role's inline policy
or adds a small number of genuinely new Lambdas/resources on top. See
[SETUP-LOG.md](./SETUP-LOG.md) for the full resource-by-resource record.

## Cost

Every genuinely new resource in this practice is $0-idle, pay-per-use — the same discipline as
every prior practice, and notably **better** than practices 02-04, which all left standing
infrastructure running. Nothing built here needs teardown to stop billing: Bedrock Guardrails,
Comprehend, the Lambda Layer, the Express state machine, and the SageMaker Model Card are all
either free or billed strictly per-invocation, confirmed with real pricing figures (Stage 9) and
zero idle-cost line items found anywhere.

## Build stages

### Stage 0 — Live audit (confirmed, no new resources)

Confirmed every piece of P02/P04 infrastructure this practice depends on was still live before
touching anything: KB `LTIWE7M3DC`, S3 Vectors index, both API Gateways, `SupportTickets`,
`rag-assistant-lambda-role`. Hit one transient, unrelated `SSL: CERTIFICATE_VERIFY_FAILED` error
on a `bedrock-agent` call mid-audit — didn't reproduce, not investigated further since the KB's
`ACTIVE` status was already confirmed another way.

### Stage 1 — Bedrock Guardrail created (built and verified live)

`rag-assistant-guardrail` (`5jk3sefhtv16`) created via CLI against the real `CreateGuardrail`
API shape — content filters, denied topics (`Legal_Advice`, `Financial_Advice`), PII policy,
prompt-attack detection. The assignment's own `create_guardrail`/`apply_guardrail` reference code
is fabricated (wrong client, wrong parameter names, wrong response shape) — this was built
directly against the real API and worked on the first attempt, verified with `get-guardrail`.

### Stage 2 — Wired into production (built and verified live)

`generate` (P02) uses inline `guardrailConfig` on `Converse` — one round trip covers input and
output. `ticket-generate-response` (P04) uses standalone `apply_guardrail` on both sides of the
Prompt Flow invocation, since Prompt Flows have no inline guardrail parameter. Found and fixed a
mislabeling bug during the very first live test (bugs table #1).

### Stage 3 — Tuned against a real 30-prompt corpus (built and verified live)

Monitor-mode test corpus (10 benign questions from P02's `test_questions.py` + 20 hand-built
adversarial/borderline prompts) run against the live guardrail, iteratively tuned:

- **v1 (initial config): 50% accuracy, 15 false positives.** Root cause: `PROMPT_ATTACK` at `HIGH`
  strength reacting to the RAG prompt template's own grounding instruction, not to any specific
  retrieved content — reproduced against every one of the 15 benign RAG-style prompts.
- **v2: PROMPT_ATTACK → `LOW`, PII entities `BLOCK` → `ANONYMIZE`.** Exposed a second, more
  consequential bug in the process — see bugs table #2. After fixing it: 90% accuracy.
- **v3: a dead publish** — see bugs table #3.
- **v4: removed the `confidential`/`proprietary` custom word list** (inherited from the
  assignment's financial-document framing, false-positiving on AWS's own documentation vocabulary)
  **+ softened the RAG prompt template's wording** (tested directly: the same retrieved content
  through a less imperative template dropped `PROMPT_ATTACK` from firing entirely). **Result: 97%
  accuracy, 0 missed adversarial prompts, 1 principled residual false positive** — the guardrail
  correctly recognizing "Act as X" persona framing as jailbreak-shaped even when used benignly, a
  real precision cost of running the filter at all, not a bug.

### Stage 4 — Comprehend PII masking on data-at-rest gaps (built and verified live)

Directly proved Bedrock's guardrail **never scans the INPUT side for sensitive information** —
confirmed with an identical text scoring `sensitiveInformationPolicyUnits: 0` on `source=INPUT`
and a real PII hit on `source=OUTPUT`. That meant raw PII was flowing unmasked into two places
Stage 2/3 didn't touch: `SupportTickets` (via `ticket-submit`, which writes to DynamoDB *before*
the guardrail-protected workflow runs) and `RagQueryCache` (via `query_router`, which caches the
raw query text verbatim). Added Comprehend `detect_pii_entities` masking to both write paths —
original unmasked subject/description still flows to generation (independently protected by
Stage 2/3's output-side guardrail), only the persisted copy is redacted. Verified live via direct
DynamoDB reads, not just Lambda return values. Hit and fixed a real deployment bug redeploying
`ticket-submit` — bugs table #4.

### Stage 5 — Regex injection detector vs. managed filter, quantified (analysis only)

Implemented the assignment's `ThreatDetector.detect_prompt_injection()` regex pattern list and
tested it three ways: against the 5 real attacks from Stage 3 (missed 1 — "Ignore *all* previous
instructions..." defeated the exact-phrase match `ignore previous instructions` with one inserted
word), against the actual 6-document corpus (0 false positives — the assignment's own "system
prompt" hypothesis didn't literally hold), and against 4 constructed-but-realistic AWS technical
sentences using the same trigger words in ordinary context (4/4 false positives, confirming the
clean corpus result was luck, not a structural property). The managed filter caught 5/5 attacks
and 0/4 false positives on the identical sentences. Not wired into anything — purely a measured
comparison.

### Stage 6 — Tiered moderation workflow (built and verified live, deliberately not deployed)

Built the assignment's two-tier Comprehend-then-LLM moderation Step Functions design —
`moderation-risk-check` (cheap Comprehend sentiment+PII scoring) → conditional escalation to
`moderation-llm-check` (Bedrock harm classification) — fixing a real bug in the assignment's own
reference CDK code along the way (bugs table #5). Measured against the Stage 3 corpus: 77% fewer
LLM moderation calls than moderating every request. But **67% (8 of 12) of adversarial prompts
skipped moderation entirely**, because Comprehend sentiment measures emotional tone, not content
harm — calmly-phrased violence requests and denied-topic (financial/legal) questions have neutral
sentiment and never escalate. The identical 12 prompts are caught 100% by the Bedrock Guardrail
already live from Stage 1-3. Kept in the repo as a documented Step Functions pattern exercise, not
wired into the live request path — deploying it as the assignment intends (a primary filter) would
be a real security regression, not a cost optimization.

### Stage 7 — Contextual grounding (built and verified live)

Added `contextualGroundingPolicyConfig` (v5) and restructured `generate`'s Converse call to use
`guardContent` blocks with `qualifiers: ["grounding_source"]`/`["query"]` — a flat text block skips
grounding scoring entirely, a real, non-obvious API requirement none of the four assignments'
"hallucination reduction" sections mention. Caught a genuine fabrication (an invented Lambda
SnapStart cold-start figure with a fake citation) in 4 of 5 identical repeated trials. Also
directly proved the grounding filter's **score itself is non-deterministic**: 5 identical calls
(same query, same retrieved content, same model) produced scores from 0.54 to 0.80, straddling the
0.75 threshold. Threshold kept at AWS's suggested default rather than raised, since raising it
would worsen false positives on legitimate elaborated answers without reliably fixing noise-driven
misses.

### Stage 8 — Structured output validation (built and verified live)

Built a `jsonschema` Lambda Layer and wired real schema validation into `moderation-llm-check`
(Stage 6), replacing bare `json.loads` + silent `.get(..., False)` defaults with
`jsonschema.validate()`, fail-closed on both parse errors and shape violations. Hit a real
build-environment bug publishing the layer (bugs table #6). Proved the fix matters with a direct
comparison: a plausible key-name drift (`"harmful"` instead of `"is_harmful"`) caused the old code
to silently *approve* content the model itself had flagged as harmful; the new code correctly
fails closed. Also compared against Converse tool-use as the AWS-native alternative — same task,
zero manual JSON parsing, no risk of the model wrapping output in prose.

### Stage 9 — Defense-in-depth cost/latency measurement (measured, no new resources)

Timed every guardrail-touching component directly (5-run averages, since Stages 3/7 already
proved these APIs have real call-to-call variance): standalone `apply_guardrail` ~0.7-0.8s, inline
`guardrailConfig` overhead on top of a bare Converse call ranged from -0.03s to +0.29s across two
measurement runs (statistically indistinguishable from noise). Dollar cost: ~$0.0019/request on
`/ask`, ~$0.0009/request on `/tickets` — genuinely negligible. Honest verdict: defense-in-depth
here is cheap in both dollars and latency; the real tradeoffs found elsewhere in this practice
(Stages 3, 6, 7) are precision/recall and architectural complexity, not cost.

### Stage 10 — Transparency: hand-rolled tool-use loop, not a managed agent (built and verified live)

Classic Bedrock Agents is blocked for this account — `CreateAgent` fails with AWS's own
"Agents Classic will no longer be open to new customers starting on July 30, 2026" maintenance-mode
policy, and that cutoff had already passed. AgentCore (AWS's current-generation replacement) was
evaluated for real: pricing is genuinely idle-free (confirmed via AWS's published rates before
any decision was made), but its differentiating components (Gateway, Identity, Memory,
managed Runtime) don't solve any problem this system actually has at its current scale — a
two-tool, single-tenant, request/response agent doesn't need multi-tool federation or cross-session
auth. Built a hand-rolled Converse tool-use loop instead (`support-agent-loop`, reusing a new
`crm-agent-actions` Lambda as a CRM-lookup/update tool alongside KB search), logging every step
itself. Verified with three live tests including a genuine multi-step read-then-conditionally-write
chain (checked a ticket's priority, decided to update it, wrote the change, confirmed via a direct
DynamoDB read) — real, model-decided branching never hand-coded. Delivered the actual
trace-vs-Step-Functions-graph comparison this stage was for: Step Functions shows every possible
path at design time and needs zero extra code for its execution history; the hand-rolled trace
shows only what *did* happen but includes the model's full chain-of-thought reasoning, which Step
Functions has no equivalent of.

### Stage 11 — Citations, confidence, and four real bugs in the streaming path (built and verified live)

Verified live that the assignment's `retrieve_and_generate` citation-parsing code crashes on the
first line against the real API response shape (`citations` is a top-level list, not a dict with a
nested `retrievalResults` key). While checking how sources are surfaced in the UI, found that
`ws_ask` — the WebSocket streaming path, which is **the UI's default mode** — had **none** of
Stages 1-9's guardrail wiring at all. Fixed it, then found and fixed three more bugs the fix itself
exposed (bugs table #7-#9): a grounding-block misclassification that left stale sources displayed
alongside a "safe" label, a garbled-display bug where a blocked message got appended directly onto
already-streamed partial content with no separator, and an unhandled Bedrock transient error that
crashed the Lambda silently and hung the client forever. Added a real `confidence` field (the
contextual grounding score, when available) to both `generate` and `ws_ask` responses, emitted
`GuardrailAction`/`GroundingScore` custom CloudWatch metrics, and added a UI notice + confidence
bar so users can tell "no results" apart from "filtered by policy" — something the UI genuinely
could not show before this stage.

### Stage 12 — Fairness evaluation, corrected via repeated sampling (built, tested, retracted)

Adapted the assignment's demographic-personas-asking-a-financial-advisor framing to this system's
actual domain: does `ticket-classify`/`ticket-generate-response` treat the *same* technical
problem differently based on how the ticket is written? An initial n=1-per-condition LLM-as-judge
eval (3 scenarios × 5 writing-style personas, run through the live `ticket-submit` endpoint)
appeared to find a clean, reproducible bias — casual/non-native-English phrasing consistently
classified as higher urgency and scored as less thorough by the judge, identically across all 3
scenarios. A user-prompted manual spot-check didn't replicate it, which led to the real test: 6
independent repeated trials per persona for urgency (result: **tied 6/6 vs 6/6**, no difference)
and 5 independent trials per persona for thoroughness, scored against a fixed rubric rather than a
single comparative judge call (result: **tied on the concrete criteria-covered metric**, the
holistic score difference within noise). **Both original claims retracted.** The real, more
valuable finding: a naive single-sample LLM-as-judge fairness audit — exactly the assignment's own
design, one comparative judge call, no repeated trials — produces a convincing, narratively
coherent, *false* result. Fairness claims from this kind of evaluation need the same
repeated-sampling rigor as any other noisy classifier metric in this practice.

### Stage 13 — Responsible-AI CloudWatch dashboard (skipped)

Skipped per direction — the `GuardrailAction`/`GroundingScore` metrics from Stage 11 are live in
CloudWatch (`RagAssistant/Guardrails` namespace) if this gets picked up later.

### Stage 14 — SageMaker Model Card (built and verified live)

`rag-assistant-support-system`, created via CLI and marked `Approved`, documenting the system
honestly — including the Stage 12 retraction and the Stage 6 workflow that was evaluated and
deliberately not deployed, not just the wins. Hit two real bugs getting it created (bugs table
#10-#11): a confusingly generic AWS validation error that was actually a newline-in-content issue,
and a self-escalation IAM restriction requiring manual action to grant `sagemaker:CreateModelCard`.
Free — no cost added.

---

## Bugs found

| # | Where | Issue → fix |
|---|---|---|
| 1 | `generate` Lambda, Stage 2 (mine) | The very first live test after wiring in the guardrail mislabeled an *input*-side `PROMPT_ATTACK` intervention (on the full RAG prompt, inside the `Converse` call) as `output_intervened`, since the code only checked `response.get("stopReason")` without inspecting which side of the trace actually fired → inspected `trace.guardrail.inputAssessment` vs `outputAssessments` explicitly to attribute the intervention correctly |
| 2 | `generate`/`ticket-generate-response` Lambdas, Stage 3 (mine) | `GUARDRAIL_INTERVENED`/`guardrail_intervened` fires identically for a real block (topic/content/word policy) **and** a successful PII `ANONYMIZE` (content redacted, not rejected) — found via a live SSN test where the model echoed the SSN back, Bedrock correctly redacted it in `output.message.content`, but the code discarded the safe, redacted answer and showed a generic blocked message anyway → added `_is_hard_block()` to both Lambdas, scanning each policy's actual per-entry `action` field rather than trusting the top-level intervened flag |
| 3 | Guardrail publish, Stage 3 (mine) | `update-guardrail` failed with `Invalid length for parameter wordPolicyConfig.wordsConfig, value: 0, valid min length: 1` (an empty array isn't valid — the key must be omitted entirely to mean "no custom words"), but `create-guardrail-version` was mistakenly still run immediately after against the stale, unmodified DRAFT, publishing a dead version 3 identical in substance to v2 → verified DRAFT's actual state via `get-guardrail` before publishing again, fixed the payload to omit `wordsConfig` rather than pass an empty list, published a real v4 |
| 4 | `ticket-submit` Lambda, Stage 4 (mine) | Redeploying with `zip -r . lambda_function.py` broke the function at runtime (`No module named 'tiktoken'`) — the original working deployment had `tiktoken` vendored directly into the zip (no Lambda Layer attached, confirmed via `get-function-configuration`), and that vendored copy was never part of the git-tracked source folder, so a redeploy from source silently dropped it → rebuilt with `pip install --platform manylinux2014_x86_64 --only-binary=:all:` (not a plain local install, which grabs macOS-native wheels that fail silently at Lambda runtime — the exact class of bug already documented once in Practice 04) |
| 5 | Moderation Step Functions definition, Stage 6 (assignment's own reference CDK) | The reference code attaches one `moderate_content` Lambda-invoke state as the `.next()` target of **two different** Choice branches (`HIGH` and `MEDIUM` risk) — a state can only be added to a state machine graph once; this fails to synthesize | Rebuilt with a single shared `ModerateContent` state reached from both branches via one Choice, with its own single downstream decision Choice — verified the resulting graph creates successfully (confirming the fix, since the original shape would fail at creation) |
| 6 | `jsonschema` Lambda Layer, Stage 8 (mine) | The layer imported fine locally but crashed at Lambda runtime: `'default' is an invalid keyword argument for typevar()` — the layer's transitively-resolved `referencing` package pulled in Python 3.13+ typing syntax (PEP 696 `TypeVar(..., default=Any)`), incompatible with this function's actual `python3.12` runtime; `pip install --python-version 3.12` only constrains wheel *tags*, not this kind of pure-Python syntax requirement → pinned `jsonschema==4.23.0`/`referencing==0.35.1`/`rpds-py==0.20.0`, grepped the installed source for the problematic syntax before redeploying rather than guessing it was fixed |
| 7 | `ws_ask` Lambda, Stage 11 (mine) | First pass at adding guardrail wiring to the streaming path only checked `outputAssessments` for a hard block, missing the separate `contextualGroundingPolicy` check `generate`'s `_grounding_failed()` already had — a grounding-blocked response streamed the generic blocked-message text but was mislabeled `"anonymized"` with `sources` left non-empty, an inconsistency caught via a genuine non-deterministic repro (reproduced 2 of 4 attempts) → added the missing `_grounding_failed()` check, reproduced the same case again on retry to confirm the fix (`sources: []`, `guardrail_action: "ungrounded_intervened"`, consistent every time) |
| 8 | `ws_ask` Lambda / UI, Stage 11 (mine) | Tokens are forwarded to the browser live as they're generated, before the guardrail verdict is known — grounding in particular can only be scored once substantial text exists, so when an intervention fires mid-stream, Bedrock appends the blocked-message text as more stream tokens onto whatever was already sent, with no separator (observed live: a long partial answer about Bedrock Knowledge Bases, cut off mid-word, directly followed by "I'm not able to provide that response...") → added a `retract` signal in the final `done` message; the frontend now discards the accumulated partial text and shows a clean replacement instead of appending onto it. Documented honestly that this fixes the *display*, not the underlying exposure — partial content still briefly reaches the client before the verdict is known; only a fully-buffered non-streaming response actually prevents that |
| 9 | `ws_ask` Lambda, Stage 11 (mine) | An unrelated, transient Bedrock `internalServerException` mid-stream crashed the Lambda with an unhandled exception — the `except` block only caught `apigw.exceptions.GoneException` (client disconnect), so the WebSocket client received no `done` or `error` message and hung indefinitely waiting for a response that would never come → added a broad exception handler that sends a proper `{"error": ...}` message on any failure |
| 10 | SageMaker Model Card, Stage 14 (AWS's error message) | `create-model-card` failed with `Value at 'content' failed to satisfy constraint: Member must satisfy regular expression pattern: .*` on a completely valid, minimal JSON payload — the message looks like a schema error but is actually a **newline** problem: `.*` in most regex engines doesn't match across newlines by default, and the content was pretty-printed multi-line JSON → minified the content to a single line before submitting; confirmed the theory by testing a trivial 2-key payload first rather than debugging blind against the full ~9.5KB content |
| 11 | IAM, Stage 14 (real, expected restriction) | The CLI user (`rag-assistant-project-user`) couldn't grant itself `sagemaker:CreateModelCard`/`sagemaker:AddTags` — same self-escalation restriction hit once before in Stage 10 (a role couldn't update its own trust policy) — `iam:PutUserPolicy` on its own identity was denied | Required manual console action to add an inline policy scoped to `sagemaker:*ModelCard*` actions; tags were dropped rather than requesting a second permission round-trip for a non-essential field |

---

_Part of [Gen AI Practice](../README.md)._
