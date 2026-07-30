"""
Embeds the chunks from chunking_results.json with three models (Titan v1,
Titan v2, Cohere v3), scores retrieval against test_questions.py, and runs a
cosine-similarity contrast check (known-similar vs. known-dissimilar
sentence pairs) per model.

Because there's exactly one correct source document per test question, "did
the correct document show up in the top-k retrieved chunks" is used as the
precision/recall proxy here, plus a lightweight MRR (rank of the first
correct-document chunk across the full ranking, not just top-k). This is a
smaller version of the same MRR/NDCG evaluation Stage 4 does more fully once
there's a real vector store and multi-document relevance judgments to work
with - here it's just enough to pick a chunking strategy + embedding model.

Run:
    python embeddings.py

Requires the "rag-assistant" AWS CLI profile, chunking_results.json (run
chunking.py first), and boto3 + numpy installed.
"""

import json
from pathlib import Path

from chunking import cosine_similarity, get_bedrock_runtime
from test_questions import TEST_QUESTIONS

TOP_K = 3

# cohere.embed-english-v3 tested successfully, then started failing on identical
# calls minutes later (AWS Marketplace payment-instrument state flipping
# mid-session, not a code issue - see write-up's "Model availability" section).
# Left out of the active comparison; embed_batch still supports it if it's ever
# worth retrying.
EMBED_MODELS = {
    "titan-v1": {"model_id": "amazon.titan-embed-text-v1", "provider": "titan"},
    "titan-v2": {"model_id": "amazon.titan-embed-text-v2:0", "provider": "titan"},
}

CONTRAST_PAIRS = {
    "similar": [
        (
            "Lambda invokes your function in a secure and isolated execution environment.",
            "Lambda provisions a separate instance of the execution environment for each concurrent request.",
        ),
        (
            "DynamoDB on-demand mode automatically scales to accommodate demanding workloads.",
            "On-demand mode eliminates the need for capacity planning in DynamoDB.",
        ),
    ],
    "dissimilar": [
        (
            "Lambda invokes your function in a secure and isolated execution environment.",
            "S3 Versioning is disabled by default on buckets and must be explicitly enabled.",
        ),
        (
            "DynamoDB charges you per read and write request in on-demand mode.",
            "API Gateway caches responses from your endpoint for a specified TTL period.",
        ),
    ],
}


def embed_batch(client, texts, model_key, input_type):
    cfg = EMBED_MODELS[model_key]
    if cfg["provider"] == "titan":
        embeddings = []
        for text in texts:
            response = client.invoke_model(
                modelId=cfg["model_id"],
                contentType="application/json",
                accept="application/json",
                body=json.dumps({"inputText": text}),
            )
            embeddings.append(json.loads(response["body"].read())["embedding"])
        return embeddings

    embeddings = []
    for i in range(0, len(texts), 96):  # Cohere batches up to 96 texts/call
        batch = texts[i:i + 96]
        response = client.invoke_model(
            modelId=cfg["model_id"],
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"texts": batch, "input_type": input_type}),
        )
        body = json.loads(response["body"].read())
        embeddings.extend(body["embeddings"])
    return embeddings


def flatten_chunks(strategy_docs):
    chunks = []
    for doc_name, doc_chunks in strategy_docs.items():
        for c in doc_chunks:
            chunks.append({"text": c["text"], "doc": doc_name})
    return chunks


def evaluate_combo(client, chunks, model_key, question_embeddings):
    chunk_texts = [c["text"] for c in chunks]
    chunk_embeddings = embed_batch(client, chunk_texts, model_key, input_type="search_document")

    hits = 0
    reciprocal_ranks = []
    for question, q_emb in zip(TEST_QUESTIONS, question_embeddings):
        scored = sorted(
            ((cosine_similarity(q_emb, c_emb), c["doc"]) for c_emb, c in zip(chunk_embeddings, chunks)),
            key=lambda x: -x[0],
        )
        top_docs = [doc for _, doc in scored[:TOP_K]]
        if question["expected_doc"] in top_docs:
            hits += 1
        rank = next((i + 1 for i, (_, doc) in enumerate(scored) if doc == question["expected_doc"]), None)
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)

    return {
        f"hit_rate_at_{TOP_K}": hits / len(TEST_QUESTIONS),
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
    }


def run_contrast_check(client, model_key):
    def avg_similarity(pairs):
        sims = []
        for a, b in pairs:
            emb_a, emb_b = embed_batch(client, [a, b], model_key, input_type="search_document")
            sims.append(cosine_similarity(emb_a, emb_b))
        return sum(sims) / len(sims)

    similar_avg = avg_similarity(CONTRAST_PAIRS["similar"])
    dissimilar_avg = avg_similarity(CONTRAST_PAIRS["dissimilar"])
    return {
        "similar_pairs_avg": similar_avg,
        "dissimilar_pairs_avg": dissimilar_avg,
        "separation": similar_avg - dissimilar_avg,
    }


if __name__ == "__main__":
    client = get_bedrock_runtime()
    chunking_results = json.load(open(Path(__file__).parent / "chunking_results.json"))
    question_texts = [q["question"] for q in TEST_QUESTIONS]

    print("Contrast check (higher separation = model distinguishes similar vs. dissimilar text better)\n")
    contrast_results = {}
    for model_key in EMBED_MODELS:
        contrast_results[model_key] = run_contrast_check(client, model_key)
        r = contrast_results[model_key]
        print(f"  {model_key:12s} similar={r['similar_pairs_avg']:.3f}  "
              f"dissimilar={r['dissimilar_pairs_avg']:.3f}  separation={r['separation']:+.3f}")

    print(f"\nRetrieval evaluation (top-{TOP_K} hit rate + MRR across {len(TEST_QUESTIONS)} test questions)\n")
    retrieval_results = {}
    for model_key in EMBED_MODELS:
        question_embeddings = embed_batch(client, question_texts, model_key, input_type="search_query")
        retrieval_results[model_key] = {}
        for strategy_name, strategy_docs in chunking_results.items():
            chunks = flatten_chunks(strategy_docs)
            metrics = evaluate_combo(client, chunks, model_key, question_embeddings)
            retrieval_results[model_key][strategy_name] = metrics
            print(f"  {model_key:12s} {strategy_name:12s} "
                  f"hit_rate@{TOP_K}={metrics[f'hit_rate_at_{TOP_K}']:.2f}  mrr={metrics['mrr']:.3f}")

    out_path = Path(__file__).parent / "embedding_evaluation_results.json"
    with open(out_path, "w") as f:
        json.dump({"contrast_check": contrast_results, "retrieval": retrieval_results}, f, indent=2)
    print(f"\nWrote full results to {out_path}")
