# Practice 07 — Evaluation & QA: can you trust the scorer?

The first practice of [Series 2](../README.md). It's AWS Bonus Assignment 01
([`practice-07.md`](./practice-07.md)): *"build a complete evaluation system for a customer support
chatbot powered by Amazon Bedrock"*. It also covers the exam's Content Domain 5, implementing
evaluation systems.

The chatbot under test is the RAG assistant from Series 1. A question goes in, passages come back
from a Bedrock Knowledge Base over six AWS docs, Nova Lite writes a cited answer, and a Bedrock
Guardrail blocks anything unsafe or ungrounded. Every evaluation in Series 1 was a one-off script
that printed a number once. This practice builds evaluation that is repeated, stored and able to
gate a release. On the way, it **tests the evaluators themselves**.

**The short version:**
- **Neither scorer could separate the models.** Bedrock's managed Q&A score and my own Practice 01
  benchmark both failed to tell Nova Micro from Nova Lite.
- **LLM judges are consistent but biased.** At temperature 0.2 a judge is nearly deterministic, and
  two judges disagreed on the same answer every single run. Running each five times just repeated
  its mistake five times.
- **Checking claim by claim catches what a single score can't.** It found an unsupported sentence
  that the guardrail's grounding score passed on every run.
- **The grounding score isn't random after all, which corrects Practice 05.** Hold the answer fixed
  and it never moves; the variation came from regenerating answers.
- **The quality gate passed a regression I created on purpose.** 7 of 10 answers were truncated
  mid-sentence, but a single-fact test set couldn't see it.
- **Four of my nine scored predictions missed,** and one more held only trivially.

**Status: complete.** Stages 0–8 are built and measured; Stage 9 is this write-up and the teardown.
Two stages were moved out when the practice was trimmed: agent metrics → Practice 11, and the
troubleshooting methodology → the Series 2 wrap-up. Resources and teardown are in
[`SETUP-LOG.md`](./SETUP-LOG.md); stage-by-stage detail is in [`PLAN.md`](./PLAN.md).

---

## How this one was run differently

Series 2 follows stricter rules than Series 1. Each one is there because Series 1 hit the problem
it prevents.

- **Predictions before data.** [`PREDICTIONS.md`](./PREDICTIONS.md) was committed in its own commit
  before the first model call, and it isn't edited afterwards. It's scored below, misses included.
- **Every model call is cached, capped and priced.** [`evalkit/`](./evalkit/) is the only path to a
  model. It saves every reply (keyed on the run number, so a five-run judge really makes five
  calls), enforces a hard call limit, and has a dry-run mode that prices a run before anything is
  sent. Prices come from the AWS Price List API.
- **Raw results are committed.** Every number below can be re-rendered from
  [`results/`](./results/) without calling AWS.
- **Offline tests:** 52 pytest tests run with AWS credentials switched off.

## Cost

**About $0.27 estimated and ~$0.17 billed so far**, against a budget of $0.50. The estimate leans
high on purpose. The billed figure is from Cost Explorer on 2026-11-25; it covers the whole account
and lags 24–48 hours, so the last day's gate runs aren't in it yet. What's still running costs $0
while idle.

| Stage | Cost |
|---|---|
| 0: probe calls | < $0.001 |
| 3: 32 live `generate` calls | ~$0.06 (estimated; the measured answer-model and grounding parts come to $0.03) |
| 4: four Bedrock evaluation jobs | < $0.02 |
| 5: 660 judge calls | $0.048 (measured from token usage) |
| 6: 89 claim-check and guardrail calls | ~$0.06 |
| 7: 335 DynamoDB writes | ~$0 |
| 8: gate baseline + 5 gate runs | ~$0.08 |

Billed, by service (account-wide): Bedrock $0.120, Bedrock Knowledge Base $0.044, S3 $0.006,
DynamoDB $0.0001, Cost Explorer queries $0.02.

The plan had budgeted Mistral Large as the second judge. The Price List API put it at $4/$12 per
million tokens, about 67× Nova Lite, so `gpt-oss-120b` ($0.15/$0.60) replaced it. Claude couldn't be
used at all: it's still blocked by the same AWS Marketplace payment error that Practices 01 and 02
hit.

## Build stages

### Stage 0 — Live audit (no new resources)

- **No code drift:** the deployed Lambdas are byte-identical to the repo.
- **Practice 06's metrics are live.** Its Stage 9 rating system was never built, so evaluating user
  feedback is out of scope.
- **Bedrock Model Evaluations is reachable,** with a quota of 1 model per automatic job.

### Stage 1 — Evaluation toolkit (offline)

[`evalkit/`](./evalkit/) handles cached and call-limited model and Lambda calls, pricing, the
golden-set loader, and statistics: summaries, Wilson intervals, raw agreement and Cohen's kappa.

Two details the tests pin down:
- **The cache key includes the run number.** Without it, "judge this five times" silently gets one
  cached reply back five times.
- **Reasoning models put their answer second.** `gpt-oss-120b` returns a reasoning block first, so
  taking `content[0]["text"]` returns None.

### Stage 2 — Predictions committed before any data

Five predictions, each with the result that would prove it wrong. They're scored
[below](#predictions-scored-so-far).

### Stage 3 — 30 live answers, collected once

[`collect_responses.py`](./collect_responses.py) ran the 10 golden questions from Practice 02, 3 times
each, through the live `generate` Lambda. Every later stage scores *these* answers, so every scorer
is compared on the same answers.

- **The right document was retrieved 30 out of 30 times.**
- **7 of 30 answers were blocked by the guardrail.** q07 and q10 were blocked on every run, q02 on
  one. q10 is probably a false block: its retrieved passage literally contains the answer ("only
  `GET` methods are cached"), yet it scored 0.43 grounding on all 3 runs. Stage 6 will check it.
- **Temperature 0 isn't deterministic.** 5 of 10 questions gave different answers across runs, from
  identical retrieved passages.
- **Blocked answers are invisible.** Bedrock replaces the answer with a refusal message and reports
  token usage of 0/0/0. So Practice 06's token metrics have been recording blocked requests as free.

**Getting the data exposed a real bug.** `generate` didn't return the retrieved passages or token
usage, so I added an opt-in `include_debug` flag on the direct-invoke path. Checking how API Gateway
reaches the function showed that **Practice 06's `tier` override had been publicly reachable all
along.**
- `/ask` is a Lambda-proxy integration with no request validator, so the whole request body is
  forwarded.
- Practice 06 claimed in a code comment that "the REST route only forwards `query`", but nobody
  had checked.
- So any caller could send `"tier": "pro"` and get Nova Pro at ~13× the cost.

Both overrides now work only on direct invocation: an API Gateway event always carries
`requestContext`, and a direct call never does. I verified this live, and corrected Practice 06's
README.

### Stage 4 — Bedrock's managed evaluation vs. my Practice 01 benchmark

[`managed_eval.py`](./managed_eval.py) runs the jobs and [`compare_managed.py`](./compare_managed.py)
compares them offline.

**Programmatic Q&A** sends the bare question to each model, with no retrieval, and scores it against
the one-line reference:

| | Nova Micro | Nova Lite |
|---|---|---|
| Bedrock managed F1 | 0.104 | 0.118 |
| Practice 01 word overlap | 0.649 | 0.658 |

- **Neither scorer separates the two models;** both gaps sit well inside the per-question spread.
  Practice 01's earlier "Micro beats Lite" ranking was never a real difference.
- **F1 sits around 0.1 even for correct answers.** The answers run ~200 words and the references are
  one line, so word overlap is low no matter what.
- **Practice 01's "similarity" turns out to be word recall,** which *rewards* long answers, while F1
  penalises them. At n=10 the length correlations were too mixed to prove that opposite bias
  cleanly.
- **Bedrock's robustness metric is unusable here.** It's a *relative* change in F1, so on a baseline
  of 0.1, tiny shifts read as 10–96%.

**LLM-as-judge on the real answers**, as a RAG evaluation job with my own responses, judged by Nova
Micro:
- **It correctly scored the two blocked answers** as refusals: correctness 0, refusal 1.
- **It silently returned no score on one cell.** On q03 the judge wrote a full explanation but no
  number, and a pipeline that averages scores would quietly drop it.
- **It caught something the guardrail passed.** q03's answer added "you must use the REST API or
  SDKs", which isn't in the source passage. Faithfulness came out 0.75, while the guardrail had
  passed the same answer at 0.89 grounding.
- **One low score was the golden set's fault, not the answer's.** q09 lost completeness because the
  reference mentions facts the question never asked for. I adjudicated it by hand as correct and
  complete.

Two near-misses along the way:
- **The 4 KB prompt quota** would have rejected the first judge dataset. Pasting the passages into
  the prompt produced 5–13 KB prompts. The `RagEvaluation` job type takes the passages as their own
  field instead.
- **The Knowledge Base's data source covers the whole docs bucket,** with no prefix filter. Practices
  03 and 04 have since written 11 customer-feedback `.docx`/`.txt` files there. Nothing has synced
  since, but the next doc change would pull customer feedback into RAG answers. That's why the
  evaluation data got its own bucket. I logged it as a dormant risk for Practice 09 rather than
  quietly changing Series 1.

### Stage 5 — The assignment's single-run judge vs. five-run rubric judges

[`judge_eval.py`](./judge_eval.py) ran two arms over the same 10 answers, 660 calls in all.

- **Arm A, the assignment's judge as written:** one combined prompt scoring six dimensions 1–10, at
  temperature 0.2. Its bugs were fixed and Nova Micro stood in for its dead model ID. It ran 6
  times: run 0 is "the single run", and runs 1–5 are the distribution it gets compared against.
- **Arm B, independent rubrics:** one anchored 1–5 rubric per dimension, with two judges, Nova
  Micro and `gpt-oss-120b`, 5 runs each.

**What it found:**
- **Judges barely vary from run to run.** Only 2–3% of cells moved by a point or more across five
  runs.
- **The two judges disagree systematically.** In 6 of 60 cells they split on *every single run*. The
  mean gap between judges (0.35) was about 4× each judge's run-to-run spread (0.08).
  **Running a judge five times doesn't fix its bias.** It just repeats it five times.
- **Adjudicating those 6 cells by hand:** `gpt-oss-120b` was right on 5. A refusal *is* fluent and
  consistent, and q09's answer is complete for the question asked. Nova Micro was right on the
  sixth, q01, where `gpt-oss-120b` called a true claim inaccurate ("reserve up to 900 units"). That
  claim is word for word in the retrieved AWS passage; the judge only saw the short reference. So
  the better judge made its one error on factual accuracy, the dimension that matters most.
- **Nova Micro's six dimensions are really one bit.** It gave every unblocked answer 5 on all six and
  every blocked answer 1 on all six, including "fluency" for a perfectly fluent refusal.
- **The assignment's verbose JSON schema broke in 2 of 60 replies.** Each was missing a closing
  brace. The assignment's code would turn those into silent error records.
- **"Quality per token" mostly measures brevity.** Quality sits at the 5/5 ceiling for every
  unblocked answer, so the ratio just ranks how short the answer is.

### Stage 6 — Claim-by-claim checks vs. the guardrail's single grounding score

[`grounding_eval.py`](./grounding_eval.py) checks each answer claim by claim. One call per answer
lists the factual claims and labels each one *supported*, *contradicted* or *not mentioned* against
the retrieved passages: 3 runs, with Nova Micro and `gpt-oss-120b`. This time the judges get the
passages, which is the gap that made `gpt-oss` mark a true fact false in Stage 5. To keep cost
down, the guardrail (~$0.001 a call) was re-run 5 times only where it mattered. Blocked answers had
their hidden draft regenerated once, with `generate`'s prompt and no guardrail, so their claims
could be checked at all.

**What it found:**
- **Claim checks name the sentence a single score can't.** Both judges flagged q03's "Instead, you
  must use the REST API or one of the AWS SDKs…" on every run, because it isn't in the passages.
  The guardrail passed the same answer at 0.89 on all 5 runs. Bedrock's RAG judge had caught the
  same sentence in Stage 4.
- **With the passages in hand, the two judges agreed.** Their only slip was Nova Micro once
  inverting a claim ("Versioning is on by default", where the answer said the opposite). That was 1
  run of 3, so it was outvoted.
- **The grounding score is deterministic, which corrects Practice 05.** With the answer text held
  fixed, every answer tested scored exactly the same on all 5 runs (q03 0.89, q06 0.96, q10 0.92,
  probe 0.79). Practice 05's "identical calls scored 0.54–0.80" had regenerated the answer each
  time. [Corrected in its README](../../series-1/practice-05/README.md).
- **A guardrail block destroys the evidence needed to judge it.** q10 was blocked live at 0.43,
  yet a regenerated draft passes at 0.92 with every claim supported. The scorer is deterministic,
  so the original must have been a different text, and nobody can now check it: Bedrock replaces
  a blocked answer, and `generate` doesn't log it. q07 and the hallucination probe show the same
  pattern. Not run, to save cost: the guardrail trace's `modelOutput` holds the original draft,
  and returning it from `include_debug` would settle all three.

### Stage 7 — Results stored in DynamoDB

[`store_results.py`](./store_results.py) loads Stages 4–6 from the committed files, with no model
calls, into an on-demand `EvaluationResults` table: **335 rows across 9 runs**, each run with its
description and cost. A score that came back empty is stored with `n=0` rather than dropped, so
"the judge silently returned nothing" stays visible in the data.

**The first load lied.** It printed "wrote 335 rows" and the table held 303. The Q&A results label
questions by *document*, two questions share each of four documents, and DynamoDB silently
overwrote the colliding rows. A duplicate-key test caught it. The loader now refuses colliding
keys, removes stale ones and checks the read-back count.

### Stage 8 — A quality gate, and the regression it missed

[`lambda/eval-quality-gate/`](./lambda/eval-quality-gate/) is a Lambda with two modes:
- **`live`** scores the deployed system.
- **`candidate`** scores a *proposed* config before it ships. It regenerates answers from the
  stored passages and runs them through the production guardrail, so blocks count as they would
  live.

It scores each answer on factual accuracy and completeness, 3 runs, compares the result with the
baseline stored in the table, writes its result back, and publishes an SNS alert on FAIL. The
baseline is the same scorer on Stage 3's 3 runs (4.13, 4.13, 3.73), so the threshold is mean 4.00 −
2 × sd = **3.54**. That tolerates one extra guardrail block and fails on more. A weekly schedule
exists but was created **disabled**: a gate that runs on a timer for nobody is spend without
purpose.

| Run | Score | Result |
|---|---|---|
| Live, deployed system | 4.10 | PASS |
| Production config as a candidate (×2) | 4.50, 4.50 | PASS |
| **Deliberate regression: Nova Micro, 40-token limit** | **4.63** | **PASS ← it should have failed** |
| Fail-path check, added afterwards: 10-token limit | 2.40 | FAIL, alert published |

**The gate passed a config I knew was worse.**
- 7 of the 10 degraded answers stop mid-sentence ("This limit can…").
- But every golden question asks for one fact with a one-line reference, and the fact lands in
  the first 40 tokens. A factual-accuracy and completeness rubric can't see truncation.
- Shorter answers also drew **zero guardrail blocks**, so the broken config outscored production.
- **A gate is only as strong as its test set.** This one can't tell a 40-token config from a
  500-token one.
- Two cheap fixes, not built: flag answers that hit the token limit (`stopReason ==
  max_tokens`), and add golden questions that need more than one fact.

The 10-token run is clearly labelled as an after-the-fact check, so the fail path, the stored rows
and the alert are verified. The alert topic deliberately has no subscriber: the publish is
confirmed (a message ID, and CloudWatch counts 1 message published), delivery isn't.

**One caveat:** candidate mode is slightly optimistic (4.50 vs. 4.10 live). It sends the prompt
as one text block, and `generate` uses two.

### Stage 9 — Wrap-up and teardown

- **Kept for Practices 08–11, all $0 while idle:** `EvaluationResults`, the gate Lambda and its
  role, the disabled schedule and the alert topic.
- **Deleted:** the evaluation-job bucket and its IAM role, after confirming every object is
  committed under `results/`.
- **Teardown check:** it included CloudWatch Logs this time. The gate's log group has 14-day
  retention.

---

## Predictions scored

From [`PREDICTIONS.md`](./PREDICTIONS.md), committed before Stage 3's first model call.

| # | Prediction | Result |
|---|---|---|
| 1 | Managed F1 won't clearly rank Micro vs. Lite, and both will score < 0.4 | ✅ **Held.** 0.104 vs. 0.118, inside the noise |
| 2 | Managed judge and my judge agree on pass/fail for ≥ 8 of 10 | ✅ **Held.** 9 of 9; one answer wasn't comparable because the managed judge returned no score |
| 3a | ≥ 20% of cells vary by ≥ 1 point across five runs | ❌ **Missed.** 2–3% |
| 3b | The single-run score falls outside its own five-run range at least once | ✅ Held, but trivially: 1 of 60 cells, by one point on fluency |
| 3c | Which judge you pick matters *less* than how many times you run it | ❌ **Missed: the opposite happened.** The gap between judges was ~4× the spread within either judge |
| 4a | Claim-level checks flag an unsupported claim in an answer the grounding score passed | ✅ **Held.** q03, flagged by both judges on every run; grounding passed it at 0.89, 5 of 5 |
| 4b | The grounding score for one answer ranges by > 0.2 across five runs | ❌ **Missed.** Range 0.00 on every answer tested. The scorer is deterministic, which corrects Practice 05 |
| 5 | The gate fails the degraded config and passes all 3 normal runs | ❌ **Half missed.** 3 of 3 normal runs passed, but the degraded config (Nova Micro, 40 tokens) passed too |
| Cost | The whole practice costs under $0.50 | ✅ **Held.** ~$0.27 estimated, ~$0.17 billed so far |

**Four misses, and they share a cause.** Each time, I expected *noise* to be the problem, because
Practice 05 had been fooled by single samples. But that noise came from the system being tested,
not from the instruments:
- the judges are consistent but biased (3a, 3c);
- the grounding scorer doesn't vary at all (4b);
- the gate is consistent but blind to what its test set can't express (5).

The risks that mattered were bias and coverage, and repetition fixes neither. Only a second judge,
a human, or a better test set does.

## Reference-code review

The assignment ships ~700 lines of reference code. These are the defects I documented rather than
copied:
- **Unfinished code:** `_calculate_efficiency_metrics` ends in a bare `return`, and `_rank_models`
  is called but never defined.
- **The document's own numbering leaked into the code:** `"Step 2: Provide only the JSON..."` sits in
  the middle of a prompt string.
- **Broken entrypoints:** `if name == "main"` instead of `if __name__ == "__main__"`.
- **A broken method:** `_extract_json_from_text` is defined at module level but called as `self.…`.
- **Dead model IDs:** `claude-3-sonnet-20240229`, `claude-instant-v1`, `claude-v2` and
  `titan-text-express-v1`.
- **Guessed token counts:** `len(text.split()) * 1.3`, when `converse()` returns the real `usage`
  figures for free.
- **Diagram promises that have no code:** User Feedback, Retrieval Evaluation, an Evaluation
  Database and a Dashboard.

## Bugs and findings

| # | Where | What |
|---|---|---|
| 1 | `generate` (P06) | The `tier` override was publicly reachable through `/ask`; any caller could choose Nova Pro. **Fixed** and verified live |
| 2 | KB data source (P02) | It covers the whole bucket, so the next sync would index 11 customer-feedback files. **Dormant; logged, not fixed** |
| 3 | `generate` metrics (P06) | Usage reads 0/0/0 on guardrail-blocked calls, so blocked requests get recorded as free |
| 4 | Bedrock evaluation | The 4 KB prompt quota rejects RAG-sized judge prompts, so I used the `RagEvaluation` job type |
| 5 | Managed judge | One cell had an explanation but no score: an empty result that looks like a normal one |
| 6 | Golden set (P02) | Some references are broader than their question, which penalises correct answers on completeness |
| 7 | Nova Lite | Temperature 0 gave different answers on 5 of 10 questions |
| 8 | Guardrail | q10 was blocked at 0.43, but a regenerated draft passes at 0.92 with every claim supported. The original can't be checked: Bedrock replaces blocked answers and `generate` doesn't log them |
| 9 | Assignment judge | The verbose JSON schema came back structurally broken in 2 of 60 replies |
| 10 | P01 benchmark | Its "similarity" is word recall, which favours long answers |
| 11 | Mine | The pilot reported "expected doc retrieved 0/3" because retrieved names carry `.md` and the golden set doesn't. Caught before the full run |
| 12 | Mine | I deployed without the rollback zip I'd assumed was saved; it was lost when the scratchpad was cleared. The previous version was in git, and it's now the documented rollback |
| 13 | P05 write-up | "The grounding score is non-deterministic" was really answer variation; the scorer is deterministic. **Corrected** in the Practice 05 README |
| 14 | Mine (loader) | The first DynamoDB load reported 335 rows and stored 303: colliding keys silently overwrote each other. Caught by a test and fixed |
| 15 | Mine (process) | A commit command piped pytest through `tail`, which hid a failing test's exit status, so it committed anyway. Caught on the next line of output and fixed before pushing |
| 16 | Golden set (P02) | Every question asks for a single fact, so no rubric over it can detect truncated answers. The gate passed a 40-token config |
| 17 | Gate | Candidate mode is slightly optimistic compared with live (one prompt block vs. two) |
