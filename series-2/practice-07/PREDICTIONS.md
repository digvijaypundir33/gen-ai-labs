# Practice 07 — Predictions

> **Committed 2026-11-14, before Stage 3's first model call.** This file is not edited after
> this commit. It gets scored in `README.md`, misses included.

Each prediction has a **falsifier**: the result that would prove me wrong.

## 1. Managed Q&A scores vs. P01's word-overlap ranking (Stage 4)

P01 ranked Nova Micro above Nova Lite on word overlap: 0.687 vs. 0.654, on its own finance
questions.

- **Prediction:** on the golden set, Bedrock's managed F1 will **not** reproduce a clear
  ranking. The Micro–Lite gap will be inside the noise.
- **Prediction:** both models will score low on F1 (mean < 0.4). The managed job sends the bare
  question to the model, with **no retrieval**, and the answers are long while the references
  are one-liners. So the managed score measures something different from our RAG system's
  quality.
- **Falsifier:** one model leads by more than the spread of the other's per-item scores, or the
  mean F1 is ≥ 0.4.

## 2. Bedrock's managed judge vs. my own judge (Stages 4c and 5)

- **Prediction:** on the 10 `generate` answers, the managed *Correctness* metric and my judge's
  factual-accuracy dimension agree on pass/fail for **at least 8 of 10** items. Pass means a
  score ≥ 4 of 5, or the managed equivalent.
- **Falsifier:** they agree on 7 or fewer.

## 3. A single-run judge vs. a five-run judge (Stage 5)

- **Prediction:** in at least **20%** of (item, dimension) cells, the five runs spread by ≥ 1
  point on the 1–5 scale. So a single run is not a stable measurement.
- **Prediction:** in at least one cell, the assignment's single-run score falls **outside** the
  five-run min–max range.
- **Prediction:** the gap between the Nova Micro and `gpt-oss-120b` judges' mean scores will be
  **no bigger** than either judge's own run-to-run spread. In other words, which judge you pick
  matters less than how many times you run it.
- **Falsifier:** fewer than 20% of cells vary; the single-run score always falls inside the
  range; the gap between judges clearly exceeds the spread within each judge.

## 4. Claim-level checks vs. managed grounding (Stage 6)

- **Prediction:** claim decomposition will flag at least one **unsupported claim** in an answer
  whose managed grounding score passed (≥ 0.75) on at least one of its five runs. The most likely
  place is P05's question known to produce hallucinations.
- **Prediction:** the managed grounding score for the same answer will again range by more than
  0.2 across five runs. P05 measured 0.30–0.72.
- **Falsifier:** claim checks find nothing the managed score missed, or the managed score is
  stable within 0.2.

## 5. The quality gate (Stage 8)

- **Prediction:** the gate **FAILS** on the degraded configuration (Nova Micro with a low
  `maxTokens`) and **PASSES** all 3 runs on the normal configuration, with no false alarms.
- **Falsifier:** the degraded configuration passes, or any normal run fails. The second would
  mean the threshold was set tighter than the measured noise.

## Cost

- **Prediction:** the whole practice costs **under $0.50**, measured from token usage.
- **Falsifier:** it costs more than $0.50.
