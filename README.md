# Gen AI Practice

I'm working through a set of hands-on Gen AI projects, mostly on AWS/Bedrock, as practice for
AWS exam prep and to actually build the kind of thing these exams ask about instead of just
reading theory. Each one starts from a scenario/assignment, gets built for real on my own AWS
account, and gets documented as I go — including the stuff that broke and what I had to do
about it, not just the parts that worked on the first try.

Sharing these under `#awsexamprep`.

The practices come in two series:

- **[Series 1](./series-1/)**: building things. Practices 01–06, each one an exam-prep assignment
  built for real.
- **[Series 2](./series-2/)**: checking whether the evidence holds up. Practices 07–11 measure,
  audit and stress-test what Series 1 left running: evaluation, abstention, whether
  guardrails actually fire, whether the graders can be trusted, and data readiness. It
  follows stricter rules: predictions committed first, repeated sampling, and pass/fail
  decided by evidence. The plan is in [`series-2/README.md`](./series-2/README.md).

## Series 1 — Building it

| # | Practice | Topics | Status |
|---|----------|--------|--------|
| 01 | [Resilient multi-model AI assistant on Amazon Bedrock](./series-1/practice-01/) — [build log](./series-1/practice-01/SETUP-LOG.md) | Bedrock, model benchmarking, AppConfig, Lambda, API Gateway, Step Functions, a real circuit breaker | Parts 1-3 built and tested live, Part 4 documented only, everything torn down |
| 02 | [RAG assistant over technical documentation](./series-1/practice-02/) — [build log](./series-1/practice-02/SETUP-LOG.md) · [Q&A](./series-1/practice-02/QNA.md) | Chunking strategies, embeddings, Bedrock Knowledge Bases, S3 Vectors, OpenSearch k-NN, hybrid search, reranking, MRR/NDCG, query decomposition, streaming | Stages 1-8 built and verified live, everything still running |
| 03 | [Resilient document analysis pipeline](./series-1/practice-03/) — [build log](./series-1/practice-03/SETUP-LOG.md) | Sync/async APIs, SQS + DLQ, SNS, WebSocket streaming, DynamoDB circuit breaker, X-Ray, Step Functions model routing — built on top of Practice 02's existing infrastructure rather than from scratch | Stages 1-7 built and verified live, everything still running |
| 04 | [AI-powered support ticket system](./series-1/practice-04/) — [build log](./series-1/practice-04/SETUP-LOG.md) | Lambda authorizers, Bedrock Prompt Flows, AWS Strands Agents, Bedrock Data Automation, a second Express Step Functions workflow, WebSocket chat, React + Amplify UI, a first pytest suite — built on top of Practice 02/03's infrastructure | Stages 1-16 built and verified live, everything still running |
| 05 | [Safe & responsible AI assistant](./series-1/practice-05/) — [build log](./series-1/practice-05/SETUP-LOG.md) | Bedrock Guardrails tuned against a real adversarial corpus, contextual grounding, Comprehend PII masking, a tiered moderation Step Functions workflow (built and deliberately not deployed), jsonschema output validation, a hand-rolled agent tool-use loop, LLM-as-judge fairness evaluation — built on top of Practice 02/04's infrastructure | Stages 0-12 and 14 built and verified live (Stage 13 skipped), everything still running — and unlike practices 02-04, nothing here is a standing/idle cost |
| 06 | [Cost, performance and observability optimisation](./series-1/practice-06/) — [build log](./series-1/practice-06/SETUP-LOG.md) | Complexity-tiered model selection A/B'd against the live guardrail, fixed-cardinality CloudWatch metrics, scheduled token-usage anomaly detection, real cost-per-request tracking — plus four of the assignment's own suggestions measured and rejected | Stages 0-8 built and verified live (Stage 9 deferred), everything still running — one scheduled rule left disabled |

Each practice lives in its own folder — the write-up is that folder's `README.md`, alongside its
build log, code, and anything else it produced.

## Series 2 — Is the evidence any good?

| # | Practice | The question | Status |
|---|----------|--------------|--------|
| 07 | [Evaluation & QA: can you trust the scorer?](./series-2/practice-07/) — [plan](./series-2/practice-07/PLAN.md) | Does Bedrock's managed evaluation agree with my hand-rolled one, and what does a quality gate need before it can be trusted? | Done: Stages 0–9 built and measured, ~$0.27. The results table and the quality gate are kept for 08–11 |
| 08 | Abstention is a property of the prompt | How far does the refusal rate move when only the wording that permits "I don't know" changes? | Not started |
| 09 | Guardrails that never fired | Does every Series 1 safety control actually fire, and does it fail open or closed when it breaks? | Not started |
| 10 | Is the grader trustworthy? | Do the graders behind Series 1's headline numbers agree with a human? | Not started |
| 11 | Data readiness, factorially | Across corpus × model × prompt × retriever, which one actually moves accuracy? | Not started |

The details for each practice, the series rules and the LinkedIn plan are in
[`series-2/README.md`](./series-2/README.md).

## Interview prep

[`interview-prep/`](./interview-prep/) is a standalone study track, decoupled from the practices
above — the role-agnostic question bank and AI Engineer role track from
[interview_prep](https://github.com/aishwaryanr/awesome-generative-ai-guide/tree/main/interview_prep),
plus vendor-agnostic concept references in [`topics/`](./interview-prep/topics/) (RAG, agents, fine-tuning, eval,
prompting, production, safety) pulled from the same repo's
[topics](https://github.com/aishwaryanr/awesome-generative-ai-guide/tree/main/topics) folder. Not
maintained independently of upstream — see that folder's README for source and license.

## What's in each practice writeup

Roughly: the scenario I was given, the architecture I ended up with, what I built part by
part, a review of whatever reference code the assignment came with (most of them ship with
example code that's outdated or has real bugs — pointing those out is half the point), and
a separate build log with every AWS resource I created and how to tear it down again.

## Topics touched so far

- Comparing foundation models on quality/latency/cost, not just "does it work"
- Bedrock's Converse API as a provider-agnostic way to call different models
- AppConfig for swapping which model serves traffic without redeploying anything
- Lambda + API Gateway + Step Functions tied together
- An actual stateful circuit breaker (DynamoDB-backed, not just retry+fallback)
- Cost control basics — On-Demand billing where it matters, budgets, tearing things down
- Which AWS services bill *while idle* and which don't, and designing around that
- RAG end to end: chunking strategies, embeddings, vector stores, hybrid search, reranking
- Measuring retrieval quality properly (precision/recall, MRR, NDCG) instead of eyeballing it
- Streaming model output to a browser over API Gateway WebSockets
- Decoupling slow work with SQS + a dead-letter queue, and notifying via SNS
- Request validation at the API edge (JSON Schema) so bad input never reaches a Lambda
- Tracing a request across services with X-Ray, and building CloudWatch dashboards
- Letting the system classify its own input and route accordingly, instead of trusting the caller
- What Lambda authorizers can and can't actually see (no request body) — and designing around that honestly instead of pretending otherwise
- Bedrock Prompt Flows as a real no-code branching mechanism, driven via its CLI/API schema rather than the console
- Bundling a third-party pip dependency into a Lambda for the first time (a Layer, cross-platform wheels, why building it on macOS silently breaks at runtime)
- AWS Strands Agents — and being honest about when an agent framework is actually earning its dependency weight vs. when a plain model call would do
- Bedrock Data Automation for document processing, including a cross-region inference profile that silently routes to a different region than the one in your IAM policy
- A first React + AWS Amplify UI, replacing the single-static-HTML-file convention for the one practice that specifically asked for a frontend framework
- A first pytest suite, keeping it to the pure-logic slice that's genuinely testable offline rather than introducing a CI harness this repo doesn't otherwise have
- Tuning Bedrock Guardrails against a real adversarial test corpus instead of configuring it once and assuming it works — going from 50% to 97% accuracy by root-causing every false positive
- Proving, not assuming, that safety/PII/grounding classifiers are non-deterministic near their decision thresholds — the same input can get a different verdict on repeated identical calls
- The difference between a hard content block and a soft PII redaction hiding behind the same "intervened" flag, and what breaks when code doesn't tell them apart
- Building an agent's tool-use loop by hand when the managed option (Bedrock Agents Classic, then AgentCore) turns out to be blocked for the account or not worth its adoption cost for the task's actual scope
- Running a fairness evaluation, getting a clean-looking result, and retracting it after applying proper repeated-sampling rigor — the retraction was the real finding
- SageMaker Model Cards as free, structured governance documentation, including a real AWS API quirk (a newline in JSON content silently fails a "regex" validation check)
- A/B testing model tiers against a live guardrail with the query held constant — and finding that the "cheap" model saves nothing because it parks answers just under the grounding threshold and gets blocked 8 times out of 10
- CloudWatch custom-metric cardinality as a cost design constraint, not a style preference — dimensioning by request ID mints a new billable metric per request, on the one AWS service in this account that bills for existing rather than for use
- Testing an optimisation *before* building it, and rejecting four of an assignment's own suggestions on measured evidence — including one that genuinely cut tokens by 31% while deleting the citation contract and the answer itself
- Why an in-memory rolling window can never work in a Lambda, and using CloudWatch itself as the durable history instead

— Digvijay Pundir. These are personal learning projects; AWS costs incurred are on me.
