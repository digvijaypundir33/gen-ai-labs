# Series 2 — Is the evidence any good?

Series 1 built things: six practices, each one an AWS exam-prep assignment built for real on
my own account (multi-model routing, RAG, async pipelines, a support-ticket system, guardrails,
cost/observability). Along the way it produced a lot of numbers — 97% guardrail accuracy, a
"cheap tier saves nothing" verdict, MRR/NDCG tables, a fairness result that had to be retracted.

Series 2 asks the next question: **which of those numbers would survive being checked properly,
and which controls actually fire when they're supposed to?** It is less about building new
services and more about measuring, auditing and stress-testing what Series 1 left running.

The method is borrowed, with thanks, from
[Julie Elkins'](https://github.com/julie-elkins) evaluation work — in particular
[Production-AI-Engineering-Bridge-Lab](https://github.com/julie-elkins/Production-AI-Engineering-Bridge-Lab),
[llm-eval-validity](https://github.com/julie-elkins/llm-eval-validity),
[abstention-eval](https://github.com/julie-elkins/abstention-eval) and
[never-fired](https://github.com/julie-elkins/never-fired). The method is borrowed; the systems,
data and findings here are my own Series 1 stack.

## Practices

| # | Practice | The question | Builds on | Est. cost | Status |
|---|----------|--------------|-----------|-----------|--------|
| 07 | [Evaluation & QA capstone](./practice-07/) — [plan](./practice-07/PLAN.md) | Does Bedrock's managed evaluation agree with my hand-rolled one, and what does a quality gate need before it can be trusted? | P01 benchmark, P02 golden set, P05 judge lessons | < $0.50 | Planned |
| 08 | Abstention is a property of the prompt | If only the wording that permits "I don't know" changes, how far does the RAG assistant's refusal rate move? | P02 `generate`, `test_questions.py` | < $0.10 | Not started |
| 09 | Guardrails that never fired | Does every safety control in Series 1 actually fire — and when it breaks, does it fail open or closed? | P01/P04 circuit breakers, P04 authorizer, P05 guardrail + moderation, P06 anomaly alarm | < $0.10 | Not started |
| 10 | Is the grader trustworthy? | Do the graders behind Series 1's headline numbers agree with a human, and is the difference between two judges bigger than one judge's run-to-run noise? | P05 `guardrail_eval.py`, P06 `tier_quality_check.py`, P07 judge | < $0.50 | Not started |
| 11 | Data readiness, factorially | Across corpus × model × prompt × retriever, which axis actually moves accuracy? | P02 Knowledge Base, P05 agent loop, P10 validated grader | ~$1–2 | Not started |

Costs are estimates written before anything runs, assuming the cost rules below. The target is
**under ~$3 for the whole series, with $0 idle.** Each practice's write-up reports the measured
figure next to the estimate.

**Order and dependencies.** 07 → 08 → 09 → 10 → 11. 08 and 09 are independent and cheap, and
are where the series' habits (predictions first, evidence-based pass/fail) get practised on
small questions. 10 validates the judge 07 builds, and 11 is the capstone that relies on 10's
grader being trustworthy — running 11 on an unvalidated grader would repeat the exact mistake
10 exists to catch.

## Rules for every practice in this series

These are what make Series 2 different from Series 1. Each one is there because Series 1 hit
the problem it prevents.

1. **Predictions before data.** Each practice commits a `PREDICTIONS.md` — what I expect, and
   what result would prove me wrong — *in its own commit, before any model is called.* Scored
   honestly in the write-up, misses included. (Series 1: P06's plan predicted "near-zero
   token savings" for Stage 2 and it measured 31% — the miss was only visible because the
   prediction happened to be written down first. Here that's required, not incidental.)
2. **Answer keys are held back.** Where a practice plants defects or labels items, the key
   lives in a file the system under test never sees, and the assessment is written before
   the key is opened.
3. **Never a single run.** Anything a model scores is repeated (n ≥ 3, n ≥ 5 for judges), and
   reported as a distribution or an interval — never a lone number. (Series 1: the P05
   fairness retraction.)
4. **Pass/fail comes from evidence, not from what the model said.** An HTTP status, a
   CloudWatch datapoint, a DynamoDB row, a file that exists. A model narrating "I was
   blocked" is not evidence that it was.
5. **Results are committed and the numbers are reproducible offline.** Raw results go in
   `results/`; a report script re-renders every number in the write-up from those files with
   no AWS calls.
6. **Offline tests.** A `tests/` pytest suite that runs without credentials — the scorers,
   the prompt arms, the report logic. Not the models.
7. **A cost ceiling per run, and the real cost reported.** Every script that calls Bedrock
   takes a max-calls limit. Cost Explorer lags 24–48h, so the write-up reports cost from
   token usage, not from "looks cheap today".
8. **Teardown is run, not just written.** Anything a practice creates gets torn down and the
   teardown verified — or is explicitly left running with its idle cost stated.
9. **Corrections stay in place.** A wrong finding gets a visible correction, not a quiet edit.

## Keeping it near $0

This series exists to demonstrate methods, not to run anything in production. Its cost should
round to zero.

**Where things stand (checked 2026-11-14, us-east-1, read-only).** Nothing in the account
bills just by existing. There are no OpenSearch domains or collections, SageMaker endpoints,
provisioned throughput, custom models, NAT gateways, RDS or customer KMS keys. The Knowledge
Base runs on S3 Vectors, which costs about $0 when idle. The two dashboards and the one alarm
fall within CloudWatch's free tier. A $1 "Zero-Spend Budget" alert is already in place. The
only thing to pay for is tokens.

**Rules for spend:**

1. **Nova first.** Use Nova Micro or Nova Lite as both the model under test and the judge.
   Per the repo's verified pricing table, Nova Lite costs $0.06/$0.24 per 1M input/output
   tokens, and Claude Haiku 4.5 costs $1/$5, about 17–20× more. Claude models are
   **blocked** on this account (an AWS Marketplace `INVALID_PAYMENT_INSTRUMENT` problem, the
   same one P01 and P02 hit, re-confirmed 2026-11-14). Where an experiment needs a second
   family of judge models (P07, P10), use **`gpt-oss-120b`** at $0.15/$0.60. Mistral Large
   also works, but at $4/$12 it costs ~27× more.
2. **Cache every model call.** Every call goes through one helper that keys on
   `hash(model, prompt, params)` and writes the reply to `results/cache/`. Re-running a report,
   fixing a scorer or re-grading then reads from the cache instead of calling Bedrock again.
   It also serves rule 5 above: the cache *is* the committed evidence.
3. **Dry run first, then a pilot, then the real run.** Every script has a `--dry-run` that
   counts the calls and prices them from estimated tokens. Then a pilot runs 1 repetition on 3
   items. The full run comes only after the pilot's real `usage` figures confirm the estimate.
   `--max-calls` is a hard stop.
4. **Small outputs.** Cap `maxTokens` on everything. Judges return a single label or a short
   JSON object, not an essay. Output tokens cost 4–5× input tokens.
5. **Reuse outputs that already exist.** P10 re-grades the replies P05 and P06 already
   generated and saved, instead of generating new ones. Only the judge calls are new.
6. **No new standing infrastructure.**
   - P11 puts the dirty and clean corpus in the *existing* Knowledge Base, tagged with a
     `corpus_version` metadata attribute and filtered at query time. That means no second KB.
   - P11's keyword retriever is P02's local BM25, which costs nothing.
   - No Aurora, no OpenSearch, no Connect.
   - P07's managed evaluation job uses a ≤10-prompt dataset and programmatic metrics where
     possible, so it bills only a handful of generator calls.
7. **Fail before the model.** P09 mostly tests controls that block *before* Bedrock is
   called: the authorizer, request-schema validation and the circuit breaker. Proving those
   work costs Lambda and API Gateway requests, which fall within the free tier.
8. **Pin the region.** The CLI's default region is `ap-south-1`, but everything lives in
   `us-east-1`. Every script and command passes the region explicitly, so nothing gets
   created in the wrong region and forgotten.

**Housekeeping (done 2026-11-14):**
- Set 14-day retention on all 35 Lambda and state-machine log groups.
- Deleted three orphaned P01 log groups that its teardown had missed. The correction is in
  P01's `SETUP-LOG.md`.
- Deleted `jsonschema-layer` version 1, which nothing used anymore.
- Still optional: disable `rag-assistant-doc-sync-schedule` (daily) between practices.
  `rag-assistant-token-anomaly-schedule` is already disabled.
- New rule for every Series 2 teardown: the verification sweep includes CloudWatch Logs.

## Standard layout per practice

```
practice-NN/
  README.md               the write-up: question, design, findings, what it doesn't show
  PLAN.md                 stage-by-stage execution plan, checked off as it goes
  PREDICTIONS.md          committed before the first model call
  SETUP-LOG.md            every AWS resource created, its cost, how to tear it down
  results/                raw results, committed
  tests/                  offline pytest suite
  linkedin-post-draft.md  written last, from the findings
```

## The practices in more detail

### 07 — Evaluation & QA capstone
The existing Bonus Assignment 01 plan, kept as the opener because it's the one practice in this
series with an exam assignment behind it. Managed Bedrock Model Evaluations vs. P01's
hand-rolled benchmark; a six-dimension judge built with n ≥ 5 sampling and run alongside the
assignment's n = 1 version; claim-level hallucination checks vs. managed contextual grounding;
an `EvaluationResults` table and a scheduled quality gate that is deliberately regressed to
prove it fails. Full detail in [`practice-07/PLAN.md`](./practice-07/PLAN.md), which now also
follows the rules above (it gains a `PREDICTIONS.md` before Stage 1).

### 08 — Abstention is a property of the prompt
- **Items:** ~30 questions the P02 corpus *can* answer (from `test_questions.py`) and ~15 it
  can't (on-topic but not covered, out-of-scope, and false-premise). Answerability decided by
  hand against the corpus before any run.
- **Arms:** four prompt versions that differ *only* in how declining is offered — never
  mentioned / a bare "say UNANSWERABLE" / a menu of reasons / extra answer categories. A test
  asserts the rest of each prompt is byte-identical.
- **Measure:** declined-vs-answered, scored separately per population — declining an
  answerable question is a cost, declining an unanswerable one is correct. 3 runs per arm.
- **Why it matters for Series 1:** `generate`'s prompt has one specific way of offering
  "not in context". Any refusal rate quoted for it is partly a property of that wording.

### 09 — Guardrails that never fired
- **Inventory first:** list every control Series 1 relies on — Bedrock Guardrail (REST *and*
  WebSocket paths), Lambda authorizer, DynamoDB circuit breakers, API Gateway schema
  validation, the moderation workflow, the token-anomaly alarm.
- **For each, two tests:** (a) force it to fire and prove it from evidence; (b) break it on
  purpose — missing guardrail ID, throttling, a crashing authorizer, an unreachable table —
  and record whether traffic is **blocked or let through**.
- **Known lead:** P05 already found the WebSocket path had no guardrail coverage. This
  practice asks how many more of those exist.
- **Output:** a control matrix — control × fires-when-it-should × fails-open-or-closed —
  plus fixes for any control that fails open, each re-tested.

### 10 — Is the grader trustworthy?
- **Targets:** the graders behind P05's guardrail accuracy and P06's tier verdicts, plus
  P07's new judge.
- **Human reference:** I hand-label a stratified sample, blind to what the grader said.
- **Measure:** agreement (Cohen's kappa, and raw agreement — kappa alone can read zero on a
  near-unanimous stratum), confidence intervals rather than point estimates, two judge models
  × 5 runs, and results split by item type so a bad category can't hide in the average.
- **Possible outcome worth being ready for:** a Series 1 headline number gets a correction.

### 11 — Data readiness, factorially
- **Corpus:** a generated dirty version of the P02 corpus — contradictory versions,
  overlapping effective dates, stale duplicates — with a held-back defect ledger, plus a
  cleaned v2. Profiled blind, then scored against the ledger.
- **Grid:** corpus (dirty/clean) × model (2–3 tiers) × prompt (2) × retriever (keyword/KB),
  16–24 cells, several turns per cell, graded with P10's validated grader.
- **Tool layer:** P05's agent tools reworked to fail closed — explicit status and next action,
  no bare nulls, customer identity bound outside the model's reach — and measured as its own
  axis.
- **The question it settles:** whether Series 1 should have spent its effort on the data
  rather than the model and prompt choices.

## LinkedIn

Same format as Series 1's drafts (a hook line, numbered steps, the bug or retraction, the repo
link, hashtags). Series 2 adds two posts:

- **Kickoff post** — Series 1 recap in three lines, the Series 2 question, the rules above in
  one sentence, and what's coming.
- **One post per practice** — `linkedin-post-draft.md`, written from the findings after the
  write-up is done, never before. Lead with the prediction that missed if there was one.
- **Wrap-up post** — which Series 1 numbers survived, which didn't.

Hashtags: `#awsexamprep` on 07 (it's an exam assignment); `#genai #aws #bedrock #llmevaluation`
across the series.

## Backlog (possible later practices)

- **MCP tool server with identity bound out of the schema** — exposing P05's agent tools over
  MCP so the model never sees or chooses the customer ID.
- **Prompt caching, measured** — real cache-hit rates and cost on the RAG path, against the
  assumption that it's a free win.
