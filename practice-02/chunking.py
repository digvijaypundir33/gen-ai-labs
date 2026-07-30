"""
Three chunking strategies for the corpus in corpus/raw-docs/, with the
reference assignment's bugs fixed:

  - fixed_size: character-window chunking with sentence-boundary snapping.
    The reference's version never terminates (see Practice-02 write-up,
    bug #1) - last iteration always set start = end - overlap, which stays
    < len(text) forever. Fixed by breaking once end reaches the text length.

  - hierarchical: splits on markdown headings (#, ##, ###, ####) using a
    heading stack, so it handles arbitrary nesting depth and tracks each
    chunk's parent section. The reference only split on a fixed "\\n## "
    pattern, so anything not exactly H2 was ignored.

  - semantic: splits where adjacent sentences' embeddings diverge past a
    similarity threshold. The reference's "semantic_chunking" wasn't
    semantic at all - it sent one prompt asking a text-generation model to
    "split this into chunks" and never parsed a chunk list out of the
    response. This version actually computes sentence-to-sentence cosine
    similarity via Titan embeddings.

Run:
    python chunking.py

Requires the "rag-assistant" AWS CLI profile and boto3 + numpy installed.
"""

import json
import re
from pathlib import Path

import boto3
import numpy as np

AWS_PROFILE = "rag-assistant"
AWS_REGION = "us-east-1"
CORPUS_DIR = Path(__file__).parent / "corpus" / "raw-docs"

SEMANTIC_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
SEMANTIC_BREAK_PERCENTILE = 25  # break only at the most-dissimilar quartile of transitions
SEMANTIC_MIN_CHUNK_SENTENCES = 2
SEMANTIC_MAX_CHUNK_CHARS = 1500


def get_bedrock_runtime():
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return session.client("bedrock-runtime")


def load_corpus():
    docs = {}
    for path in sorted(CORPUS_DIR.glob("*.md")):
        docs[path.stem] = path.read_text(encoding="utf-8")
    return docs


def fixed_size_chunking(text, chunk_size=1000, overlap=100):
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end < text_len:
            search_floor = max(start + chunk_size // 2, start + 1)
            for i in range(end - 1, search_floor, -1):
                if text[i] in ".?!" and i + 1 < text_len and text[i + 1] == " ":
                    end = i + 1
                    break
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({"text": chunk_text})
        if end >= text_len:
            break
        start = end - overlap
    return chunks


HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)")


def hierarchical_chunking(text):
    lines = text.split("\n")
    chunks = []
    stack = []
    current_lines = []
    current_level = 0
    current_title = None

    def flush():
        content = "\n".join(current_lines).strip()
        if not content:
            return
        parent = stack[-2][1] if len(stack) >= 2 else None
        chunks.append({
            "text": content,
            "level": current_level,
            "title": current_title,
            "parent_section": parent,
        })

    for line in lines:
        match = HEADING_RE.match(line)
        if match:
            flush()
            current_lines = [line]
            level = len(match.group(1))
            title = match.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current_level = level
            current_title = title
        else:
            current_lines.append(line)
    flush()
    return chunks


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


def embed_titan(client, text, model_id=SEMANTIC_EMBED_MODEL):
    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text}),
    )
    return json.loads(response["body"].read())["embedding"]


def semantic_chunking(text, client):
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if len(sentences) <= 1:
        return [{"text": text.strip()}] if text.strip() else []

    embeddings = [embed_titan(client, s) for s in sentences]
    sims = [cosine_similarity(embeddings[i - 1], embeddings[i]) for i in range(1, len(sentences))]

    # Titan sentence-to-sentence similarity spans a wide range even within one
    # topic (observed ~0.07-0.90 on this corpus), so a fixed cutoff either
    # breaks almost everywhere or almost nowhere depending on the document.
    # Break only at the most-dissimilar quartile of THIS document's own
    # transitions, so the boundary is relative to its own texture.
    break_threshold = float(np.percentile(sims, SEMANTIC_BREAK_PERCENTILE))

    chunks = []
    current = [sentences[0]]
    current_len = len(sentences[0])

    for i in range(1, len(sentences)):
        sim = sims[i - 1]
        sentence = sentences[i]
        boundary_hit = sim <= break_threshold and len(current) >= SEMANTIC_MIN_CHUNK_SENTENCES
        size_hit = current_len + len(sentence) > SEMANTIC_MAX_CHUNK_CHARS
        if boundary_hit or size_hit:
            chunks.append({"text": " ".join(current)})
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += len(sentence)

    if current:
        chunks.append({"text": " ".join(current)})

    return chunks


def summarize(strategy_name, doc_name, chunks):
    lengths = [len(c["text"]) for c in chunks]
    avg_len = sum(lengths) / len(lengths) if lengths else 0
    print(f"  {strategy_name:12s} {doc_name:35s} {len(chunks):3d} chunks, avg {avg_len:6.0f} chars")


if __name__ == "__main__":
    docs = load_corpus()
    print(f"Loaded {len(docs)} documents from {CORPUS_DIR}\n")

    client = get_bedrock_runtime()
    results = {"fixed_size": {}, "hierarchical": {}, "semantic": {}}

    for doc_name, text in docs.items():
        results["fixed_size"][doc_name] = fixed_size_chunking(text)
        summarize("fixed_size", doc_name, results["fixed_size"][doc_name])

    for doc_name, text in docs.items():
        results["hierarchical"][doc_name] = hierarchical_chunking(text)
        summarize("hierarchical", doc_name, results["hierarchical"][doc_name])

    print("\nRunning semantic chunking (one Titan embed call per sentence - slowest strategy)...")
    for doc_name, text in docs.items():
        results["semantic"][doc_name] = semantic_chunking(text, client)
        summarize("semantic", doc_name, results["semantic"][doc_name])

    out_path = Path(__file__).parent / "chunking_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote all chunks to {out_path}")
