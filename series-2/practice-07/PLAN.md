# practice-07: Evaluation & QA capstone (Bonus Assignment 01 + Content Domain 5)

The step-by-step execution plan. It's the opener of [Series 2](../README.md) and follows its rules:
- predictions are committed before the first experimental model call;
- every model call goes through a cache and a call limit;
- raw results go in `results/`;
- an offline `tests/` suite;
- the LinkedIn draft is written last.

Work stage by stage, and check each stage off before starting the next.

**Budget: under $0.50 for the whole practice, and $0 idle afterwards.** Every stage lists its
own estimate, and the write-up reports the measured cost next to it.

Paths into Series 1: `../../series-1/practice-NN/` from here. For example,
`sys.path.insert(0, "../../series-1/practice-02")` reuses `test_questions.py`.

## What this practice is for

Bonus Assignment 01 (`practice-07.md`) asks for "a complete evaluation system for a customer
support chatbot", plus the **Content Domain 5** exam tasks: 5.1 implement evaluation systems,
and 5.2 troubleshoot GenAI applications.

Series 1 already has plenty of evaluation code, but every piece is a one-off local script
writing a local JSON file. Nothing is repeated, stored, or used to gate anything. That gap is
what this practice fills.

**The headline going in:** the assignment's Module 1 is single-pass LLM-as-judge scoring. P05
already showed that method producing a convincing, reproducible-looking and *false* result: the
fairness retraction. So this practice runs the assignment's n=1 judge next to an n=5 one and
reports how far apart they land.

## Already covered in Series 1 (reuse, don't rebuild)

- **Golden set:** `series-1/practice-02/test_questions.py`. It has 10 questions, each with
  `expected_doc` and `ground_truth`, hand-verified against the corpus.
- **Multi-model benchmark (Module 2):** `series-1/practice-01/benchmark_models.py`. Its
  word-overlap similarity is the hand-rolled score that Stage 4 compares against the managed
  service.
- **Retrieval quality:** `series-1/practice-02/retrieval_quality.py` computes hit-rate@k, MRR
  and NDCG across four strategies. That's more than the assignment asks for, so it is not
  rebuilt.
- **Tiered generation:** P06's `tier` override on `generate`'s direct-invoke path. Stage 8
  uses it to cause a regression deliberately, without changing any deployed code.

## Defects in the assignment's reference code (document these, don't reproduce them)

- **Truncated or non-functional code:** `_calculate_efficiency_metrics` ends in a bare
  `return` (line 685), and `_rank_models` is called (line 578) but never defined.
- **Document structure leaked into code:** `"Step 2: Provide only the JSON response..."` sits in
  the middle of a prompt literal (line 212).
- **Broken entrypoints:** `if name == "main"` (lines 302 and 465).
- **Broken method binding:** `_extract_json_from_text` is defined at module level (lines 215
  and 412) but called as `self._extract_json_from_text`.
- **Dead model IDs:** `claude-3-sonnet-20240229`, `claude-instant-v1`, `claude-v2` and
  `titan-text-express-v1`.
- **Rough token counts:** `len(text.split()) * 1.3`, when `converse()` returns the real
  `usage` figures for free.
- **Diagram promises that have no code:** the architecture diagram promises User Feedback,
  Retrieval Evaluation, an Evaluation Database and a Dashboard. Only Modules 1 and 2 have code.

---

## Stages

### - [x] Stage 0: Live audit and availability checks ($0, done 2026-11-14)

All of this is read-only, except for a handful of one-word "Reply with OK" probe calls costing
under $0.001 in total.

- **No drift:** the deployed `generate`, `record-metrics`, `analyze`, `support-agent-loop` and
  `token-anomaly-check` are byte-identical to local source.
- **P06 landed:** `RagAssistant/Ops` has datapoints from 2026-08-18 (nova-lite 5, nova-pro 2).
  `RoutingMetrics` has 8 rows, 2 of them with `estimated_cost_usd`. That's expected, because
  the field is written only when the cost is known. Note that `list-metrics` shows nothing,
  because it only covers the last 14 days. Query the statistics directly instead.
- **P06 Stage 9 was never built.** `SupportTickets` (46 rows) has no rating attribute, so
  user-feedback evaluation is **out of scope**.
- **Bedrock Model Evaluations:**
  - The API works in us-east-1 (`list-evaluation-jobs` returns 0 jobs).
  - Quotas: 1000 prompts per dataset, **1 model per automatic job** (so comparing models takes
    one job per model), 3 metrics per dataset, and 20 concurrent jobs.
  - Cost: automatic algorithmic scores are free, and you pay only for generator inference.
    LLM-as-judge jobs pay the judge's on-demand tokens, and nothing more per job or per metric.
  - Bring-your-own responses is supported, so Bedrock can judge `generate`'s real answers
    without calling the model again.
  - **Not proven yet:** that `create-evaluation-job` is actually allowed for this account.
    Stage 4a tests that first.
- **Models:**

  | Model | Status |
  |---|---|
  | Nova Micro, Nova Lite, Nova Pro | OK |
  | Nova 2 Lite | OK, but only through the `us.` inference profile |
  | Mistral Large | OK |
  | `gpt-oss-120b` | OK |
  | Claude Haiku 4.5 | **Blocked:** `INVALID_PAYMENT_INSTRUMENT`, the same Marketplace problem P01 and P02 hit |
  | Llama 3.1 70B | Blocked (legacy) |
  | Nova Premier | End of life |

  - Nova Lite v1 is **not** a supported Bedrock judge; Nova Micro, Nova 2 Lite and Nova Pro are.
  - **Second judge family for this series: `gpt-oss-120b` (OpenAI).** Mistral Large works too,
    and is a supported Bedrock judge. But the Price List API puts it at $4/$12 per 1M tokens,
    about 67× Nova Lite, against $0.15/$0.60 for `gpt-oss-120b`. Claude is out unless the
    Marketplace payment problem gets fixed.
- **AgentCore Evaluations exists** (`bedrock-agentcore-control list-evaluators` returns 32).
  Agent metrics moved to Practice 11 when this practice was trimmed (see below), so whether it
  can score a plain Lambda Converse loop gets checked there.

### - [x] Stage 1: Evaluation toolkit (offline, $0, done 2026-11-14)

Shared code for this practice and the rest of Series 2. No AWS calls.

**Done:** 25 tests pass with AWS credentials disabled (`.venv/bin/python -m pytest tests`).
Two details the tests pin down:

- The cache key includes a `trial` index. Without it, a five-run judge would get one cached
  reply back five times and silently become a one-run judge.
- Replies from `gpt-oss-120b` start with a reasoning block. Taking `content[0]["text"]` returns
  None, so the toolkit joins all the text blocks instead.

- `evalkit/bedrock.py` is the only way any script calls a model. It provides:
  - a cache keyed on `hash(model, prompt, params, trial)` in `results/cache/`;
  - real `usage` capture;
  - cost from prices read from the AWS Price List API on 2026-11-14 (`evalkit/pricing.py`).
    Any model without a price entry is flagged, never counted as free;
  - `--dry-run`, which counts and prices the calls without making them;
  - `--max-calls`, a hard stop;
  - the region pinned to `us-east-1`.
- `evalkit/golden.py` loads P02's `test_questions.py`.
- `evalkit/stats.py` computes mean, stdev, min and max, Wilson intervals, and agreement between
  two scorers.
- `tests/` checks the cache key, the cost maths, the stats and the call limit with pytest, all
  offline.
- **Done when:** `pytest` passes with no credentials.

### - [ ] Stage 2: Predictions (commit on its own, $0)

Write `PREDICTIONS.md` and commit it **before** Stage 3's first model call. For each question:
what I expect, and what result would prove me wrong. The questions to commit to:

1. Do Bedrock's managed Q&A scores (F1) rank Nova Micro and Nova Lite the same way P01's
   word-overlap proxy did?
2. Does the managed judge's *Correctness* score agree with my own judge on which answers are
   wrong?
3. How far apart are the n=1 and n=5 judge scores, and does any conclusion flip?
4. Does splitting answers into individual claims catch a hallucination that the managed
   grounding score passes?
5. Will the quality gate fail on the deliberately degraded configuration (Nova Micro, low
   `maxTokens`), and pass on the normal one?

### - [x] Stage 3: Collect responses once (~$0.06, done 2026-11-18)

Call the live `generate` Lambda (direct invoke) on the 10 golden questions × 3 runs = 30 calls.
Store each answer with its retrieved context, model, `usage` and latency in
`results/responses.jsonl`. **Every later stage reads these files** rather than generating new
answers. Script: `collect_responses.py`.

**What it took:**
- `generate` didn't return chunk text or usage. An opt-in `include_debug` flag was added and
  redeployed (SETUP-LOG row 1).
- The estimate was revised from $0.01 to $0.057. Each call runs the whole pipeline (two guardrail
  passes, the router and retrieval), not just the answer model.

**Findings:**
- **The `tier` override was publicly reachable.** `/ask` is an `AWS_PROXY` integration with no
  request validator, so the full body reaches `generate`. P06's "direct-invoke only" claim was
  never true, and any caller could pick Nova Pro. Fixed: overrides are now honoured only on
  direct invoke. Verified live, and corrected in P06's README. This is a lead for Practice 09.
- **Retrieval is solid:** the expected document was retrieved 30/30.
- **7 of 30 answers were blocked.**
  - q07 was blocked 3/3, at grounding 0.27–0.42.
  - q10 was blocked 3/3 at 0.43, **although its retrieved passage literally contains the
    answer** ("only `GET` methods are cached"). That is likely a false block; Stage 6 checks
    it.
  - q02 was blocked 1 time in 3, at 0.70; its other runs scored 0.91 and 0.93.
- **Temperature 0 isn't deterministic.** 5 of 10 questions gave different answers across runs,
  with identical retrieved chunks every time.
- **Blocked answers are invisible.** Bedrock substitutes the refusal message, so the model's
  actual text can't be scored, and usage reports 0/0/0 on all 7 blocked calls. P06's
  `RagAssistant/Ops` token metrics therefore record blocked requests as 0 tokens. Later stages
  score what the user actually saw, with a block counted as a failed answer.

### - [x] Stage 4: Managed Bedrock evaluation vs. P01's hand-rolled benchmark (< $0.02, done 2026-11-18)

Scripts: `managed_eval.py` (build, submit, status, fetch) and `compare_managed.py` (offline).
Outputs are in `results/managed-eval/`.

**4a.** The bucket and role were created (SETUP-LOG rows 2–3). The test job **completed in ~10
minutes**, so evaluation jobs are *not* blocked for this account. Each real job also took ~15
minutes, even for 10 items.

**4b: programmatic Q&A, bare model, no retrieval, same 10 questions:**

| | Nova Micro | Nova Lite |
|---|---|---|
| Managed F1 | mean **0.104**, sd 0.063 | mean **0.118**, sd 0.068 |
| P01 word overlap | mean 0.649, sd 0.208 | mean 0.658, sd 0.181 |
| Answer length | 228 words | 204 words |
| Robustness | 28.4, range 13.5–96.4 | 19.5, range 10.6–34.0 |
| Toxicity | ~0.001 | ~0.001 |

- **Neither scorer separates the two models.** Lite leads by 0.014 on F1 and by 0.009 on
  overlap, both well inside the per-item spread. On its own finance questions, P01 had ranked
  Micro first (0.687 vs. 0.654). That ranking was never a real difference; both directions sit
  inside the noise.
- **F1 is low because the references are one line and the answers are ~200 words,** so even a
  correct answer scores ~0.1–0.2. The test item scored 0.14 on a correct answer. The
  length-bias hypothesis was only partly supported: the length–score rank correlations were
  mixed (F1 −0.25 for Micro, +0.45 for Lite), so at n=10 the clean opposite-bias story didn't
  show up. What did show is that every answer is long, so F1 is floored for all of them.
- **Robustness is unusable here.** It's a relative change in F1 under perturbed prompts. On a
  baseline F1 of ~0.1, tiny absolute changes become 10–96% swings.
- **The bare-model job doesn't measure the RAG system.** It sends the question with no
  retrieval, so it scores what Nova knows, not what the assistant answers.

**4c: managed RAG judge (Nova Micro) on `generate`'s real answers, trial 0:**
- Correctness mean 0.78 (9 of 10 scored), Completeness 0.72, Faithfulness 0.78, Refusal 0.20.
- **The two blocked answers (q07, q10) score 0 on correctness and 1 on refusal,** so the judge
  correctly sees the refusal the user got. Every unblocked answer scores 1.0 on correctness.
- **A silent empty score.** On q03, the judge wrote a full Correctness explanation but returned
  no score. That's 1 of 40 managed judgments, and a pipeline averaging the scores would quietly
  drop it.
- **Faithfulness caught something the guardrail passed.** q03 got faithfulness 0.75 for adding
  "you must use the REST API or SDKs", which isn't in the retrieved passage. The guardrail's
  grounding score passed the same answer at 0.89. This is early evidence for prediction 4;
  Stage 6 tests it properly.
- **One low score is a golden-set artifact.** q09 got completeness 0.25 because the reference
  also lists the maximum TTL and the TTL=0 behaviour, which the question never asked about.
  Adjudicated by hand: the answer is correct and complete for the question asked. The
  reference is broader than the question, so a reference-based completeness score penalises a
  right answer.

**Prediction 1 is scored in README (Stage 9).** The data supports it: F1 < 0.4 for both models,
and the gap is inside the noise.

**Findings before any results:**
- **The KB data source is scoped to the whole docs bucket.** It has no `inclusionPrefixes`.
  The last ingestion (2026-07-29) saw only the 6 docs, but P03 and P04 have since written 11
  customer-feedback `.docx`/`.txt` files to `feedback-raw/`. Both are formats the KB indexes.
  `check-and-sync` only starts a sync when `raw-docs/` changes, but the sync then scans
  everything. So the next doc change would pull customer feedback into RAG answers. That's
  dormant, not live. **Not fixed here**, because it's a Series 1 change; the fix is
  `inclusionPrefixes: ["raw-docs/"]` on the data source. It's a lead for Practice 09, and it's
  why evaluation data got its own bucket.
- **The prompt quota (4 KB) would have rejected the first judge dataset.** Pasting the
  retrieved chunks into the prompt made 5–13 KB prompts. The fix was a different job type:
  `RagEvaluation` with bring-your-own responses, which takes passages as their own field.
  Its dataset format was confirmed from the user guide's Markdown page, since the HTML pages
  wouldn't render.
- **P01's "similarity" is word recall,** the share of reference words found anywhere in the
  answer. So it rewards long answers, while managed F1 penalises them. The two scorers have
  opposite length biases, so `compare_managed.py` reports answer length next to both.

- **4a, setup and a test job:**
  - Create the IAM role `rag-assistant-eval-role`: trusted by `bedrock.amazonaws.com`, scoped
    to the evaluation job ARN, with S3 read/write on the `eval/` prefix only and
    `InvokeModel` on Nova only.
  - Store the data under the `eval/` prefix in the existing `rag-assistant-docs-dig-003`
    bucket.
  - Then run a **one-prompt test job**. If it's refused at account level, Stage 4 becomes a
    documented blocked attempt, as with P05's Agents Classic, and the rest of this stage is
    skipped.
- **4b, programmatic Q&A jobs:** a 10-prompt custom dataset (`prompt`, and `referenceResponse`
  set to `ground_truth`). One job for Nova Micro, one for Nova Lite. Metrics: accuracy (F1),
  robustness and toxicity. There's no judge, so you pay only for 20 generator calls.
- **4c, LLM-as-judge job on Stage 3's answers (bring your own responses):** Nova Micro judges
  Correctness, Completeness and Faithfulness, the most the 3-metrics-per-dataset limit allows.
- **4d, compare:** managed F1 against P01's word-overlap ranking, and the managed judge against
  Stage 5's own judge. Where they disagree, read the answer and decide by hand which scorer was
  right.

### - [x] Stage 5: Six-dimension judge, n=5 vs. the assignment's n=1 (~$0.05, done 2026-11-20)

Script: `judge_eval.py`. Results are in `results/judge-eval.json` and
`results/judge-eval-report.txt`. 660 calls: arm A (the assignment's combined 1–10 prompt,
Nova Micro, 6 runs) and arm B (independent 1–5 rubrics, Nova Micro + `gpt-oss-120b`, 5 runs
each). Both at temperature 0.2. Pilot: 66 calls for $0.0072. The dry-run upper bound was $0.21;
the actual cost was ~$0.05.

**Results:**

| | Predicted | Measured |
|---|---|---|
| 3a: cells whose 5 runs spread ≥ 1 point | ≥ 20% | **3%** (Nova Micro, 2/60), **2%** (`gpt-oss`, 1/60). **Missed.** |
| 3b: single run outside its own 5-run range | ≥ 1 cell | **1/60** (q04 fluency, 9 vs. five 8s). Held, but only trivially. |
| 3c: between-judge gap no bigger than within-judge spread | gap ≤ spread | Mean gap **0.35** vs. mean spread **0.08**. In 6/60 cells the judges disagree *every single run*. **Missed: the opposite happened.** |
| 2: managed Correctness vs. my factual accuracy, pass/fail | ≥ 8/10 agree | **9/9** agree (q03 not comparable: the managed judge returned no score). Held. |

**What it means:**
- **At temperature 0.2, judges barely vary from run to run, but they disagree with each other
  systematically.** Repetition can't fix a bias: five runs of a consistently wrong judge are
  consistently wrong. P05's lesson was about variance in the system under test. The judge's own
  risk here is *bias*, which only a second judge, or a human, exposes.
- **Adjudicating the 6 disagreeing cells by hand:**
  - `gpt-oss` was right on 5: a refusal *is* fluent and consistent (q07, q10 × 2); and q09's
    answer is complete for the question asked.
  - Nova Micro was right on 1: q01, where `gpt-oss` scored a true claim ("reserve up to 900
    units") as inaccurate. The claim is word for word in the retrieved passage; `gpt-oss` only
    saw the one-line reference.
  - So the better judge overall made its one error on factual accuracy, the dimension that
    matters most.
- **Nova Micro shows a complete halo effect.** Every unblocked answer got 5 on all six
  dimensions and every blocked answer got 1 on all six, including the fluency of a fluent
  refusal. Its six-dimension scores carry one bit: blocked or not. It also ignored the rubric's
  "against the question, not the reference" instruction on q09.
- **The assignment's verbose JSON schema broke in 2 of 60 replies** (12 of 360 scores). Each
  was missing a closing brace. The assignment's code would turn those into silent error
  records.
- **Quality-per-token mostly measures brevity.** Quality sits at the 5/5 ceiling for every
  unblocked answer, so the ratio just ranks how short the answer is: 30 tokens beats 204. It's
  undefined for blocked answers, which report 0 tokens.

- **Dimensions** (from the assignment): relevance, factual accuracy, consistency, fluency,
  helpfulness, completeness.
- **One independent rubric per dimension.** The judge returns a 1–5 integer and a one-line
  reason, as short JSON with `maxTokens` capped.
- **Runs:**
  - 10 answers × 6 dimensions × 5 runs with Nova Micro = 300 calls.
  - The same 10 answers × 6 dimensions × 1 run, which reproduces the assignment's method.
  - `gpt-oss-120b` on the same 10 × 6 × 5, as the second judge family. It's cheap enough to
    run in full, which allows the comparison that matters: is the gap *between* the two
    judges bigger than either judge's own spread from run to run?
- **Report distributions, never single numbers.** The finding is how often the n=1 score falls
  outside the n=5 range, and whether any ranking flips.
- **Efficiency metrics** (Module 2): `quality_per_token` and `quality_per_second`, from real
  `usage` and latency.

### - [x] Stage 6: Claim-level hallucination checks vs. managed grounding (~$0.06, done 2026-11-25)

Script: `grounding_eval.py`. Results are in `results/grounding-eval.json` and
`results/grounding-eval-report.txt`. Kept cheap on purpose: claim checks first, with 11 answers ×
3 runs × 2 judges, given the retrieved passages (the gap Stage 5 exposed). The guardrail
(`ApplyGuardrail`, ~$0.001 a call) ran 5 times only on flagged answers, q10, P05's probe and one
control. 89 calls for $0.057, plus one `generate` call for the probe.

**Results:**
- **Prediction 4a held.** q03 was flagged by *both* judges on every run for "Instead, you must use
  the REST API or one of the AWS SDKs…", which isn't in the retrieved passages. The guardrail
  passed the same answer at **0.89 on all 5 runs**. This is the same catch the managed RAG judge
  made in Stage 4 (faithfulness 0.75). A single grounding number can't say *which* sentence is
  unsupported; the claim check can. The probe was also flagged, but its flagged claim is "refer to
  the official documentation", which is advice, not a factual hallucination. So the probe doesn't
  count towards 4a.
- **Prediction 4b missed, and it corrects P05.** With the answer text held fixed, the grounding
  score was **identical across all 5 runs** for every answer tested (q03 0.89, q06 0.96, q10 0.92,
  probe 0.79; range 0.00). P05's "5 identical calls scored 0.54–0.80" regenerated the answer on
  every call, and Stage 3 showed Nova Lite's answers vary even at temperature 0. **The scorer is
  deterministic; the variation came from the generated answer.** P05's README attributes it to the
  score itself; a visible correction belongs there. Caveats: 4 answers, guardrail v5 vs. P05's v1.
- **The q10 false block is still unresolved, and why is itself a finding.**
  - q10 was blocked 3/3 in Stage 3 at grounding 0.43.
  - A draft regenerated today with the same passages and question passes at **0.92, 5/5**, and
    every claim in it is supported. Since the scorer is deterministic, the original hidden draft
    must have been a *different text* that scored 0.43.
  - The regeneration put the passages and instruction in one text block, where `generate` uses
    two `guardContent` blocks. That difference alone could change Nova Lite's wording.
  - The original draft can't be recovered: Bedrock replaces a blocked answer, and `generate`
    doesn't log it. **A guardrail block destroys the evidence needed to judge whether it was
    right.** The same pattern shows up on the probe: blocked live, but its regenerated draft
    (which correctly says the passages don't cover the figure) passes at 0.79.
  - q07 was blocked at 0.27–0.42 live, and its regenerated draft has 12–15 claims, all supported.
- **The judges agreed this time.** With the passages in hand, Nova Micro and `gpt-oss` agreed on
  every flag. The only slip was Nova Micro once inverting a q04 claim ("Versioning is turned on by
  default", where the answer said the opposite). It didn't reach a majority, so it wasn't flagged.

**Open follow-up (not run, pending approval):** `generate`'s `include_debug` could also return
the guardrail trace's `modelOutput`, the model's original text before the block. That means one
redeploy and 3 `generate` calls (~$0.006), and it would settle q07, q10 and the probe on the real
drafts.

- **Claim checks:** split each answer into individual claims, then label each one *supported*,
  *contradicted* or *not mentioned* against the retrieved context. Run this 3 times, and
  compute an accuracy and hallucination rate.
- **Managed baseline:** Bedrock contextual grounding (`ApplyGuardrail`, about $0.002 per call)
  on the same answers, 5 times each, since P05 measured this score swinging between 0.30 and
  0.72 on identical input.
- **Include P05's question that is known to produce hallucinations**, from `grounding_test.py`.
- **The question:** does checking claims one by one catch anything the single managed score
  misses, and is it worth the extra calls?

### - [x] Stage 7: Store results ($0 idle, done 2026-11-25)

**Done.** `store_results.py` loads the committed results from Stages 4–6 into `EvaluationResults`
(on-demand, SETUP-LOG row 5), with no model calls: **335 rows across 9 runs**. Each run has a
`#run` record (description, source file, recorded cost). Each item and metric row carries score
(the mean over n), n, stdev, min, max, scorer and model. Reading a run back with `--show <run_id>`
returns every row.

Missing scores are kept, not dropped: q03's empty managed Correctness is stored with `n=0`, so the
"silent empty score" finding stays visible in the data. Writes are idempotent, so rerunning
overwrites the same keys. 4 offline tests cover keys, the missing-score row and type conversion.

**Bug caught by the duplicate-key test:** the first load printed "wrote 335 rows", but the table
held **303**. The Stage 4 Q&A output labels each question by its *document*, two questions share
each of four documents, and DynamoDB silently overwrote the 32 colliding rows. Rows are now keyed
by the golden `item_id`. The loader refuses to write if any keys collide, prunes keys its files
no longer produce (48 stale rows removed), and reads the count back, failing on a mismatch. The
final read-back is 335 rows, matching. (My commit command also let the failing test through,
because a pipe hid pytest's exit status. It was caught on the next line of output and fixed
before pushing.)

- Create a DynamoDB table `EvaluationResults` with on-demand billing:
  - partition key `run_id`;
  - sort key `item_id#metric`;
  - attributes for score, scorer, model, n, stdev and cost.
- A loader writes Stages 4–6 into the table.
- **Check:** query a run back by `run_id`.

### - [x] Stage 8: Quality gate with a deliberate regression (~$0.08, done 2026-11-25)

Built as `lambda/eval-quality-gate/` (SETUP-LOG rows 6–9), with the baseline from
`gate_baseline.py`.

**A change from the plan:** P06 removed the Nova Micro tier from `generate`, so the planned
`tier` override couldn't produce the regression. Rather than redeploy `generate`, the gate has two
modes:
- `live` invokes the deployed system.
- `candidate` scores a *proposed* config before it ships. It regenerates answers from the stored
  passages, then runs the production guardrail via `ApplyGuardrail`, so a block counts as it
  would live.

**Scorer:** Nova Micro, factual accuracy and completeness, 3 runs. These are the same rubrics as
Stage 5, imported from the Lambda's own file into the baseline script, so they can't drift apart.

**Threshold, from data:** the gate scorer on Stage 3's 3 runs gave 4.13, 4.13 and 3.73 (q02's
one-off block). Mean 4.00 − 2 × sd 0.23 = **3.54**. That's wider than the floor of one item
flipping (0.4), so the floor didn't apply.

| Run | Config | Score | Blocked | Decision |
|---|---|---|---|---|
| Normal 1 | live, deployed `generate` | 4.10 | 2/10 | PASS |
| Normal 2 | candidate, Nova Lite, 500 tokens (production) | 4.50 | 1/10 | PASS |
| Normal 3 | same again | 4.50 | 1/10 | PASS |
| **Deliberate regression** | candidate, **Nova Micro, 40 tokens** | **4.63** | **0/10** | **PASS** ← prediction 5 missed |
| Fail-path check (post hoc) | candidate, Nova Micro, 10 tokens | 2.40 | 2/10 | FAIL, SNS published (message ID returned) |

**Prediction 5 missed. The gate passed a config I knew was worse.**
- 7 of the 10 degraded answers stop mid-sentence ("This limit can…", "This option offers…").
- But each golden question asks for one fact with a one-line reference, and the fact lands in
  the first 40 tokens. So a factual-accuracy plus completeness rubric can't see truncation.
- The degraded config also scored *above* production, because it had zero blocks. Short answers
  leave the guardrail less to call ungrounded, including q07 and q10, which production blocks
  every time.
- **A gate is only as strong as its test set and rubric.** This golden set can't tell a 40-token
  config from a 500-token one.
- Cheap fixes, not built: a deterministic `stopReason == max_tokens` check in candidate mode, and
  golden questions whose answers need more than one fact.

**The fail path is verified separately, and labelled as post hoc.** At 10 tokens the answers cut
off before the fact: 2.40 → FAIL, rows written, and the SNS publish was accepted. Delivery wasn't
tested: by choice, the topic has no subscriber. It's a demo, and it stays implemented-only.

**Caveat:** candidate mode is slightly optimistic compared with live (4.50 vs. 4.10, 1 block vs.
2). It sends the prompt as one text block, where `generate` uses two `guardContent` blocks, and
Stage 6 saw that difference change Nova Lite's drafts.

- **The gate:** a Lambda `eval-quality-gate` that:
  1. runs the golden set through `generate`;
  2. scores the answers with Stage 5's judge, n=3;
  3. compares them with the stored baseline;
  4. writes a PASS or FAIL row to `EvaluationResults`;
  5. on FAIL, publishes to the existing SNS topic.

  No new CloudWatch custom metric, because custom metrics bill for existing.
- **Threshold:** set from Stage 5's measured variance (the baseline mean minus k × stdev), not
  from a round number. Document the reason.
- **Schedule:** create the EventBridge rule **disabled** and run the gate by hand. A gate that
  runs on a timer for no one is spend without purpose.
- **Verify:**
  - a normal run must PASS;
  - a run using the `tier` override with Nova Micro and a low `maxTokens` must FAIL;
  - an SNS message must actually arrive.

  A gate that has never been triggered hasn't been verified.

### Trimmed out (2026-11-18)

The practice was trimmed to keep it to one story: evaluating the evaluators, then gating on
the result. Two stages moved, and none were dropped:

- **Agent metrics** (was Stage 9) → **Practice 11.** Practice 11 rebuilds the agent's tool
  layer and measures it anyway. Scoring completion, tool choice and iterations from
  `support-agent-loop`'s trace belongs there, along with the AgentCore Evaluations check.
- **Troubleshooting methodology** (was Stage 10, exam Task 5.2) → **the Series 2 wrap-up.** It
  turns real failures into a method, and Series 2 keeps producing them. This practice alone has
  added a publicly reachable override, a Knowledge Base scoped to the whole bucket, and a 4 KB
  quota that would have rejected the first dataset. So it's stronger written once, at the end.

### - [ ] Stage 9: Write-up, teardown, LinkedIn ($0)

- **`README.md`:** the stage-by-stage write-up. Score each prediction as it landed, and keep any
  corrections visible.
- **Offline report:** `make report` (or `python report.py`) re-renders every number from
  `results/` with no AWS calls.
- **`SETUP-LOG.md`:** every resource created (eval role, `eval/` prefix, table, gate Lambda,
  disabled rule), with its idle cost and teardown command. Then decide whether to keep or
  delete each one. The teardown check includes CloudWatch Logs.
- **`linkedin-post-draft.md`:** written last, opening with whichever prediction missed.

---

## Out of scope (decisions, not oversights)

- **User feedback evaluation:** P06 Stage 9 was never built, so there's no rating data.
- **Detecting semantic drift over time:** this needs a long baseline history. Stage 7's table
  is the start of one.
- **An annotation or labelling UI:** that's a product, not an evaluation capability.
- **A results dashboard:** the table can be queried directly, following P05 Stage 13's
  precedent.
- **Production A/B tests:** the mechanism exists (P01's AppConfig), but the system has no real
  traffic.
- **Claude as a judge:** blocked by the Marketplace payment problem. `gpt-oss-120b` is the
  second judge family instead.

## Cost summary (estimates, before running)

| Stage | Calls (approx.) | Est. |
|---|---|---|
| 3 | 30 `generate` calls | ~$0.06 (measured estimate; was $0.01) |
| 4 | 1 test job + 20 generator calls + 30 judge calls | ~$0.05 |
| 5 | ~360 Nova Micro + 300 `gpt-oss-120b` calls | ~$0.10 |
| 6 | ~90 claim calls + 50 `ApplyGuardrail` | ~$0.10 |
| 8 | 2–3 gate runs | ~$0.02 |
| **Total** | | **≈ $0.33** |

Everything created is $0 when idle: the IAM role, an S3 prefix, an on-demand table, a Lambda and
a disabled rule. Prices come from the AWS Price List API, read 2026-11-14.
