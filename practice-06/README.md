# Practice 06 — Cost, performance and observability optimisation

Three "bonus assignment" specs ([`practice-06.md`](./practice-06.md)) asking for 15 separate
optimisations across token efficiency, latency, and monitoring. Built on top of practices 02-05's
existing infrastructure rather than from scratch, following this repo's established pattern.

**The short version: of the 15 asks, 4 were already built, 4 turned out to be actively harmful or
inapplicable when measured, and 4 were worth building. The measurements are the point.**

This practice ended up being less about adding features than about testing whether the assignment's
suggestions were actually good ideas on this system. Four times the answer was no — and in two of
those cases the *reason* was the interesting part.

**Status:** Stages 0-8 built and verified live. Stage 9 (business-impact tracker) deferred, never
built. Full resource list and teardown in [`SETUP-LOG.md`](./SETUP-LOG.md); stage-by-stage detail
in [`PLAN.md`](./PLAN.md).

---

## What was skipped, and why

Four asks were already fully built in earlier practices. Rebuilding them would have been pure
duplication:

| Ask | Already exists as |
|---|---|
| Response streaming | `ws_ask`, `analyze-stream`, `ticket-chat-stream` — all `converse_stream` + `post_to_connection` (P02/03/04) |
| Precomputed-response cache | `query_router` + the `RagQueryCache` table, TTL 3600s (P02) |
| Parallel model calls in a workflow | `query-workflow.asl.json`'s Map state, fanning out sub-question search (P02) |
| X-Ray tracing + dashboards | X-Ray active since P03; `practice-02/dashboard.json`, `practice-03/dashboard.json` |

A fifth — token estimation — already exists as **real `tiktoken` BPE counting** in `ticket-submit`.
The assignment's `len(text) // 4` heuristic would have been a downgrade, not an addition.

---

## Stage 2 — Prompt compression: measured 31% savings, rejected anyway

The assignment ships a `compress_prompt()` that strips filler phrases and, failing a reduction
target, truncates to `sections[0] + ". " + sections[-1]`. The plan predicted a near-zero saving on
this system's short, purpose-written prompts. **The prediction was wrong, and the real result is
worse.**

Run against six real prompt strings ([`prompt_compression_eval.py`](./prompt_compression_eval.py)),
with genuine `tiktoken` counts rather than the assignment's own estimator:

**31.3% fewer tokens.** The savings claim is numerically true.

But almost all of it comes from the truncation branch *deleting whole sentences*, and what it
deleted was load-bearing:

- **`generate`'s instruction** (49 → 23 tokens) lost the **`[Source N]` citation requirement** and
  the **"state that clearly" don't-guess instruction** — the entire anti-hallucination contract,
  gone.
- **A real retrieved chunk used as `grounding_source`** (126 → 60 tokens) lost **the answer fact
  itself** ("1,000 concurrent executions") and the per-Region qualifier. The guardrail would then
  score a correct answer as ungrounded, because the source no longer contains it.
- Where filler-removal alone applied, it achieved nothing: **1 token** saved on `query_router`, and
  **0 tokens saved on `query_expand` while still altering the text** — pure risk, zero benefit.

The one case where the compressor worked as advertised (32.6%, meaning intact) was the user's
**ticket free-text** — which isn't a prompt at all, is stored as a support record a human reads,
and already passes through P05's Comprehend PII masking. The single input it helps on is the one
you least want rewritten.

**The transferable lesson: a token counter cannot see this failure.** The headline number looks
like a clean win while the citation contract and the answer are being deleted.

---

## Stage 3 — nltk query preprocessing: rejected on a measurement, not an argument

The assignment's `QueryPreprocessor` does stopword removal, lemmatization, and synonym expansion —
techniques from the keyword/BM25 era. This system retrieves by embedding similarity, which is a
different mechanism, so rather than argue it,
[`query_preprocessing_eval.py`](./query_preprocessing_eval.py) measured it: embed each of P02's 10
real corpus questions twice with **the same model the Knowledge Base is indexed with**
(`amazon.titan-embed-text-v2:0`, 1024-d, normalized) — once raw, once preprocessed — and compare.

**Mean cosine 0.8724 (min 0.7881, max 0.9532). Every single query landed below 0.95.**

So preprocessing isn't a harmless no-op; it **materially relocates the query** in the exact space
the KB is indexed in, by ~0.13 cosine. For scale, P02 measured Titan v2's entire
similar-vs-dissimilar separation gap at **0.599 vs 0.454** — so 0.13 is a large fraction of the
model's meaningful signal range. And the *direction* of that move is unverifiable here, because P02
documented its retrieval eval **saturates at 1.000** on this 6-document corpus.

The hand-maintained term dictionary also rotted on first contact. It has no `on-demand` entry, so
the hyphen split plus stopword removal of "on" turns **"on-demand capacity mode" into "demand
capacity mode"** — a different concept, in a corpus where on-demand vs provisioned is the exact
distinction being asked about. Lemmatization also mangles product names ("Step Functions" → "step
function") and destroys question structure ("**How many** times..." → "**many** time...").

---

## Stage 4 — Complexity-tiered model selection: built, then two-thirds retracted

The idea: route simple queries to a cheap model, complex ones to an expensive model. The complexity
signal is free — `query-router` already pays for an LLM classification, and its result is readable
off the workflow output (`AggregateResults` emits `subQueries`, `SearchSimple` doesn't). It also
**survives a cache hit**, since `ReturnCached` replays the cached result verbatim.

Three tiers were built, then A/B'd against the live guardrail with the query held constant and only
the model varied ([`tier_quality_check.py`](./tier_quality_check.py)). A `tier` override was added
to `generate`'s direct-invoke path specifically so *"this tier answers worse"* could be separated
from *"this query is hard"*.

**`nova-micro` — rejected.** On a query the corpus definitively answers, n=10:

| | mean grounding | stdev | blocked |
|---|---|---|---|
| nova-micro | **0.741** | 0.028 | **8/10** |
| nova-lite | **0.917** | 0.016 | **0/10** |

Non-overlapping, and the failure mode is precise: nova-micro parks answers at ~0.74 against the
guardrail's **0.75** threshold, converting a reliably-working answer into a refusal 80% of the time.
**A cheaper per-token rate that buys guardrail refusals is not cheaper.**

**`nova-pro` — kept, but only after a false negative.** On the first complex query tried it looked
useless (blocked 5/5, same as lite) — but that query turned out to be unanswerable from this corpus
at all, the same topical narrowness that saturated P02's retrieval eval, so it couldn't discriminate
anything. Retested on a multi-part query the corpus *can* answer, n=8:

| | mean grounding | stdev | range | blocked |
|---|---|---|---|---|
| nova-pro | **0.924** | 0.009 | [0.91, 0.93] | **0/8** |
| nova-lite | **0.794** | 0.113 | [0.54, 0.88] | **2/8** |

Non-overlapping. Notably **the win is stability as much as strength** — pro's stdev is ~12× tighter,
and it's lite's *variance* (dipping to 0.54) that pushes it under the threshold, not its average.

**maxTokens tiering — rejected as solving a non-problem.** A real multi-part answer measured **141
tokens, 28% of the existing 500 budget**. Raising the ceiling to 800 fixes nothing. All tiers now
share `maxTokens: 500`; the tier varies the model only.

**A single sample would have got this backwards in both directions** — the first micro test blamed
the wrong cause, and the first pro test would have rejected a tier that works. P05's retraction
lesson applied directly to this practice's own work.

---

## Stage 5 — Conversation-history pruning: rejected, premise doesn't hold

Planned as a build item; measured first, on Stage 4's lesson. **Two independent disqualifiers:**

**There is no conversation history in this system.** The assignment's
`prune_context(conversation_history, preserve_last_n_turns=2)` is a multi-turn-chat construct. Every
Bedrock call in the entire repo seeds `messages` with exactly one user message and no prior turns —
`support-agent-loop`, `ticket-chat-stream`, `ws_ask` alike. There is nothing to preserve or drop.

**Even within-request tool accumulation doesn't need it.** The premise was that `messages` grows
across up to `MAX_TOOL_ITERATIONS = 5` rounds. Measured against the live Lambda:

| scenario | iterations | tool calls | peak context | % of 300K window |
|---|---|---|---|---|
| single tool call | 2 / 5 | 1 | 223 | 0.07% |
| KB search | 2 / 5 | 1 | 1,734 | 0.58% |
| multi-step (pro tier) | 2 / 5 | 2 | 5,823 | 1.94% |
| **adversarial** — 6 searches forced | **2 / 5** | **6** | **10,462** | **3.49%** |

**The loop never reached 3 iterations**, including the adversarial case built to force serial tool
use. The reason is behavioural: the model **batches tool calls within one iteration** rather than
serialising them across iterations, so context doesn't grow the way the plan assumed.

Building it anyway would have meant bundling `tiktoken` into the Lambda — which P05 documented as
the source of three separate bugs (macOS wheels failing silently at runtime, the hidden cold-start
BPE-blob fetch, and a redeploy that dropped the vendored package) — plus a real risk that pruning a
tool result the model still needs makes it re-call the tool, costing *more*.

---

## Stage 6 — Operational metrics, and the cardinality trap

Five metrics (`InputTokens`, `OutputTokens`, `TokenCount`, `Latency`, `ErrorCount`) to a new
`RagAssistant/Ops` namespace, **dimensioned by `ModelId` only**.

**The cardinality fix is the whole substance of this stage.** The assignment's `track_request()`
dimensions every metric by `RequestId`. CloudWatch custom metrics **bill per metric per month for
existing, not for use** — the one standing cost in this account — so that single line converts a
fixed, negligible charge into an unbounded one that grows with traffic and never shrinks. Verified
after deploy: **exactly 10 series**, and the ceiling is the tier count, not the request count.

Token counts come off the Converse response's `usage` block rather than a tiktoken re-encode — free,
and they're the real billed figures rather than an estimate of them.

**Worth knowing:** a guardrail-**blocked** response still carries `usage`, so token metrics fire even
when the answer is rejected. That's correct — those tokens were billed — but it means `TokenCount`
measures *spend*, not successful answers, and conflating the two would misread the dashboard.
`ErrorCount` is emitted as an explicit `0` on success so the metric has a denominator.

---

## Stage 7 — Anomaly detection, fixing a Lambda-statelessness bug in the reference code

The assignment's `TokenUsageMonitor` keeps `self.token_history = {}` in memory on the class instance
and flags anything beyond 2σ. **That cannot work on Lambda**: instances are ephemeral and not shared
across concurrent invocations, so the dict resets on every cold start and never accumulates a real
window. Implemented literally it would either never fire or fire on noise from a two-sample history.

Here **CloudWatch is the history** — Stage 6's `TokenCount`/`ModelId` series is durable, shared, and
already being written. The check runs on a scheduled Lambda rather than inline, so it adds no
round-trip to the user-facing `generate` path.

Two guards the reference lacks, both from P05:

- **Refuses to judge below 5 baseline points** rather than computing a "2σ" verdict from 2
  datapoints — precisely the single-sample trap P05 retracted a finding over.
- **Handles zero-variance baselines explicitly.** A fixed prompt shape produces near-identical token
  counts, so `stdev == 0` is a real state; dividing by it would make any trivial drift infinitely
  anomalous.

Verified in two halves: the anomaly math unit-tested across 5 cases (spike → z=+543, collapse →
z=−214, steady → normal, zero-variance → normal, thin baseline → refused), and the CloudWatch read
path verified live. **Honest limitation:** emission is proven against injected data, not a real
24-hour accumulated baseline — this system has no continuous traffic to build one. Window overrides
were added to the handler so the detector stays testable rather than requiring a 24-hour wait.

---

## Stage 8 — Cost reporting from real data, and what nova-pro actually costs

Pricing was **re-verified against the Bedrock pricing page**, not copied: `nova-micro` and
`nova-lite` in `benchmark_models.py` were correct as written; **`nova-pro` added at $0.0008 input /
$0.0032 output per 1K — roughly 13× nova-lite on both.**

Scope was larger than planned. `record-metrics` couldn't compute cost alone, because `analyze`'s
`_invoke_with_retry()` returned only the response text and **silently discarded the `usage` block** —
not a crash, just a return statement that dropped the billing data. Fixed by carrying `usage`
through to the response body.

A small but important design choice: `estimate_cost()` returns `None`, not `0`, when the model or
token counts are unknown, and the fields are omitted from the DynamoDB item rather than zeroed. **A
missing cost and a genuinely free request must not look identical**, or every average computed
downstream is silently wrong.

[`cost_capability_report.py`](./cost_capability_report.py) reads the real `RoutingMetrics` table
rather than the assignment's hand-written `test_history`, and applies a `MIN_SAMPLES = 3` guard — on
the current data it reports *"too few samples to recommend anything. This is a gap to fill, not a
finding"* rather than ranking off 2 rows, which is what the reference version would happily do.

**The most useful output is the counterfactual** — the same observed token volume priced at each
model's rate:

| if everything ran on | total | vs actual |
|---|---|---|
| nova-micro | $0.00012582 | −$0.00005103 |
| nova-lite | $0.00021570 | +$0.00003885 |
| **nova-pro** | **$0.00287600** | **+$0.00269915 (~16×)** |
| claude-haiku-4-5 | $0.00447500 | +$0.00429815 |

This makes Stage 4 concrete: routing decomposed queries to nova-pro buys a measured grounding
improvement (0.924 vs 0.794, 0/8 vs 2/8 blocked) at roughly **16× the token cost**. Both halves are
now measured, so it's a choice rather than a guess.

---

## Stage 9 — deferred

The business-impact tracker (satisfaction ratings on `SupportTickets`, a new Lambda and REST route,
and a local HTML page) was deliberately deferred at the wrap-up point in favour of documenting the
live resources Stages 0-8 created. Nothing was built. The IAM condition widening in Stage 1 already
pre-authorises the `RagAssistant/BusinessImpact` namespace it would use, and the cardinality fix it
needs is recorded in [`PLAN.md`](./PLAN.md): dimension by ticket `category`, never `ConversationId`,
which carries the same per-request cardinality bug as Stage 6's `RequestId`.

---

## Bugs and gotchas found

1. **P01's IAM lesson repeated verbatim.** Routing to nova-pro crashed `support-agent-loop` with
   `AccessDeniedException`. I'd verified nova-pro against the *shared* `rag-assistant-lambda-role` —
   but that Lambda runs under **`rag-assistant-agent-loop-role`**, a separate, narrower role P05
   scoped to Nova Lite only. Exactly what P01 warned about: *always test under the real execution
   role*. Only the live invoke caught it.
2. **CloudWatch custom-metric ingestion lag is ~2-3 minutes, not seconds.** Two consecutive live
   checks returned `no_recent_data` for traffic generated 30s earlier — indistinguishable from a
   broken query path until direct `get_metric_statistics` confirmed the data wasn't queryable yet.
   A reason an hourly schedule is safe where a per-minute one would race ingestion.
3. **`analyze` silently discarded the Converse `usage` block**, making per-request cost unknowable
   downstream. Found only by trying to compute cost in Stage 8.
4. **Reference-code defects** (documented, not implemented): `RequestId` as a CloudWatch dimension
   (unbounded metric cardinality); `ConversationId` likewise in the satisfaction tracker;
   `token_history` as in-memory Lambda state; `len(text)//4` token estimation where real BPE
   counting already exists; and dead model IDs throughout (`anthropic.claude-instant-v1`,
   `claude-v2`, `claude-3-sonnet-20240229-v1:0`), all confirmed retired.

---

## What this practice actually taught

Four of the assignment's fifteen asks were already solved. Four more were **wrong for this system**,
and only measurement revealed it — three of those four looked entirely reasonable on paper, and one
(prompt compression) even produced a *true* headline number while quietly deleting the anti-hallucination
contract and the answer itself.

The pattern that keeps recurring across P05 and now here: **a single sample points the wrong way
often enough that it can't be trusted.** It happened three separate times in this practice alone —
nova-micro blamed on the wrong cause, nova-pro nearly rejected on an undiscriminating query, and
Stage 5 nearly built on an assumption about loop behaviour that the model doesn't actually exhibit.

And the cheapest lesson of all: of the six items planned as builds, **one shipped as designed, one
shipped substantially narrowed, one was rejected outright, and one was deferred.** Planning
predicted the work; measurement decided it.

---

_Part of [Gen AI Practice](../README.md)._
