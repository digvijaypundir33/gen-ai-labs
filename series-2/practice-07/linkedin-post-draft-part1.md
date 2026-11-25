⚖️ How do you know your AI assistant's answers are actually good? Usually by asking another AI to grade them. But who checks the grader?

🧩 The problem
Most GenAI evaluation comes down to one of two things: a managed score from your cloud provider, or an "LLM-as-judge" that rates each answer once. Both produce clean-looking numbers. Almost nobody checks whether those numbers measure what they claim to, or whether two different graders would even agree.

🛠️ What I built
An evaluation lab for my RAG assistant on Amazon Bedrock, which answers AWS questions from a Knowledge Base, with a Guardrail in front.
• Collected 30 real answers from the live system and saved them, so every grader scores exactly the same answers.
• Ran Bedrock's managed evaluation on them: automatic Q&A scoring, plus an LLM judge built for RAG.
• Built my own judge on 6 quality dimensions, using two different model families, running every judgment 5 times.
• Wrote down 5 predictions and committed them to git before any data existed, so I couldn't adjust them afterwards.

🔍 What it showed
1️⃣ Bedrock's managed Q&A score couldn't tell two models apart (0.104 vs. 0.118), and neither could my earlier benchmark. That earlier "ranking" was never real.
2️⃣ Running a judge 5 times didn't help. At temperature 0.2 its scores barely moved; the real problem was bias. Two judges disagreed on the same answer every single run, by ~4× their own noise.
3️⃣ The more accurate judge's one mistake was the costliest kind: it marked a true fact as false, because the fact wasn't in the short reference answer it was given.
4️⃣ The cheaper judge's "6 dimensions" were really one: every answer got all 5s or all 1s.
5️⃣ Two of my own predictions missed. That's the point of writing them down first.

🐛 Collecting the data also exposed a real bug: a "use the bigger model" override that a code comment said was internal-only was reachable from the public API. Anyone could have requested the model that costs 13× more. Fixed.

💰 Total cost: about $0.13.

Everything is in the repo: the code, the raw results, the scored predictions and every bug 👇
🔗 https://github.com/digvijaypundir33/gen-ai-labs

#awsexamprep #genai #aws #bedrock #llmevaluation
