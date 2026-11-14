🧪 I ran a fairness eval on my AI support system, found a clean, reproducible bias across 3 different scenarios — then spent an hour trying to prove myself wrong. I succeeded.

Here's what happened:

1️⃣ I wrote the same technical support ticket 5 different ways — formal, casual, non-native English phrasing, distressed tone, corporate-speak — and ran all 5 through the live system. Same underlying problem, every time.

2️⃣ The result looked damning: casual/non-native phrasing consistently got classified as higher urgency and got measurably less thorough responses than formal phrasing. Identical pattern, 3 scenarios in a row.

3️⃣ That consistency is what made it convincing — and it's also exactly why it was wrong. I'd only tested each condition ONCE per scenario. A single sample can look "reproducible" purely by chance.

4️⃣ Reran it properly: 6 independent trials per condition instead of 1. The urgency difference vanished — tied 6/6 vs 6/6. Reran the thoroughness claim with an independent scoring rubric instead of a single comparative judgment: tied on the concrete metric too.

5️⃣ Both original findings, retracted. The real lesson: a single-pass LLM-as-judge fairness check — which is literally how most "bias audits" get built — produces a convincing, narratively coherent, false result. It needs the same repeated-sampling rigor as any other noisy classifier.

🛡️ That was one piece of a bigger defense-in-depth build: a real Bedrock Guardrail tuned against a 30-prompt adversarial corpus (went from 50% to 97% accuracy by root-causing every false positive, not just cranking up a strictness slider), contextual grounding that caught a genuine model hallucination, and a tiered moderation workflow I built, measured, and then deliberately did NOT deploy — it saved 77% on moderation costs but missed 67% of actual attacks, because sentiment analysis isn't a harm detector.

🐛 The scariest bug: the WebSocket streaming path in my own UI — the DEFAULT mode users land on — had zero guardrail protection while the REST path right next to it was fully covered. Same app, same UI, one door locked and one wide open. Found it by accident while checking how sources get displayed.

📚 This is practice #5 in a series I'm building for real on my own AWS account as AWS exam prep — every practice gets the bugs, the retractions, and the real cost numbers documented, not just the parts that worked. Full write-up (every stage, every bug, the whole fairness retraction in detail) linked below. 👇

🔗 https://github.com/digvijaypundir33/gen-ai-labs

#awsexamprep #genai #aws #bedrock #responsibleai
