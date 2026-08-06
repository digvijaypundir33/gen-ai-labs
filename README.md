# Gen AI Practice

I'm working through a set of hands-on Gen AI projects, mostly on AWS/Bedrock, as practice for
AWS exam prep and to actually build the kind of thing these exams ask about instead of just
reading theory. Each one starts from a scenario/assignment, gets built for real on my own AWS
account, and gets documented as I go — including the stuff that broke and what I had to do
about it, not just the parts that worked on the first try.

Sharing these under `#awsexamprep`.

## Practices

| # | Practice | Topics | Status |
|---|----------|--------|--------|
| 01 | [Resilient multi-model AI assistant on Amazon Bedrock](./practice-01/) — [build log](./practice-01/SETUP-LOG.md) | Bedrock, model benchmarking, AppConfig, Lambda, API Gateway, Step Functions, a real circuit breaker | Parts 1-3 built and tested live, Part 4 documented only, everything torn down |
| 02 | [RAG assistant over technical documentation](./practice-02/) — [build log](./practice-02/SETUP-LOG.md) · [Q&A](./practice-02/QNA.md) | Chunking strategies, embeddings, Bedrock Knowledge Bases, S3 Vectors, OpenSearch k-NN, hybrid search, reranking, MRR/NDCG, query decomposition, streaming | Stages 1-8 built and verified live, everything still running |
| 03 | [Resilient document analysis pipeline](./practice-03/) — [build log](./practice-03/SETUP-LOG.md) | Sync/async APIs, SQS + DLQ, SNS, WebSocket streaming, DynamoDB circuit breaker, X-Ray, Step Functions model routing — built on top of Practice 02's existing infrastructure rather than from scratch | Stages 1-7 built and verified live, everything still running |
| 04 | [AI-powered support ticket system](./practice-04/) — [build log](./practice-04/SETUP-LOG.md) | Lambda authorizers, Bedrock Prompt Flows, AWS Strands Agents, Bedrock Data Automation, a second Express Step Functions workflow, WebSocket chat, React + Amplify UI, a first pytest suite — built on top of Practice 02/03's infrastructure | Stages 1-16 built and verified live, everything still running |

Each practice lives in its own folder — the write-up is that folder's `README.md`, alongside its
build log, code, and anything else it produced. I'll add `practice-04/` etc. as I go.

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

— Digvijay Pundir. These are personal learning projects; AWS costs incurred are on me.
