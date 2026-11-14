# practice-06: Integrate Bonus Assignments 01-03 into existing infrastructure

Execution plan. Work stage by stage, in order — check a stage off before starting the next.

## Context

`practice-06/practice-06.md` contains three unbuilt "bonus assignment" specs (15 individual asks total, generic reference Python code, old dead model IDs) — no other files exist in `practice-06/` yet. This repo's established pattern (practice-03/04/05 all built on top of practice-02's infra rather than starting fresh) means the right move here is an audit-first approach, not a blind full build.

An Explore-agent audit + a Plan-agent design pass (both run and spot-verified against the real code) found that **4 of the 15 asks are already fully built** in practice-01–05, **2 are a poor fit for this repo's architecture** and should be evaluated-and-rejected rather than built (matching how practice-05 built-but-deliberately-didn't-deploy its tiered moderation workflow — a documented non-build is a real finding here, not a silent skip), and the remaining asks collapse into **6 real build items**, each extending an existing Lambda/table rather than standing up a parallel system. The bonus spec's reference code also uses dead model IDs (`anthropic.claude-instant-v1`/`claude-v2`/`claude-3-sonnet-20240229`, confirmed retired per practice-02's README) and has two real correctness bugs (CloudWatch dimension cardinality explosions, and a Lambda-statelessness bug in the anomaly-detection reference code) that must not be implemented as written.

## Per-item verdicts

**SKIP — already fully built, adding a duplicate would be pure waste:**
- Streaming responses → exists in `ws_ask`, `analyze-stream`, `ticket-chat-stream` (all `converse_stream` + `post_to_connection`)
- Precomputed-response cache → exists: `query_router` + `RagQueryCache` DynamoDB table, TTL 3600s
- Parallel Bedrock calls in a workflow → exists: `query-workflow.asl.json` Map state fans out sub-question search concurrently
- X-Ray tracing + CloudWatch dashboard → X-Ray active since P03; dashboards at `practice-02/dashboard.json`, `practice-03/dashboard.json`
- (Bonus: raw token-count estimation → `ticket-submit` already does real `tiktoken` BPE counting; the spec's `len(text)//4` heuristic would be a downgrade, not an upgrade)

**EVALUATE-AND-REJECT — write up the reasoning, ship no code (documented non-build):**
- **Prompt compression** (filler-word regex stripping): this repo's prompts (`generate`, `query_router`, `ticket-classify`) are short, purpose-written instructions with none of the rambling filler the spec targets — the only large text blocks are RAG context chunks and ticket descriptions, where wording affects grounding/citation accuracy (P05 Stage 3 already found prompt-wording changes guardrail behavior). Regex-mangling grounding-source text for ~0 token savings is a correctness risk with no upside here.
- **Classic-NLP query preprocessing** (nltk stopword/lemma/synonym expansion): `query_expand`/`query_decompose` already do LLM-based paraphrasing for retrieval — domain-aware for free, no new dependency. Bedrock KB retrieval is vector/embedding search, not keyword/BM25 — stopword removal and lemmatization are a keyword-search-era technique with little payoff against embeddings, and would require bundling nltk + corpora into a Lambda package (a new packaging problem) plus a hand-maintained synonym dict that will rot.

**BUILD — real gaps, each extends an existing Lambda/table:**
1. Complexity-tiered model + maxTokens selection (merges the spec's three separate "by complexity," "by cost," and "by latency" asks into one mechanism — they're the same axis)
2. Conversation-history token-budget pruning
3. Fixed-cardinality operational CloudWatch metrics (token count, latency, error count)
4. Token-usage anomaly detection (built on top of #3's metrics, not the reference code's broken in-Lambda dict)
5. Cost-capability tradeoff reporting over real production data
6. Business-impact tracker (satisfaction rating + resolution metrics), with a small local static-HTML page to submit/demo ratings against the new API route — matching this repo's pre-P04 convention (a single self-contained HTML file, e.g. `practice-02/ui/index.html`) rather than wiring into practice-04's deployed React+Amplify app

## Decisions made

1. **Stage 9 UI**: local static-HTML page (pre-P04 convention), not a React/Amplify integration.
2. **CloudWatch namespaces**: two — `RagAssistant/Ops` (Stages 6+7), `RagAssistant/BusinessImpact` (Stage 9).
3. **Stage 7**: periodic EventBridge-scheduled check, not inline per-request.
4. **Stage 4 ticket-path gap**: `ticket-generate-response`'s Prompt Flow is documented as a deliberate non-build, not edited.

## Remaining open question

5. Should Stages 2-3 (the two evaluate-and-reject write-ups) and Stage 8 (reporting script) happen before or interleaved with the BUILD stages — i.e., one practice-06 write-up covering everything end-to-end, or the reject write-ups landing first as a standalone deliverable? Defaulting to numeric stage order (0→9) unless told otherwise.

## Build order

- [x] **Stage 0 — Live audit. DONE.** All confirmed live: `CloudWatchPutMetrics` scoped to `RagAssistant/Guardrails` as a **single string** (25 statements total in inline policy `Policy`); all 6 target Lambdas live on python3.12; all 5 DynamoDB tables live. **`generate`, `support-agent-loop`, `record-metrics` deployed code is byte-identical to local** (verified by downloading and diffing) — no drift. `support-agent-loop`'s deployment zip contains **only `lambda_function.py`** — confirms Stage 5 must bundle `tiktoken`. **New finding:** the `subQueries` complexity signal *survives the cache path* — `ReturnCached` uses `InputPath: $.routing.result`, returning the cached `finalResult` verbatim, so a cached complex query still carries `subQueries`. Stage 4's tiering is safe on cache hits. (`isComplex` itself is *not* visible to `generate` — both `ReturnResult` and `ReturnCached` strip `$.routing` — so `subQueries` presence is the only available signal, as planned.)

- [x] **Stage 1 — IAM widened. DONE.** `cloudwatch:namespace` condition changed from the single string `"RagAssistant/Guardrails"` to the list `["RagAssistant/Guardrails", "RagAssistant/Ops", "RagAssistant/BusinessImpact"]`. All 25 statements preserved (verified on read-back); policy size 5,086 chars against the 10,240 limit. Backup of the pre-change policy kept during the edit.

- [x] **Stage 2 — Prompt compression evaluated and REJECTED. DONE.** Script: `prompt_compression_eval.py`. **The result inverted the plan's expectation, and is a much stronger finding.** The plan predicted "near-zero token delta"; the measured delta is **31.3% fewer tokens** across the 6 real prompts — the assignment's savings claim is numerically *true*. But the savings come almost entirely from the compressor's final "truncation branch" (`sections[0] + ". " + sections[-1]` when >3 sentences), which **deletes whole sentences rather than removing filler**, and it destroyed 4 load-bearing elements:
  - `generate`'s instruction (49→23 tok): lost **the `[Source N]` citation requirement** and **the "state that clearly" don't-guess instruction** — i.e. it deleted the entire anti-hallucination contract.
  - A real retrieved RAG chunk used as `grounding_source` (126→60 tok): lost **the answer fact itself** ("1,000 concurrent executions") and the per-Region qualifier. The guardrail would then score a correct answer as ungrounded, because the source no longer contains it.
  - Where filler-removal alone applied, it did essentially nothing: `query_router` saved **1 token** (by collapsing `\n\n` to a space), and `query_expand` saved **0 tokens while still altering the text** — pure risk, zero benefit.
  - The one case where the compressor worked as advertised (32.6%, meaning preserved) was the **user's ticket free-text** — which is not a prompt at all, is stored as a support record a human reads, and already goes through P05's Comprehend PII masking. The one input it helps on is the one input you least want rewritten.

  **Verdict: reject.** A token counter alone cannot see this failure — the headline number looks like a win while the citation contract and the answer fact are being deleted. Not deployed.

- [x] **Stage 3 — nltk query preprocessing evaluated and REJECTED. DONE.** Script: `query_preprocessing_eval.py`. Rather than argue the case, this measured it: each of practice-02's 10 real corpus questions was embedded twice with **the same model the KB is indexed with** (`amazon.titan-embed-text-v2:0`, 1024-d, normalized) — once raw, once nltk-preprocessed — and compared by cosine.

  **Result: mean cosine 0.8724 (min 0.7881, max 0.9532, stdev 0.0490), mean 5.1 words removed per query. Every single query landed below 0.95.**

  So preprocessing is not a harmless no-op — it **materially relocates the query** in the exact space the KB is indexed in, by ~0.13 cosine on average. For scale, practice-02 measured Titan v2's entire similar-vs-dissimilar separation gap at **0.599 vs 0.454**, so a 0.13 displacement is a large fraction of the model's meaningful signal range. And the *direction* of that displacement is unmeasurable here: practice-02 documented its retrieval eval **saturates at 1.000** on this 6-doc corpus, so there is no discriminating metric available to prove the move helps rather than hurts.

  Concrete damage visible in the outputs, beyond the raw number:
  - **The hand-maintained `domain_terms` dict already rots on first contact** — it has no entry for `on-demand`, so the hyphen split plus stopword removal of "on" turns **"on-demand capacity mode" into "demand capacity mode"** and "DynamoDB on-demand mode" into "dynamodb demand mode". That is a different concept, in a corpus where on-demand vs provisioned is the actual distinction being asked about.
  - Lemmatization mangles product names: "Step Functions" → "step function", "Knowledge Bases" → "knowledge base".
  - Question structure is destroyed: "**How many** times in a 24-hour window…" → "**many** time 24 hour window…", inverting an interrogative into an assertion; "**Is** S3 Versioning turned on by default…" → "s3 versioning turned default create bucket".

  **Verdict: reject.** Not "no benefit" but "measured displacement with unverifiable direction," plus a dependency (nltk + bundled corpora, a fresh Lambda packaging problem) and a term dictionary demonstrated to be already incomplete. `query_expand`'s LLM paraphrasing covers the same goal with no dictionary to maintain. Not deployed.

- [x] **Stage 4 — Complexity-tiered model selection. DONE, but substantially corrected by measurement.** Scripts: `tier_quality_check.py`. Built as planned (3 tiers, model + maxTokens), then A/B'd against the live guardrail with the query held constant and only the tier varied — via a `tier` override added to `generate`'s direct-invoke path specifically so "this tier answers worse" could be separated from "this query is hard". **Two of the three planned tier decisions did not survive contact with data.**

  **The mechanism works.** All tiers fire correctly; `subQueries` presence routes as designed; the cache path preserves it.

  **`nova-micro` — REJECTED.** The first smoke test showed it blocked, but a single sample cannot tell a bad tier from a hard query, and P05 already measured grounding scores swinging 0.30–0.72 on *identical* input. Re-tested properly on a query the corpus definitively answers, **n=10**:
  - `nova-micro`: mean **0.741**, stdev 0.028, **8/10 BLOCKED**
  - `nova-lite`: mean **0.917**, stdev 0.016, **0/10 blocked**

  Non-overlapping, and the failure mode is precise: nova-micro parks answers at ~0.74 against the guardrail's **0.75** threshold, so it converts a reliably-working answer into a refusal 80% of the time. A "cheap tier" that gets blocked is not a saving. Removed from both Lambdas.

  **`nova-pro` — VALIDATED, but only on the second attempt.** On the *first* complex query tried, pro looked useless: blocked 5/5, same as lite. That query turned out to be unanswerable from this corpus at all (cross-document synthesis — the same 6-doc topical narrowness P02 documented when its retrieval eval saturated), so it couldn't discriminate anything. Re-tested on a genuinely multi-part query the corpus **can** answer, **n=8**:
  - `nova-pro`: mean **0.924**, stdev 0.009, range [0.91, 0.93], **0/8 blocked**
  - `nova-lite`: mean **0.794**, stdev 0.113, range [0.54, 0.88], **2/8 blocked**

  Non-overlapping. Notably the win is **stability as much as strength** — pro's stdev is ~12× tighter, and it's nova-lite's *variance* (dipping to 0.54 and 0.73) that pushes it under the threshold, not its average. Kept for the decomposed path.

  **maxTokens tiering — REJECTED as solving a non-problem.** A real multi-part answer measured **141 tokens, 28% of the existing 500 budget** (pro's was 70). Raising the ceiling to 800 fixes nothing. All tiers now share `maxTokens: 500`, so the tier varies the *model* only.

  **Bug hit: P01's IAM lesson repeated, verbatim.** Routing to pro crashed `support-agent-loop` with `AccessDeniedException` on `bedrock:InvokeModel`. Cause: that Lambda runs under **`rag-assistant-agent-loop-role`**, not the shared `rag-assistant-lambda-role` — a separate, narrower role P05 scoped to **Nova Lite only**. I verified nova-pro access against the *shared* role and assumed it covered everything. This is exactly the failure P01 documented ("invisible in local testing because that ran under the broad CLI profile, not the Lambda's narrow execution role — always test under the real execution role"), and only the live invoke caught it. Fixed by adding the nova-pro ARN to `AgentInvokeModel` (now 2 resources).

  **Net outcome:** what shipped is narrower than planned — two tiers, not three; model-only, not model+budget — but every surviving decision has a non-overlapping measured distribution behind it.
  - `practice-02/lambda/generate/lambda_function.py`: the Step Functions workflow already carries a free complexity signal — `AggregateResults`'s `ResultSelector` includes `subQueries` (confirmed at `query-workflow.asl.json:148`), `SearchSimple`'s does not. Replace the hardcoded `GENERATE_MODEL = "amazon.nova-lite-v1:0"` / `maxTokens: 500` (lines 11, 169) with a 3-way pick: subQueries present → `nova-pro` + higher maxTokens; no subQueries + short query → `nova-micro` + lower maxTokens; else keep `nova-lite` + 500 as today's default.
  - `practice-05/lambda/support-agent-loop/lambda_function.py`: same idea — replace fixed `MODEL_ID`/`maxTokens: 600` (lines 17, 127) with a tier computed once from `user_message` before the tool loop starts (line ~118), held fixed through all `MAX_TOOL_ITERATIONS=5` rounds to avoid inconsistent tool-schema behavior mid-loop.
  - **Deliberately not touched**: `ticket-generate-response` — its model call lives inside a managed Bedrock Prompt Flow (`FLOW_ID = "KGO3XOMZI5"`, confirmed — `start_flow_execution`/`get_flow_execution`, no direct `converse()`/`invoke_model` call in the Lambda itself), so retrofitting this means editing and republishing a Prompt Flow version, not a Lambda code change. **Decision: document as a deliberate non-build** (same pattern as P05 Stage 13's skip) — not touched in this practice.
  - Follow this repo's established convention: duplicate the complexity-estimate helper per-Lambda rather than introducing a shared Layer (the one existing Layer, `jsonschema-layer`, is for a third-party dependency, not shared business logic — `mask_pii` etc. are already copy-pasted across Lambdas today).

- [x] **Stage 5 — Conversation-history pruning. REJECTED as a documented non-build (was planned as a BUILD item).** Measured before building, on the Stage 4 lesson that a planned improvement can turn out to solve a non-problem. **Two independent findings, either of which is sufficient on its own:**

  **1. There is no conversation history in this system to prune.** The assignment's `prune_context(conversation_history, max_tokens, preserve_last_n_turns=2)` is a multi-turn-chat construct. Every Bedrock call in the entire repo seeds `messages` with exactly one user message and no prior turns — `support-agent-loop:164`, `ticket-chat-stream:74`, `ws_ask:146`. `preserve_last_n_turns` has nothing to operate on. The plan had already noted `ticket-chat-stream`/`LiveChat.jsx` are stateless per call; that turns out to be true of *every* path, including the agent loop.

  **2. Even the within-request tool accumulation doesn't need pruning.** The plan's premise was that `messages` grows across up to `MAX_TOOL_ITERATIONS=5` rounds. Measured against the live Lambda:

  | scenario | iterations | tool calls | peak context | % of 300K window |
  |---|---|---|---|---|
  | single tool call | 2 / 5 | 1 | 223 | 0.07% |
  | KB search | 2 / 5 | 1 | 1,734 | 0.58% |
  | multi-step (pro tier) | 2 / 5 | 2 | 5,823 | 1.94% |
  | **adversarial** — 6 doc searches forced in one query | **2 / 5** | **6** | **10,462** | **3.49%** |

  **The loop never reached 3 iterations, let alone 5** — including the adversarial case built specifically to force serial tool use. The reason is behavioural: the model **batches tool calls within a single iteration** (6 calls in iteration 0) rather than serialising them across iterations, so context does not grow the way the plan assumed. Worst measured case leaves a ~29× margin against the context window, and the cost of the un-pruned context on that worst case is a fraction of a cent.

  **Cost of building it anyway:** bundling `tiktoken` into `support-agent-loop`, which practice-05 documented as the source of three separate distinct bugs (macOS wheels that fail silently at Lambda runtime; the hidden cold-start BPE-blob network fetch requiring `TIKTOKEN_CACHE_DIR`; and a redeploy that silently dropped the vendored package). Plus a genuine correctness risk: pruning a tool result the model still needs would make it re-call the tool, costing *more* than it saves.

  **Verdict: reject.** Would become justified if `MAX_TOOL_ITERATIONS` were raised substantially, if the KB returned many more chunks per search, or — most likely — if genuine multi-turn agent chat were added. None of those is true today. Not built. Plug into `support-agent-loop`'s tool loop (`lines 118-174`) — the only place in the repo where a `messages` list actually grows across multiple Bedrock calls in one request (up to 5 rounds, each potentially adding 3 KB chunks from `search_knowledge_base`). Before each `converse()` call after the first, estimate running token count with the same `tiktoken`/`cl100k_base`/`TIKTOKEN_CACHE_DIR` packaging trick already proven in `ticket-submit` (lines 6, 22) — not the spec's crude `len(text)//4`. If over budget, drop/truncate oldest tool-result blocks, preserving system prompt + latest exchange. Requires bundling `tiktoken` into `support-agent-loop`'s deployment zip (doesn't have it today).

- [x] **Stage 6 — Fixed-cardinality operational metrics. DONE, built as planned.** Extended `generate`'s existing metrics path with a second emitter, `_emit_ops_metrics()`, publishing to the new **`RagAssistant/Ops`** namespace: `InputTokens`, `OutputTokens`, `TokenCount`, `Latency`, `ErrorCount` — **dimensioned by `ModelId` only**.

  **The cardinality fix is the substance of this stage.** The assignment's `track_request()` dimensions every metric by `RequestId`, which mints a brand-new CloudWatch custom metric per request. Custom metrics bill **per metric per month for existing, not for use** — the one standing cost in this whole account — so that single line would convert a fixed ~$0.60/month into an unbounded bill that grows with traffic and never shrinks. Verified after deploy: exactly **10 metric series (5 metrics × 2 ModelId values)**, and the ceiling is the tier set, not the request count.

  Token counts are read off the Converse response's `usage` block rather than re-encoded with tiktoken — free, and they're the real billed figures rather than an estimate. Live values confirmed flowing (e.g. nova-lite `InputTokens` avg 1,463, `Latency` avg 1,169 ms; nova-pro `TokenCount` 4,910, `Latency` 1,700 ms).

  **Finding worth keeping:** a guardrail-**blocked** response still carries a `usage` block, so token metrics are emitted even when the answer is rejected. That's the behaviour you want — those tokens were billed regardless — but it means `TokenCount` counts spend, not successful answers, and the two must not be conflated when reading the dashboard. `ErrorCount` is emitted as an explicit `0` on success rather than only on failure, so the metric has a denominator instead of only firing when something breaks. Extend `generate`'s existing `_emit_metrics()` helper (line 99, already publishing `GuardrailAction`/`GroundingScore` to `RagAssistant/Guardrails` since P05 Stage 11) to also publish `TokenCount`, `Latency`, `ErrorCount` to a new namespace **`RagAssistant/Ops`** — **dimensioned by `ModelId` only**. This fixes a real bug in the bonus spec's reference code: `track_request()` dimensions every metric by `RequestId`, which is a CloudWatch custom-metric cardinality explosion (this repo's own "standing cost watch-list" flags custom-metric storage as the one thing that bills for existing, not just for use — see practice-02/05 READMEs). Read `usage.inputTokens`/`usage.outputTokens` directly off the `converse()` response rather than re-encoding with tiktoken.

- [x] **Stage 7 — Token-usage anomaly detection. DONE, built as planned.** New Lambda `token-anomaly-check` (`practice-06/lambda/token-anomaly-check/`), on a **classic EventBridge Rule** `rag-assistant-token-anomaly-schedule` at `rate(1 hour)` — deliberately the `events.amazonaws.com` pattern P02 already proved with `rag-assistant-doc-sync-schedule` → `check-and-sync`, not EventBridge **Scheduler**, which P02 documented as a different product with a different principal (`scheduler.amazonaws.com`).

  **The reference implementation's bug, and the fix.** The assignment's `TokenUsageMonitor` keeps `self.token_history = {}` in memory on the class instance. Lambda instances are ephemeral and not shared across concurrent invocations, so that dict resets on every cold start and never accumulates a window — implemented literally it would either never fire or fire on noise from a two-sample "history". Here CloudWatch *is* the history: Stage 6's `TokenCount`/`ModelId` series is durable, shared, and already being written.

  **Guards added that the reference lacks**, both learned from practice-05:
  - `MIN_BASELINE_POINTS = 5` — refuses to judge rather than computing a "2 sigma" verdict off 2 datapoints. That is precisely the single-sample trap P05 retracted a finding over.
  - Zero-variance baseline is handled explicitly. A fixed prompt shape produces near-identical token counts, so `stdev == 0` is a real state; dividing by it would make any trivial drift infinitely anomalous.

  **Verification — two halves, both done:**
  - *Anomaly math*, unit-tested locally against injected datapoints, 5 cases: steady traffic → `normal`; **token spike → `anomaly` (z=+543)**; **token collapse → `anomaly` (z=-214)**; zero-variance baseline with small drift → `normal` (not a divide-by-zero); thin baseline → `insufficient_baseline`. Exactly 2 `TokenUsageAnomaly` emissions, as expected. An untested detector is not a verified detector.
  - *CloudWatch read path*, verified live end-to-end against real Stage 6 data — correctly partitions baseline vs recent windows and correctly reports `no_recent_data` / `insufficient_baseline`.

  **Bug hit: CloudWatch custom-metric ingestion lag is ~2–3 minutes, not seconds.** Two consecutive live checks returned `no_recent_data` for traffic generated 30 s earlier, which read as a broken query path. Direct `get_metric_statistics` confirmed the data simply wasn't queryable yet. Worth knowing before trusting any "the metric didn't fire" conclusion — and a reason the hourly schedule is safe while a per-minute one would race ingestion.

  **Honest limitation:** the anomaly *emission* has been proven against injected data, not against a real 24-hour accumulated baseline — this system has no continuous traffic to build one. Window overrides (`baseline_hours`/`recent_minutes`/`min_baseline`) were added to the handler specifically so the detector remains testable rather than requiring a 24-hour wait to learn whether it works.

  **IAM:** required a new statement — `CloudWatchReadMetrics` (`GetMetricStatistics`, `GetMetricData`, `ListMetrics`). The role had only `PutMetricData`. Note these read APIs **do not support a resource ARN or a `cloudwatch:namespace` condition**, unlike `PutMetricData`, so this one is necessarily `Resource: "*"` — scoped to metric reads only. Role now has 26 statements. Built on Stage 6's metrics, not the reference code's approach: `TokenUsageMonitor.token_history` in the spec is an in-memory Python dict on a Lambda instance — Lambda instances are ephemeral and not shared across concurrent invocations, so this resets on every cold start and never accumulates a real window. **Decision: periodic EventBridge-scheduled Lambda**, not an inline per-request check — same proven pattern as `rag-assistant-doc-sync-schedule` → `check-and-sync`, avoiding added latency on the user-facing `generate` path. It pulls a trailing window back from CloudWatch via `get_metric_statistics`/`get_metric_data` (same `TokenCount`/`ModelId` metric from Stage 6), computes `statistics.mean`/`statistics.stdev` (same library already used in P05's eval scripts), and emits a `TokenUsageAnomaly` count metric (dimensioned by `ModelId` only) to `RagAssistant/Ops` when >2 std dev out.

- [x] **Stage 8 — Cost-capability tradeoff reporting. DONE.** Script: `cost_capability_report.py`.

  **Pricing re-verified, not copied.** Checked against the Bedrock pricing page 2026-08-18: `nova-micro` ($0.000035/$0.00014 per 1K) and `nova-lite` ($0.00006/$0.00024) in `benchmark_models.py` were **correct as written**. `nova-pro` added at **$0.0008 input / $0.0032 output — roughly 13× nova-lite on both**, which is what makes Stage 4's pro tier a genuine tradeoff rather than a free upgrade.

  **Scope was larger than planned: 2 Lambdas, not 1.** The plan assumed `record-metrics` could compute cost on its own. It can't — it receives `model_used` but no token counts, because `analyze`'s `_invoke_with_retry()` returned only `response["output"]...["text"]` and **discarded the `usage` block entirely**. Cost was unknowable downstream. Fixed by carrying `usage` through `_invoke_with_retry` → `analyze_document` → the response body, then computing in `record-metrics`. Safe against P02's documented ResultSelector trap: `ProcessDocument` selects `$.Payload.body` wholesale, so added keys need no ASL change.

  **Design detail that matters:** `estimate_cost()` returns `None`, not `0`, when the model or token counts are unknown, and the cost fields are omitted from the DynamoDB item entirely rather than written as zero. A missing cost and a genuinely free request must not look identical, or every average computed downstream is silently wrong. Verified live — new rows carry `input_tokens`/`output_tokens`/`estimated_cost_usd`; the 6 pre-Stage-8 rows correctly show absent rather than zero.

  **The report reads real data and refuses to over-claim.** The assignment's `analyze_cost_capability_tradeoff()` runs off a hand-written 5-row `test_history` and will happily recommend "downgrade these to a cheaper model" from a single row per model. This one scans the real `RoutingMetrics` table and applies a `MIN_SAMPLES = 3` guard — on the current 2 priced rows it reports *"too few samples to recommend anything. This is a gap to fill, not a finding."* rather than ranking. Same guard philosophy as Stage 7.

  **Most useful output — the counterfactual.** Priced against the same observed token volume:

  | if everything ran on | total | vs actual |
  |---|---|---|
  | nova-micro | $0.00012582 | −$0.00005103 |
  | nova-lite | $0.00021570 | +$0.00003885 |
  | **nova-pro** | **$0.00287600** | **+$0.00269915 (~16×)** |
  | claude-haiku-4-5 | $0.00447500 | +$0.00429815 |

  This is the number that makes Stage 4's decision concrete: routing decomposed queries to nova-pro buys a measured grounding improvement (0.924 vs 0.794, 0/8 vs 2/8 blocked) at roughly **16× the token cost**. Both halves are now measured, so the tradeoff is a choice rather than a guess. The report closes by pointing back at Stage 4's quality data, because a cheaper per-token rate that buys guardrail refusals is not cheaper.

- [ ] **Stage 9 — DEFERRED, not attempted.** Business-impact tracker (satisfaction ratings, `SupportTickets` fields, new Lambda + REST route, local HTML page). Deliberately deferred at the wrap-up point in favour of documenting the live resources Stages 0-8 created. Nothing was built, so there is nothing to tear down for this stage. Extend `practice-03/lambda/record-metrics/lambda_function.py` (already writes `model_used`/`complexity`/`document_type`/`timestamp` per real request to `RoutingMetrics`) to also compute/store an `estimated_cost` field, using a corrected copy of `practice-01/benchmark_models.py`'s `PRICING_PER_1K_TOKENS` dict — confirmed it currently only has entries for `nova-micro`, `nova-lite`, and `claude-haiku-4-5`, **missing `nova-pro`** (needed if Stage 4 starts routing complex queries to it) — must add and verify against current Bedrock pricing before trusting. Then a new one-off reporting script (same shape as `benchmark_models.py`) reading real `RoutingMetrics` data instead of the spec's synthetic `test_history`, producing the same "optimal model per complexity tier + recommendations" output. No new Lambda, no new table.

- [ ] **Stage 9 — Business-impact tracker.**
  - Extend `SupportTickets` with new attributes: `satisfaction_rating` (1-5), `feedback_text`, `resolved_at`, and a genuine `status="resolved"` value (today's enum is only `received`→`responded`, and `responded` — set by `crm-mock-update`, confirmed line 27 — means "the AI answered," not "the customer confirmed resolution").
  - New thin Lambda (justified the same way P05 justified `crm-agent-actions`: no existing Lambda owns a customer-initiated post-response update — `get-ticket` is read-only) wired to a new route on the existing REST API Gateway, writing rating/feedback/resolved_at via `update_item`, then emitting `UserSatisfactionRating`/`TimeToResolution` to a new namespace **`RagAssistant/BusinessImpact`** — **dimensioned by ticket `category` only**, fixing the same `ConversationId`-dimension cardinality bug present in the spec's `track_user_satisfaction()`.
  - `IssueResolutionRate` computed on-demand via a Stage-8-shaped script querying `SupportTickets` directly (a rate is better computed from the source table than approximated as a live CloudWatch counter).
  - **UI: a small local static-HTML page** (single self-contained file, same convention as `practice-02/ui/index.html` — the pre-P04 pattern, not a React/Amplify build) to look up a ticket and submit a rating/feedback against the new API route, enough to demo and manually test the end-to-end flow without extending practice-04's deployed React app.

## New model-ID / IAM concerns

- Every bonus-spec code snippet uses dead model IDs (`anthropic.claude-instant-v1`/`claude-v2`/`claude-3-sonnet-20240229-v1:0`, confirmed retired). All new code uses `amazon.nova-micro-v1:0`/`nova-lite-v1:0`/`nova-pro-v1:0` only, matching every other practice in this repo.
- `rag-assistant-lambda-role`'s `CloudWatchPutMetrics` statement is scoped to the single namespace `RagAssistant/Guardrails` — Stages 6, 7, and 9 all publish outside that scope and need Stage 1's IAM widening first or they'll get `AccessDenied`.

## Verification

- Each Lambda change: invoke directly via AWS CLI (`aws lambda invoke`) with representative payloads before/after, matching how every prior practice validated Lambda changes in this repo — no local test harness exists for these, consistent with the repo's established pattern (see P04's pytest suite, which is scoped to pure-logic-only, not live AWS calls).
- Stage 6/7 metrics: confirm via `aws cloudwatch get-metric-statistics` that the new namespace/metrics appear with the expected dimensions (and only those dimensions — re-check cardinality before calling it done).
- Stage 4: run one query through each complexity path (simple/no-decomposition vs. complex/decomposed) and confirm the model/maxTokens actually differ in the Lambda's CloudWatch logs.
- Stage 9: manually submit a rating through the local static-HTML page and confirm the DynamoDB item and CloudWatch metric both update.
- Write up practice-06/README.md and practice-06/SETUP-LOG.md at the end, following the exact structure of practice-05's (stage-by-stage narrative + full resource table with cost/teardown columns), including the two evaluate-and-reject stages documented as real findings, not omitted.
