# practice-07: Evaluation & QA capstone (Bonus Assignment 01 + Content Domain 5)

Execution plan. **Depends on practice-06 being built first** — see Sequencing below. Work stage by stage; check a stage off before starting the next.

> **Now the opener of [Series 2](../README.md).** Paths into Series 1 are `series-1/practice-NN/` from the repo root (`../../series-1/practice-NN/` from here — e.g. `sys.path.insert(0, "../../series-1/practice-02")` to reuse `test_questions.py`). This practice also follows the Series 2 rules: commit a `PREDICTIONS.md` before Stage 1's first model call, keep raw results in `results/`, add an offline `tests/` suite, and write `linkedin-post-draft.md` last. P06 Stage 9 (the rating system Stage 6's feedback side would consume) was deferred and never built — treat user-feedback consumption as out of scope unless Stage 9 gets built first.

## Context

`practice-07/practice-07.md` is the last practice, and it's the evaluation one: Bonus Assignment 01 ("build a complete evaluation system for a customer support chatbot") plus the **Content Domain 5** exam material (Task 5.1 implement evaluation systems, Task 5.2 troubleshoot GenAI applications). No other files exist in `practice-07/` yet.

This repo already has a *lot* of evaluation work scattered across practices — `series-1/practice-01/benchmark_models.py` (multi-model quality/latency/cost benchmark), `series-1/practice-02/retrieval_quality.py` (hit-rate@k, MRR, NDCG across BM25/vector/RRF/rerank), `series-1/practice-02/test_questions.py` (a hand-verified golden set with `expected_doc` + `ground_truth`), and seven separate P05 eval scripts (guardrail corpus, grounding, fairness, confidence, cost comparisons). What it does **not** have is any of that running continuously, persisted anywhere, or gating anything — every eval in this repo is a one-off local script writing a local JSON file. That gap is what practice-07 is actually for.

The single most important finding going in: **the assignment's entire Module 1 is single-pass LLM-as-judge scoring — precisely the methodology practice-05 already proved produces convincing, reproducible-looking, false results** (the Stage 12 fairness retraction). The assignment hands over the exact broken pattern this repo has already documented. That's the headline narrative for this practice, and Stage 3 below is built to demonstrate it rather than just cite it.

### Defects in the assignment's reference code (document these, don't reproduce them)

Consistent with this repo's convention of reviewing the shipped reference code:
- **Truncated / non-functional**: `_calculate_efficiency_metrics` ends in a bare `return` (line 685); `_rank_models` is called (line 578) but never defined anywhere.
- **Doc structure leaked into code**: the string `"Step 2: Provide only the JSON response..."` is embedded mid-prompt-literal (line 212) — the markdown's own step numbering ended up inside the Python.
- **Broken entrypoints**: `if name == "main"` (lines 302, 465) instead of `if __name__ == "__main__"`.
- **Broken method binding**: `_extract_json_from_text` is defined at module level (lines 215, 412) but called as `self._extract_json_from_text` — would `AttributeError` at runtime.
- **Dead model IDs again**: `anthropic.claude-3-sonnet-20240229-v1:0`, `claude-instant-v1`, `claude-v2`, `amazon.titan-text-express-v1` — same stale set as practice-06's spec, all confirmed retired/unused in this account.
- **Crude token estimation**: `len(query.split()) * 1.3` for token counts, when `converse()` returns real `usage` figures for free and `ticket-submit` already does real `tiktoken` BPE counting.
- **Architecture diagram promises four pillars** (Quality Assessment, Model Comparison, User Feedback, Retrieval Evaluation) plus an Evaluation Database and Reporting Dashboard — but only Modules 1 and 2 have any code. User Feedback, Retrieval Evaluation, the database, and the dashboard are diagram-only.

## Decisions made

1. **Sequencing**: build practice-06 fully first, then practice-07. P07's eval framework then has real metrics and P06's rating system to work against, and nothing gets built twice.
2. **Scope**: deep on genuine gaps, not broad-and-thin. Document the already-covered areas as covered (with pointers), rather than rebuilding them for exam-surface completeness.
3. **Judge rigor**: build the quality evaluator with repeated sampling (n≥5) from the outset, **and** run the assignment's n=1 version alongside it to show the divergence concretely.

## Audit: P07 asks vs. what already exists

**SKIP — already built, would be a duplicate:**
- Multi-model comparison framework (Module 2) → `series-1/practice-01/benchmark_models.py` already runs the same query across models and scores weighted quality/latency/cost into `model_selection_strategy.json`. The assignment's `quality_per_token`/`quality_per_second` are a small delta, folded into Stage 2 rather than rebuilt.
- Retrieval quality testing (relevance scoring, context matching, retrieval latency) → `series-1/practice-02/retrieval_quality.py` already does hit-rate@k, MRR, and NDCG across four retrieval strategies. More thorough than what the assignment asks for.
- Golden/reference test set → `series-1/practice-02/test_questions.py` already exists, hand-verified against real corpus docs, and is already reused by P05's `guardrail_eval.py` and `grounding_test.py`. Reuse it again here; do not write a new one.
- LLM-as-judge as a *technique* → already used in P05's fairness work. What's missing is rigor and persistence, not the technique.
- User feedback / rating system → being built in **practice-06 Stage 9**. P07 consumes it, doesn't rebuild it.

**BUILD — real gaps:**

- [ ] **Stage 0 — Live audit + availability checks.** Confirm P06's stages landed and are still live (`RagAssistant/Ops` + `RagAssistant/BusinessImpact` namespaces, `SupportTickets` rating attributes, `RoutingMetrics` cost field). Then two genuine unknowns to resolve before planning further: **(a) is Amazon Bedrock Model Evaluations available and usable in this account/region** (P05 hit a hard block on Bedrock Agents Classic, so account-level restrictions are a real, precedented risk here), and **(b) what does a managed evaluation job actually cost** — it bills for the inference it runs, which is a real (if bounded) charge against a repo that has otherwise stayed near-zero idle cost. If either answer is bad, Stage 1 becomes a documented blocked-attempt (the P05 Agents Classic pattern), not a build.

- [ ] **Stage 1 — Amazon Bedrock Model Evaluations (managed) vs. P01's hand-rolled benchmark.** The headline. This repo has never touched the managed evaluation service — P01 hand-rolled `benchmark_models.py` instead. Run a managed automatic evaluation job over the existing `test_questions.py` golden set against the same Nova models P01 benchmarked, then compare: does the managed service's scoring agree with P01's word-overlap similarity proxy? Where do they diverge, and which one is actually right? This is the same managed-vs-hand-rolled comparison the repo has run before (P05: Bedrock Agents → hand-rolled tool loop; P05: managed contextual grounding → its own eval), and the answer is genuinely unknown in advance. **Cost note**: unlike almost everything else in this repo, an evaluation job is not $0-idle — record the real figure.

- [ ] **Stage 2 — Six-dimension quality evaluator, built with repeated-sampling rigor.** The assignment's Module 1: score responses on relevance, factual accuracy, consistency, fluency, helpfulness, completeness. Build it against the live `generate` Lambda's real answers over `test_questions.py`, using an **independent per-dimension rubric with n≥5 trials per item** — the exact correction P05's `fairness_thoroughness_check.py` had to apply after the retraction, applied from the start this time. Then **also run the assignment's n=1 single-pass version over the same items** and report both: how far apart are the scores, and would the n=1 run have supported a conclusion the n≥5 run refutes? Fold in Module 2's `quality_per_token`/`quality_per_second` efficiency metrics here, computed from real `converse()` `usage` figures rather than the spec's `len(text.split()) * 1.3` estimate. Use `nova-lite` or `claude-haiku-4-5` as the judge model — never a dead model ID, and note the judge-model choice as a documented variable (a judge inherits its own blind spots, already called out in P05's model card).

- [ ] **Stage 3 — Claim-level factual verification + hallucination rate.** The assignment's Task 1.2: decompose a response into individual factual claims, label each `supported` / `contradicted` / `not_mentioned` against retrieved context, and compute accuracy + hallucination scores. Genuinely new — P05 has Bedrock's **managed contextual grounding**, but that returns a single 0–1 score for the whole response, with no indication of *which* claim is unsupported. Run both over the same responses (including P05's known hallucination-prone question, already isolated in `grounding_test.py`) and answer: does claim decomposition catch anything the managed score misses, and is it worth the extra model calls? Apply repeated sampling here too — P05 proved the managed grounding score itself swings between 0.30 and 0.72 on identical inputs, so a single comparison run would be meaningless.

- [ ] **Stage 4 — Evaluation results persistence.** Every eval in this repo writes a local JSON file that nothing reads afterwards (`retrieval_quality_results.json`, `fairness_eval_results.json`, `embedding_evaluation_results.json`, …). Add a DynamoDB `EvaluationResults` table keyed by eval run + item, so Stages 1-3's scores become a queryable history instead of point-in-time artifacts. This is the prerequisite for Stage 5 — you cannot regression-test against a baseline you never stored. Keep it on-demand billing, consistent with every other table in this account.

- [ ] **Stage 5 — Regression suite + automated quality gate.** The highest-value item after Stage 1, and entirely absent today: P04's pytest suite is pure-logic unit tests (circuit breaker, authorizer, ticket-submit validation) with no output-quality coverage at all. Build a scheduled evaluation run over the golden set — same EventBridge-Rule→Lambda pattern already proven by `rag-assistant-doc-sync-schedule` → `check-and-sync` — that scores current output, compares against the stored Stage 4 baseline, and **fails loudly when quality regresses past a threshold**. This is what turns the repo's scattered one-off evals into an actual quality gate. Decide and document the threshold empirically from Stage 2's observed variance, not by picking a round number — P05's grounding-score variance data is the cautionary example for why an arbitrary fixed threshold misfires.

- [ ] **Stage 6 — Agent performance metrics.** Task 5.1's agent-framework bullet: task completion rate, tool-usage effectiveness, reasoning quality across multi-step workflows. `support-agent-loop` already emits a **self-logged trace** of every tool call it makes (built in P05 Stage 10) — the raw material exists and nothing computes anything from it. Score: did the loop reach a real answer or exhaust `MAX_TOOL_ITERATIONS`; were the tools it chose the right ones; how many iterations did it need. Check during Stage 0 whether **Bedrock Agent Evaluations** is usable here — likely not, since this account's agent is a hand-rolled Converse loop rather than a managed Bedrock Agent (P05 found Agents Classic blocked), in which case document *why* the managed option doesn't apply rather than silently hand-rolling.

- [ ] **Stage 7 — Task 5.2: troubleshooting methodology write-up.** No build, no AWS spend, high value. Content Domain 5's second task is troubleshooting GenAI applications via systematic layered analysis. This repo has accumulated an unusually good corpus of *real, documented* failures across six practices — a cross-region inference profile silently routing outside its IAM policy, a Lambda Layer broken by a Python-version-dependent transitive dependency, macOS-built wheels failing at runtime, a WebSocket path with zero guardrail coverage sitting next to a fully-covered REST path, an IAM self-escalation restriction, a newline silently failing a "regex" check, and a full fairness-finding retraction. Synthesize these into a layered troubleshooting methodology (which layer to suspect first, what each class of symptom actually indicated) rather than restating the exam bullets abstractly.

**Deliberately out of scope** (recorded as decisions, not oversights — per the "deep on real gaps" scope decision):
- *Semantic drift detection* — needs a longitudinal baseline that won't exist until Stage 4 has been collecting for a while. Correct follow-up, not buildable now.
- *Annotation workflows / human-in-the-loop labelling UI* — P06 Stage 9 delivers the rating capture; a full annotation tool is a product, not an eval capability, and would dwarf the rest of this practice.
- *Reporting dashboard for eval results* — Stage 4's table makes this cheap to add later; P05 Stage 13 already set the precedent of skipping a dashboard when the data is queryable without one.
- *A/B testing foundation models in production* — the mechanism already exists (P01's AppConfig model-swap without redeploy); running a real production A/B needs traffic this system doesn't have.

## Cost note

Unlike practices 02-05, this one has a genuinely non-zero cost centre: **Stage 1's managed evaluation job bills for the inference it runs**, and Stages 2-3's repeated-sampling design multiplies model calls by n≥5 on purpose. That's the correct tradeoff for methodological rigor, but it must be measured and reported, not hand-waved — same treatment the README's Cost sections give every other practice. Stage 4's DynamoDB table is on-demand ($0 idle); Stage 5's scheduled Lambda is pay-per-invocation.

## Verification

- Stage 1: confirm the managed evaluation job completes and its output is retrievable; report the real dollar cost and the agreement/divergence vs. `benchmark_models.py`'s ranking.
- Stages 2-3: both the n≥5 and n=1 runs must be reported together — the comparison *is* the finding. Report score distributions (min/max/stdev), never a single number.
- Stage 4: query the table back after a run and confirm results are retrievable by eval-run ID.
- Stage 5: deliberately regress something (e.g. point `generate` at `nova-micro` with a low maxTokens) and confirm the gate actually fails — an untriggered gate is not a verified gate.
- Stage 6: run several agent queries of differing complexity and confirm the computed completion/tool-use metrics match what the traces actually show.
- Write up `practice-07/README.md` and `practice-07/SETUP-LOG.md` following practice-05's structure (stage-by-stage narrative + resource table with cost/teardown columns), including any blocked-attempt stages documented as real findings.
