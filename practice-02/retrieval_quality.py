"""
Stage 4: retrieval quality. Compares four retrieval approaches against the
same 10 test questions from Stage 2 (test_questions.py), scored with hit
rate, MRR, and NDCG:

  - keyword_only  : BM25 over the 6 whole documents, no AWS calls.
  - vector_only   : Bedrock KB retrieve() (Titan v2 + S3 Vectors, from Stage 3).
  - hybrid        : Reciprocal Rank Fusion of the two document-level rankings
                     above - the standard way to combine ranked lists that
                     have incomparable score scales (BM25 score vs. cosine
                     similarity).
  - hybrid_rerank : takes vector_only's actual retrieved chunk text (not just
                     doc identity) and re-scores it with Nova as an
                     LLM-as-judge reranker. Substitutes for Cohere's
                     dedicated rerank model, which tested working once and
                     then failed on identical calls minutes later (see the
                     write-up's "Model availability" section) - not reliable
                     enough to build on.

Run:
    python retrieval_quality.py

Requires the "rag-assistant" AWS CLI profile, the synced Knowledge Base
(KNOWLEDGE_BASE_ID below), and boto3 + rank_bm25 + numpy installed.
"""

import json
import math
from pathlib import Path

import boto3
from rank_bm25 import BM25Okapi

from chunking import load_corpus
from test_questions import TEST_QUESTIONS

AWS_PROFILE = "rag-assistant"
AWS_REGION = "us-east-1"
KNOWLEDGE_BASE_ID = "LTIWE7M3DC"
TOP_K = 3
RRF_K = 60
RERANK_MODEL = "amazon.nova-lite-v1:0"


def get_clients():
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return session.client("bedrock-agent-runtime"), session.client("bedrock-runtime")


def build_bm25_index():
    docs = load_corpus()
    doc_names = list(docs.keys())
    tokenized = [docs[name].lower().split() for name in doc_names]
    return BM25Okapi(tokenized), doc_names


def keyword_rank_docs(bm25, doc_names, query):
    scores = bm25.get_scores(query.lower().split())
    ranked = sorted(zip(doc_names, scores), key=lambda x: -x[1])
    return [name for name, _ in ranked]


def vector_search_chunks(agent_client, query, num_results=5):
    response = agent_client.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": num_results}},
    )
    chunks = []
    for r in response["retrievalResults"]:
        uri = r["location"]["s3Location"]["uri"]
        doc_name = Path(uri).stem
        chunks.append({"doc": doc_name, "text": r["content"]["text"], "score": r["score"]})
    return chunks


def dedup_docs_by_first_occurrence(chunks_or_docs, key=None):
    seen = []
    for item in chunks_or_docs:
        doc = item[key] if key else item
        if doc not in seen:
            seen.append(doc)
    return seen


def reciprocal_rank_fusion(ranked_lists, k=RRF_K):
    scores = {}
    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    return [doc for doc, _ in sorted(scores.items(), key=lambda x: -x[1])]


def _extract_score(element):
    if isinstance(element, (int, float)):
        return float(element)
    if isinstance(element, dict):
        for key in ("score", "relevance", "rating", "value"):
            if key in element and isinstance(element[key], (int, float)):
                return float(element[key])
    return 0.0


def nova_rerank_chunks(bedrock_client, query, chunks):
    prompt = (
        "Score how well each passage answers the question, on a scale of 0-10. "
        "Respond with ONLY a JSON array of integers, one score per passage, in the "
        "same order as the passages below - no other text.\n\n"
        f"Question: {query}\n\n"
    )
    for i, c in enumerate(chunks):
        prompt += f"Passage {i + 1}: {c['text'][:800]}\n\n"

    response = bedrock_client.converse(
        modelId=RERANK_MODEL,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 200, "temperature": 0},
    )
    output = response["output"]["message"]["content"][0]["text"]

    try:
        raw = json.loads(output[output.index("["):output.rindex("]") + 1])
        scores = [_extract_score(e) for e in raw]
    except (ValueError, json.JSONDecodeError):
        print(f"  [nova_rerank] couldn't parse model output, leaving order unchanged: {output!r}")
        scores = [0.0] * len(chunks)

    if len(scores) != len(chunks):
        print(f"  [nova_rerank] expected {len(chunks)} scores, got {len(scores)} - padding/truncating: {output!r}")
        scores = (scores + [0.0] * len(chunks))[:len(chunks)]

    reranked = sorted(zip(chunks, scores), key=lambda x: -x[1])
    return [c for c, _ in reranked]


def reciprocal_rank(ranked_docs, expected_doc):
    for i, doc in enumerate(ranked_docs, start=1):
        if doc == expected_doc:
            return i
    return None


def score_ranking(ranked_docs, expected_doc, top_k=TOP_K):
    rank = reciprocal_rank(ranked_docs, expected_doc)
    hit = rank is not None and rank <= top_k
    rr = 1.0 / rank if rank else 0.0
    ndcg = 1.0 / math.log2(rank + 1) if rank else 0.0  # binary relevance, ideal DCG = 1
    return hit, rr, ndcg


def summarize(name, results):
    n = len(results)
    hit_rate = sum(r[0] for r in results) / n
    mrr = sum(r[1] for r in results) / n
    ndcg = sum(r[2] for r in results) / n
    print(f"  {name:16s} hit_rate@{TOP_K}={hit_rate:.2f}  mrr={mrr:.3f}  ndcg={ndcg:.3f}")
    return {"hit_rate": hit_rate, "mrr": mrr, "ndcg": ndcg}


if __name__ == "__main__":
    agent_client, bedrock_client = get_clients()
    bm25, doc_names = build_bm25_index()

    print(f"Evaluating 4 retrieval approaches across {len(TEST_QUESTIONS)} test questions\n")

    keyword_results, vector_results, hybrid_results, reranked_results = [], [], [], []

    for q in TEST_QUESTIONS:
        expected = q["expected_doc"]

        keyword_ranked = keyword_rank_docs(bm25, doc_names, q["question"])
        keyword_results.append(score_ranking(keyword_ranked, expected))

        vector_chunks = vector_search_chunks(agent_client, q["question"])
        vector_ranked = dedup_docs_by_first_occurrence(vector_chunks, key="doc")
        vector_results.append(score_ranking(vector_ranked, expected))

        hybrid_ranked = reciprocal_rank_fusion([keyword_ranked, vector_ranked])
        hybrid_results.append(score_ranking(hybrid_ranked, expected))

        reranked_chunks = nova_rerank_chunks(bedrock_client, q["question"], vector_chunks)
        reranked_ranked = dedup_docs_by_first_occurrence(reranked_chunks, key="doc")
        reranked_results.append(score_ranking(reranked_ranked, expected))

    summary = {
        "keyword_only": summarize("keyword_only", keyword_results),
        "vector_only": summarize("vector_only", vector_results),
        "hybrid": summarize("hybrid", hybrid_results),
        "hybrid_reranked": summarize("hybrid_reranked", reranked_results),
    }

    out_path = Path(__file__).parent / "retrieval_quality_results.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote results to {out_path}")
