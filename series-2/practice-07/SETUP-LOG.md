# Practice 07 — Setup log

Every AWS change this practice makes, with its idle cost and how to undo it. Region: `us-east-1`.

| # | Stage | Change | How | Idle cost | Undo / teardown |
|---|---|---|---|---|---|
| 1 | 3 | **`generate` (P02 Lambda) redeployed** with two changes. (a) An opt-in `include_debug` flag returns the retrieved chunk text, the answer model's token usage and `subQueries`. (b) The `tier` and `include_debug` overrides are now honoured only on direct invoke (no `requestContext` in the event). Until now, `tier` was reachable from the public `/ask` route. Normal responses are unchanged. | `zip -j generate.zip lambda_function.py && aws lambda update-function-code --function-name generate --zip-file fileb://generate.zip`. Verified by downloading the deployed code and diffing it (identical), then a live check on both paths. | $0 (code change only) | Redeploy the previous version: `git show 2770786:series-1/practice-02/lambda/generate/lambda_function.py > lambda_function.py`, then zip and `update-function-code` as before. That version is identical to what was deployed before (confirmed by the Stage 0 diff). |

## Spend so far

| Stage | Calls | Cost |
|---|---|---|
| 0 | ~8 one-word "Reply with OK" probe calls | < $0.001 |
| 3 | 2 smoke-test `generate` calls + 30 collection calls | ~$0.061 (estimated at P05's measured $0.0019 per `/ask` request; the answer model's tokens alone are far less) |
