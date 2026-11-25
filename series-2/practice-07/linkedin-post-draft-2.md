🚦 I built a quality gate for my AI assistant, then deliberately broke the assistant to prove the gate works. The gate passed it anyway.

🧩 The problem
A RAG assistant can fail quietly: it makes up a sentence, it gets cut off mid-answer, or its safety filter blocks a perfectly good answer. Most teams watch one number, like a grounding score or an average quality score, and trust it to catch all of that. I wanted to know what a single number actually misses.

🛠️ What I built on Amazon Bedrock
• A claim-by-claim checker: it splits each answer into individual facts and checks every one against the source documents, using two different judge models.
• A comparison against Bedrock Guardrails' grounding score on the same answers.
• A results table in DynamoDB, so every score is stored, not just printed once.
• A quality gate in Lambda that re-scores the system against a stored baseline and raises an alert when quality drops. Its pass mark comes from measured variation, not a round number.

🔍 What it showed
1️⃣ The claim checker found a sentence that wasn't in the source document. The guardrail passed the same answer 5 times out of 5. A single score can't tell you *which* sentence is wrong.
2️⃣ I'd previously written that the grounding score is "random". It isn't. Hold the answer fixed and the score never moves; the randomness came from the model writing a new answer each time. I've corrected my earlier write-up.
3️⃣ When the guardrail blocks an answer, the original text is gone. One blocked answer looks like a false alarm, but there's no way left to check.
4️⃣ I cut the model to a 40-token limit, so 7 of 10 answers stopped mid-sentence. The gate passed it, and scored it *higher* than production. Every test question asked for one fact, the fact fit in 40 tokens, and shorter answers got blocked less. A gate is only as good as its test questions.
5️⃣ Four of my nine written predictions missed. Every miss had the same cause: I expected noise to be the problem, and the real problems were bias and coverage.

🐛 Bonus: my own loader reported "wrote 335 rows" and stored 303. Duplicate keys were silently overwriting each other. A test caught it.

💰 Total cost of the whole lab: about $0.27.

Everything is in the repo: the code, the raw results, the scored predictions and every bug 👇
🔗 https://github.com/digvijaypundir33/gen-ai-labs

#awsexamprep #genai #aws #bedrock #llmevaluation
