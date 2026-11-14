"""
Stage 2: evaluate Bonus Assignment 01 Part 1 Step 3's `compress_prompt()` against
this system's REAL prompts, to decide whether to adopt it.

The assignment presents prompt compression as an obvious token saving. That claim
is testable, so this tests it rather than accepting or dismissing it: the
compressor is copied verbatim from practice-06.md (lines 163-229), then run over
every prompt string this system actually sends to Bedrock, plus the two large
free-text blocks (a retrieved RAG chunk and a ticket description) that are the
only places in the whole pipeline with enough prose for filler-stripping to
plausibly matter.

Token counts are real `tiktoken`/cl100k_base BPE counts (the same encoding
ticket-submit already uses in production), not the assignment's `len(text)//4`
heuristic - measuring a token-savings claim with a fake token counter would beg
the question.

Run:  python prompt_compression_eval.py
Deps: tiktoken  (local analysis only - nothing here ships to a Lambda)
"""

import re

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text):
    return len(_enc.encode(text))


# ---------------------------------------------------------------------------
# compress_prompt(), copied verbatim from practice-06.md lines 163-229.
# Unmodified on purpose - the point is to evaluate what the assignment ships.
# ---------------------------------------------------------------------------
def compress_prompt(prompt: str, target_reduction: float = 0.3) -> str:
    filler_phrases = [
        "I was wondering if", "I would like to know", "Can you tell me",
        "I'm curious about", "Please provide information on", "I need to understand",
        "Could you explain", "I want to learn about", "Please help me understand",
        "I would appreciate it if you could", "It would be great if you could",
        "I'm interested in learning"
    ]

    compressed = prompt
    for phrase in filler_phrases:
        compressed = compressed.replace(phrase, "")

    replacements = {
        "in order to": "to",
        "due to the fact that": "because",
        "at this point in time": "now",
        "a large number of": "many",
        "a majority of": "most",
        "a sufficient amount of": "enough",
        "in the event that": "if",
        "in the near future": "soon",
        "in spite of the fact that": "although",
        "with regard to": "about",
        "with the exception of": "except",
    }

    for verbose, concise in replacements.items():
        compressed = compressed.replace(verbose, concise)

    redundant_words = [
        "very", "really", "quite", "basically", "actually", "definitely",
        "certainly", "probably", "essentially", "fundamentally", "particularly"
    ]

    for word in redundant_words:
        compressed = re.sub(r'\b' + word + r'\b', '', compressed)

    compressed = re.sub(r'\s+', ' ', compressed).strip()

    original_tokens = count_tokens(prompt)
    compressed_tokens = count_tokens(compressed)

    if compressed_tokens > original_tokens * (1 - target_reduction):
        # "Look for sections to truncate" - keeps only the FIRST and LAST
        # sentence of anything with >3 sentences. See findings.
        sections = compressed.split(". ")
        if len(sections) > 3:
            compressed = sections[0] + ". " + sections[-1]

    return compressed


# ---------------------------------------------------------------------------
# The real prompts. Every string this system actually sends to Bedrock.
# ---------------------------------------------------------------------------
QUERY = "What is the default total concurrency limit for Lambda functions?"

# practice-02/lambda/generate/lambda_function.py:149-153
GENERATE_INSTRUCTION = (
    "Use the reference material to answer the question below. Include a [Source N] "
    "citation for any fact you use. If the material doesn't cover the answer, state "
    f"that clearly.\n\nQuestion: {QUERY}"
)

# practice-04/lambda/ticket-classify/lambda_function.py:17-20
TICKET_CLASSIFY_SYSTEM = (
    "You are a support ticket triage assistant. Classify the ticket's category "
    "and urgency, and briefly explain why."
)

# practice-02/lambda/query_expand/lambda_function.py:18-22
QUERY_EXPAND = (
    "Generate 3 alternative phrasings of this question that use different "
    "vocabulary but ask the same thing - this is for a search system, so the "
    "goal is to catch documents that use different wording than the question. "
    'Respond with ONLY a JSON array of 3 strings, no other text.\n\n'
    f"Question: {QUERY}"
)

# practice-02/lambda/query_router/lambda_function.py:78
QUERY_ROUTER = (
    'Respond with ONLY valid JSON: {"isComplex": true} or {"isComplex": false}.\n\n'
    f"Question: {QUERY}"
)

# A real retrieved chunk, from practice-02/corpus/raw-docs/lambda-concurrency.md.
# This is grounding_source material - the guardrail scores the answer against it.
RAG_CHUNK = (
    "[Source 1: lambda-concurrency]\n"
    "Concurrency is the number of in-flight requests that your AWS Lambda function "
    "is handling at the same time. For each concurrent request, Lambda provisions a "
    "separate instance of your execution environment. As your functions receive more "
    "requests, Lambda automatically handles scaling the number of execution "
    "environments until you reach your account's concurrency limit. By default, "
    "Lambda provides your account with a total concurrency limit of 1,000 concurrent "
    "executions across all functions in an AWS Region. To support your specific "
    "account needs, you can request a quota increase and configure function-level "
    "concurrency controls so that your critical functions don't experience throttling."
)

# A realistic support ticket description - the free-text a user actually writes,
# and the most filler-prone input anywhere in the system.
TICKET_DESCRIPTION = (
    "Hi, I was wondering if you could help me out. I'm curious about why my Lambda "
    "function is basically timing out all the time. It was working fine last week and "
    "now it's really slow. I would like to know if this is due to the fact that we "
    "increased traffic, or if something else is going on. Could you explain what might "
    "be happening? I would appreciate it if you could get back to me soon, this is "
    "actually quite urgent for us."
)

PROMPTS = [
    ("generate instruction", GENERATE_INSTRUCTION, "system prompt"),
    ("ticket-classify system", TICKET_CLASSIFY_SYSTEM, "system prompt"),
    ("query_expand", QUERY_EXPAND, "system prompt"),
    ("query_router classify", QUERY_ROUTER, "system prompt"),
    ("RAG chunk (grounding_source)", RAG_CHUNK, "retrieved content"),
    ("ticket description (user text)", TICKET_DESCRIPTION, "user free text"),
]


def main():
    print("=" * 78)
    print("Stage 2: prompt compression evaluated against real system prompts")
    print("Token counts: tiktoken cl100k_base (real BPE, not len//4)")
    print("=" * 78)
    print()

    total_before = total_after = 0
    rows = []

    for name, text, kind in PROMPTS:
        before = count_tokens(text)
        compressed = compress_prompt(text)
        after = count_tokens(compressed)
        saved = before - after
        pct = (saved / before * 100) if before else 0.0
        mangled = compressed != text
        total_before += before
        total_after += after
        rows.append((name, kind, before, after, saved, pct, mangled, text, compressed))

    print(f"{'prompt':32s} {'kind':18s} {'tok':>5s} {'→':>5s} {'saved':>6s} {'%':>7s}")
    print("-" * 78)
    for name, kind, before, after, saved, pct, *_ in rows:
        print(f"{name:32s} {kind:18s} {before:5d} {after:5d} {saved:6d} {pct:6.1f}%")
    print("-" * 78)
    tot_saved = total_before - total_after
    tot_pct = (tot_saved / total_before * 100) if total_before else 0.0
    print(f"{'TOTAL':32s} {'':18s} {total_before:5d} {total_after:5d} {tot_saved:6d} {tot_pct:6.1f}%")
    print()

    # Which prompts were altered at all, and did any lose meaning?
    print("=" * 78)
    print("Content changes (the part that decides whether this is safe)")
    print("=" * 78)
    for name, kind, before, after, saved, pct, mangled, orig, comp in rows:
        if not mangled:
            print(f"\n[{name}] UNCHANGED - compressor found nothing to strip.")
            continue
        print(f"\n[{name}] ALTERED  ({before} → {after} tokens)")
        print(f"  before: {orig[:150]}{'...' if len(orig) > 150 else ''}")
        print(f"  after : {comp[:150]}{'...' if len(comp) > 150 else ''}")
        # Did the ">3 sentences" truncation branch fire? That drops whole
        # sentences, which is destructive rather than compressive.
        orig_sentences = len(orig.split(". "))
        comp_sentences = len(comp.split(". "))
        if orig_sentences > 3 and comp_sentences < orig_sentences:
            print(f"  !! TRUNCATION BRANCH FIRED: {orig_sentences} sentences → "
                  f"{comp_sentences}. Middle content dropped entirely.")

    # ---------------------------------------------------------------------
    # The decisive test: token savings are only a saving if meaning survives.
    # These are the specific load-bearing strings - the grounding contract in
    # the prompt, and the answer fact in the retrieved source.
    # ---------------------------------------------------------------------
    print()
    print("=" * 78)
    print("Survival check: did the load-bearing content survive compression?")
    print("=" * 78)

    checks = [
        ("generate instruction", GENERATE_INSTRUCTION,
         [("[Source N] citation requirement", "citation"),
          ("\"state that clearly\" (the don't-guess instruction)", "state that clearly")]),
        ("RAG chunk (grounding_source)", RAG_CHUNK,
         [("the answer fact itself (\"1,000 concurrent executions\")", "1,000 concurrent"),
          ("the per-Region qualifier", "AWS Region")]),
        ("ticket description", TICKET_DESCRIPTION,
         [("the urgency signal", "urgent"),
          ("the traffic-increase hypothesis", "increased traffic")]),
    ]

    lost_total = 0
    for name, text, items in checks:
        comp = compress_prompt(text)
        print(f"\n[{name}]")
        for label, needle in items:
            survived = needle.lower() in comp.lower()
            if not survived:
                lost_total += 1
            print(f"  {'OK  ' if survived else 'LOST'}  {label}")

    print()
    print("=" * 78)
    print(f"VERDICT: {tot_pct:.1f}% fewer tokens, but {lost_total} load-bearing "
          f"element(s) destroyed.")
    print("The savings come from the truncation branch deleting whole sentences,")
    print("not from removing filler. A token counter alone cannot see this.")
    print("=" * 78)


if __name__ == "__main__":
    main()
