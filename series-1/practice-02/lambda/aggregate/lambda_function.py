def lambda_handler(event, context):
    original_query = event["originalQuery"]
    sub_query_results = event["subQueryResults"]

    seen_texts = set()
    merged = []
    for sub_result in sub_query_results:
        for chunk in sub_result.get("results", []):
            if chunk["text"] not in seen_texts:
                seen_texts.add(chunk["text"])
                merged.append(chunk)

    return {
        "query": original_query,
        "subQueries": [sr["query"] for sr in sub_query_results],
        "results": merged,
    }
