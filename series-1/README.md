# Series 1 — Building it

Six hands-on AWS/Bedrock practices. Each one is an exam-prep assignment built for real on my
own account, with a build log that records every resource created and how to tear it down.

| # | Practice |
|---|----------|
| 01 | [Resilient multi-model AI assistant on Amazon Bedrock](./practice-01/) |
| 02 | [RAG assistant over technical documentation](./practice-02/) |
| 03 | [Resilient document analysis pipeline](./practice-03/) |
| 04 | [AI-powered support ticket system](./practice-04/) |
| 05 | [Safe & responsible AI assistant](./practice-05/) |
| 06 | [Cost, performance and observability optimisation](./practice-06/) |

Topics, status and costs for each practice are in the [repo README](../README.md).
[Series 2](../series-2/) picks up from here: it measures and audits what these practices built.

**Running scripts after the move:** the practices moved under `series-1/` together, so the
cross-practice imports (`sys.path.insert(0, "../practice-02")` in P05 and P06) still resolve.
Run each script from inside its own practice folder, as before.
