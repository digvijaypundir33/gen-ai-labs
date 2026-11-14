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
  Whether it can score a plain Lambda Converse loop is checked in Stage 9, from the docs only.

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

### - [ ] Stage 3: Collect responses once (~$0.01)

Call the live `generate` Lambda (direct invoke) on the 10 golden questions × 3 runs = 30 calls.
Store each answer with its retrieved context, model, `usage` and latency in
`results/responses.jsonl`. **Every later stage reads these files** rather than generating new
answers.

### - [ ] Stage 4: Managed Bedrock evaluation vs. P01's hand-rolled benchmark (~$0.05)

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

### - [ ] Stage 5: Six-dimension judge, n=5 vs. the assignment's n=1 (~$0.10)

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

### - [ ] Stage 6: Claim-level hallucination checks vs. managed grounding (~$0.10)

- **Claim checks:** split each answer into individual claims, then label each one *supported*,
  *contradicted* or *not mentioned* against the retrieved context. Run this 3 times, and
  compute an accuracy and hallucination rate.
- **Managed baseline:** Bedrock contextual grounding (`ApplyGuardrail`, about $0.002 per call)
  on the same answers, 5 times each, since P05 measured this score swinging between 0.30 and
  0.72 on identical input.
- **Include P05's question that is known to produce hallucinations**, from `grounding_test.py`.
- **The question:** does checking claims one by one catch anything the single managed score
  misses, and is it worth the extra calls?

### - [ ] Stage 7: Store results ($0 idle)

- Create a DynamoDB table `EvaluationResults` with on-demand billing:
  - partition key `run_id`;
  - sort key `item_id#metric`;
  - attributes for score, scorer, model, n, stdev and cost.
- A loader writes Stages 4–6 into the table.
- **Check:** query a run back by `run_id`.

### - [ ] Stage 8: Quality gate with a deliberate regression (~$0.02)

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

### - [ ] Stage 9: Agent metrics from `support-agent-loop` traces (~$0.02)

- **Queries:** about 6 queries of differing complexity × 2 runs. Before running, hand-label
  the expected tools for each query, held back from the agent.
- **Measure from the agent's own trace:**
  - did it finish with an answer, or run out of `MAX_TOOL_ITERATIONS`;
  - did the tools it used match the expected ones;
  - how many iterations it took.
- **AgentCore Evaluations:** check from the docs only whether it could score this Lambda loop,
  which isn't running on AgentCore Runtime or instrumented with OpenTelemetry. Document why it
  applies or doesn't; build nothing.

### - [ ] Stage 10: Troubleshooting methodology (Task 5.2, $0)

A write-up that turns Series 1's *real* failures into a layered troubleshooting method: which
layer to suspect first, and what each kind of symptom turned out to mean. The failures:
- the inference profile routing outside its IAM policy;
- the Lambda Layer broken by a dependency;
- wheels built on macOS failing at runtime;
- the WebSocket path with no guardrail;
- the IAM self-escalation restriction;
- the newline failing a "regex" check;
- the fairness retraction;
- the teardown that missed log groups.

### - [ ] Stage 11: Write-up, teardown, LinkedIn ($0)

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
| 3 | 30 `generate` calls | ~$0.01 |
| 4 | 1 test job + 20 generator calls + 30 judge calls | ~$0.05 |
| 5 | ~360 Nova Micro + 300 `gpt-oss-120b` calls | ~$0.10 |
| 6 | ~90 claim calls + 50 `ApplyGuardrail` | ~$0.10 |
| 8 | 2–3 gate runs | ~$0.02 |
| 9 | ~12 agent runs | ~$0.02 |
| **Total** | | **≈ $0.30** |

Everything created is $0 when idle: the IAM role, an S3 prefix, an on-demand table, a Lambda and
a disabled rule. Prices come from the AWS Price List API, read 2026-11-14.
