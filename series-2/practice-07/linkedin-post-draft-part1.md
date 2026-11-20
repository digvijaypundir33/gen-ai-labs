⚖️ I ran an LLM judge 5 times per answer to make it "rigorous". It gave the same score every time, and it was still wrong.

This is Part 1 of the first practice in my second series: building an evaluation system for my RAG assistant on Amazon Bedrock. Before building anything, I wrote down 5 predictions and committed them to git, so I couldn't adjust them after seeing the data. Two have already missed.

1️⃣ AWS's managed evaluation couldn't tell two models apart. Bedrock's built-in Q&A score gave Nova Micro 0.104 and Nova Lite 0.118, well inside the noise. My own earlier benchmark had "ranked" them too. That ranking was never real.

2️⃣ I expected judge noise to be the problem: in an earlier practice, single samples fooled me into a false finding. So I ran every judgment 5 times. At temperature 0.2, the scores barely moved (only 2–3% varied).

3️⃣ The real problem was bias. Two different judge models disagreed on the same answer *every single run*. The gap between the judges was ~4× either judge's run-to-run noise. Running a biased judge five times just repeats its mistake five times.

4️⃣ I checked the disagreements by hand. The "better" judge was right 5 times out of 6, but its one miss was on factual accuracy: it called a true claim false, because the claim wasn't in the short reference answer it was given. It was word for word in the AWS source document.

5️⃣ The cheaper judge didn't really score 6 dimensions. Every normal answer got 5/5 on everything, and every blocked answer got 1/5 on everything, including "fluency" for a perfectly fluent refusal. Six dimensions, one bit of information.

🐛 Bonus bug: collecting test data exposed that an internal "pick a bigger model" override from a previous practice was reachable from the public API. A code comment said it wasn't, but nobody had ever checked. Anyone could have asked for the model that costs 13× more. Fixed.

💰 Total spend so far: about $0.13.

Part 2 tomorrow: claim-by-claim hallucination checks, and a quality gate I'll try to break on purpose.

🔗 https://github.com/digvijaypundir33/gen-ai-labs

#awsexamprep #genai #aws #bedrock #llmevaluation
