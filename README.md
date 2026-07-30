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
| 01 | [Resilient multi-model AI assistant on Amazon Bedrock](./Practice-01-Resilient-Multi-Model-Bedrock-Assistant.md) — [build log](./Practice-01-Setup-Log.md) | Bedrock, model benchmarking, AppConfig, Lambda, API Gateway, Step Functions, a real circuit breaker | Parts 1-3 built and tested live, Part 4 documented only, everything torn down |
| 02 | [RAG assistant over technical documentation](./Practice-02-RAG-Technical-Documentation-Assistant.md) — [build log](./Practice-02-Setup-Log.md) · [Q&A](./Practice-02-QnA.md) | Chunking strategies, embeddings, Bedrock Knowledge Bases, S3 Vectors, OpenSearch k-NN, hybrid search, reranking, MRR/NDCG, query decomposition, streaming | Stages 1-8 built and verified live, everything still running |

I'll add `Practice-03-...` etc. as separate files as I go.

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

— Digvijay Pundir. These are personal learning projects; AWS costs incurred are on me.
