import json

import boto3

agent_runtime = boto3.client("bedrock-agent-runtime")
bedrock_runtime = boto3.client("bedrock-runtime")

KNOWLEDGE_BASE_ID = "LTIWE7M3DC"
RERANK_MODEL = "amazon.nova-lite-v1:0"
RESULTS_PER_QUERY = 3
RERANK_CANDIDATES = 5
FINAL_TOP_K = 3


def retrieve_chunks(query, num_results=RESULTS_PER_QUERY):
    response = agent_runtime.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": num_results}},
    )
    chunks = []
    for r in response["retrievalResults"]:
        uri = r["location"]["s3Location"]["uri"]
        chunks.append({
            "doc": uri.split("/")[-1],
            "uri": uri,
            "text": r["content"]["text"],
            "score": r["score"],
        })
    return chunks


def merge_and_dedup(chunk_lists):
    best_by_text = {}
    for chunks in chunk_lists:
        for c in chunks:
            key = c["text"]
            if key not in best_by_text or c["score"] > best_by_text[key]["score"]:
                best_by_text[key] = c
    return sorted(best_by_text.values(), key=lambda c: -c["score"])


def _extract_score(element):
    if isinstance(element, (int, float)):
        return float(element)
    if isinstance(element, dict):
        for key in ("score", "relevance", "rating", "value"):
            if key in element and isinstance(element[key], (int, float)):
                return float(element[key])
    return 0.0


def nova_rerank(query, chunks):
    if not chunks:
        return []

    prompt = (
        "Score how well each passage answers the question, on a scale of 0-10. "
        "Respond with ONLY a JSON array of integers, one score per passage, in the "
        "same order as the passages below - no other text.\n\n"
        f"Question: {query}\n\n"
    )
    for i, c in enumerate(chunks):
        prompt += f"Passage {i + 1}: {c['text'][:800]}\n\n"

    response = bedrock_runtime.converse(
        modelId=RERANK_MODEL,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 200, "temperature": 0},
    )
    output = response["output"]["message"]["content"][0]["text"]

    try:
        raw = json.loads(output[output.index("["):output.rindex("]") + 1])
        scores = [_extract_score(e) for e in raw]
    except (ValueError, json.JSONDecodeError):
        scores = [0.0] * len(chunks)

    if len(scores) != len(chunks):
        scores = (scores + [0.0] * len(chunks))[:len(chunks)]

    reranked = sorted(zip(chunks, scores), key=lambda x: -x[1])
    return [c for c, _ in reranked]


def lambda_handler(event, context):
    queries = event.get("expandedQueries") or event.get("queries") or [event["query"]]
    primary_query = queries[0]

    chunk_lists = [retrieve_chunks(q) for q in queries]
    merged = merge_and_dedup(chunk_lists)

    reranked = nova_rerank(primary_query, merged[:RERANK_CANDIDATES])
    top = reranked[:FINAL_TOP_K]

    return {
        "query": primary_query,
        "results": [{"doc": c["doc"], "text": c["text"], "uri": c["uri"]} for c in top],
    }
