"""
Stage 3: evaluate Bonus Assignment 02 Part 2 Step 1's `QueryPreprocessor`
(nltk stopword removal + lemmatization + a hand-maintained synonym dict)
against this system's actual retrieval stack, to decide whether to adopt it.

The assignment presents classic-NLP query preprocessing as a retrieval
improvement. That framing comes from the keyword/BM25 era, where dropping
function words and collapsing inflections genuinely helps a term-matching
index. This system retrieves by *embedding similarity* against a Bedrock
Knowledge Base, which is a different mechanism - so the claim needs testing
rather than assuming, in either direction.

The measurement: embed each real corpus question twice with the same model the
KB itself uses (amazon.titan-embed-text-v2, 1024-d) - once raw, once
preprocessed - and measure cosine similarity between the two vectors. That
directly answers the only question that matters here:

  Does preprocessing move the query's position in the same embedding space
  the KB is indexed in? If it barely moves, preprocessing cannot change
  retrieval and is pure added dependency. If it moves a lot, that is a risk,
  not a win, because the raw question is what the user actually asked.

Why not measure retrieval quality end-to-end instead: practice-02 documented
that its retrieval eval **saturated** - hit_rate@3, MRR and NDCG all scored
1.000 for every strategy, because the corpus is 6 documents on clearly
distinct topics. A saturated metric cannot discriminate between two
approaches, so measuring embedding displacement is the honest alternative.

Run:  python query_preprocessing_eval.py
Deps: nltk, numpy, boto3 (local analysis only - nothing ships to a Lambda)
"""

import re
import sys

import boto3
import nltk
import numpy as np
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

sys.path.insert(0, "../practice-02")
from test_questions import TEST_QUESTIONS  # noqa: E402

EMBED_MODEL = "amazon.titan-embed-text-v2:0"  # the model the KB is indexed with
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


# ---------------------------------------------------------------------------
# QueryPreprocessor, from practice-06.md lines 1237-1320 (Bonus 02 Part 2).
# Trimmed only of the synonym-expansion method whose body the assignment
# truncates mid-file; the preprocessing pipeline itself is as written.
# ---------------------------------------------------------------------------
class QueryPreprocessor:
    def __init__(self):
        self.stop_words = set(stopwords.words("english"))
        self.lemmatizer = WordNetLemmatizer()
        self.domain_terms = {
            "aws", "s3", "ec2", "lambda", "dynamodb", "rds", "cloudfront",
            "vpc", "iam", "cloudwatch", "sqs", "sns", "ebs", "efs",
            "route53", "cloudformation", "fargate", "eks", "ecs",
        }

    def preprocess(self, query: str) -> str:
        q = query.lower()
        for term in self.domain_terms:
            q = q.replace(term, f"___{term}___")
        q = re.sub(r"[^\w\s]", " ", q)
        for term in self.domain_terms:
            q = q.replace(f"___{term}___", term)
        tokens = nltk.word_tokenize(q)
        filtered = [t for t in tokens
                    if t.lower() in self.domain_terms or t.lower() not in self.stop_words]
        lemmatized = [t if t.lower() in self.domain_terms else self.lemmatizer.lemmatize(t)
                      for t in filtered]
        return " ".join(lemmatized)


def embed(text):
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=f'{{"inputText": {__import__("json").dumps(text)}, "dimensions": 1024, "normalize": true}}',
    )
    return np.array(__import__("json").loads(resp["body"].read())["embedding"])


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def main():
    pre = QueryPreprocessor()

    print("=" * 92)
    print("Stage 3: nltk query preprocessing vs. raw query, in the KB's own embedding space")
    print(f"Embedding model: {EMBED_MODEL} (1024-d, normalized) - same as the KB index")
    print("=" * 92)
    print()

    sims, dropped_counts = [], []
    rows = []

    for tq in TEST_QUESTIONS:
        raw = tq["question"]
        processed = pre.preprocess(raw)
        sim = cosine(embed(raw), embed(processed))
        raw_words = len(raw.split())
        proc_words = len(processed.split())
        dropped = raw_words - proc_words
        sims.append(sim)
        dropped_counts.append(dropped)
        rows.append((raw, processed, sim, raw_words, proc_words, dropped))

    for raw, processed, sim, rw, pw, dropped in rows:
        print(f"cos={sim:.4f}  words {rw:2d}→{pw:2d} (-{dropped})")
        print(f"   raw : {raw}")
        print(f"   proc: {processed}")
        print()

    print("=" * 92)
    print(f"n = {len(sims)} real corpus questions")
    print(f"cosine similarity raw vs preprocessed:  mean={np.mean(sims):.4f}  "
          f"min={np.min(sims):.4f}  max={np.max(sims):.4f}  stdev={np.std(sims):.4f}")
    print(f"words removed per query:                mean={np.mean(dropped_counts):.1f}  "
          f"max={np.max(dropped_counts)}")
    print("=" * 92)
    print()
    print("Reading the number:")
    print("  ~1.00 => preprocessing does not meaningfully move the query in the space")
    print("           the KB is indexed in, so it cannot change what gets retrieved.")
    print("           It would add an nltk dependency + bundled corpora + a")
    print("           hand-maintained synonym dict for no retrieval effect.")
    print("  <0.95 => preprocessing materially relocates the query. That is a risk,")
    print("           not a win: the raw question is what the user actually asked,")
    print("           and the KB was indexed on natural prose, not stripped tokens.")


if __name__ == "__main__":
    main()
