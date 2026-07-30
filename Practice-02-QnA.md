# Practice 02 — Q&A

Questions I'd expect to be asked about the RAG system in
[Practice 02](./Practice-02-RAG-Technical-Documentation-Assistant.md), with the answers I'd
give. Written for quick verbal recall rather than as documentation — the answers are the length
you'd actually say out loud, and where a question has a trap in it, the trap is called out.

Concept definitions live in the main write-up; this file is about *being asked*.

---

## RAG fundamentals

**Q: What is RAG and why use it instead of just asking the model?**

A foundation model only knows what was in its training data, frozen at a cutoff date, and when it
doesn't know something it tends to produce a plausible-sounding answer anyway. RAG retrieves
relevant documents at question time and puts them in the prompt, so the model's job becomes
reading comprehension over supplied text rather than recall. That gets you three things: current
information without retraining, the ability to cite sources, and far less hallucination — because
the model is answering *from* something you can point at.

**Q: RAG vs fine-tuning — when would you pick which?**

They solve different problems and the common mistake is treating them as alternatives. Fine-tuning
changes how the model *behaves* — tone, output format, domain-specific reasoning patterns. RAG
changes what the model *knows*. If your problem is "the model doesn't know our internal docs,"
fine-tuning is the wrong tool: it's expensive, needs redoing whenever the docs change, and still
won't let you cite a source. If your problem is "the model won't produce output in our required
structure," RAG won't fix that. They compose — fine-tune for behaviour, RAG for knowledge.

For this project RAG was clearly right: technical documentation changes constantly, and citations
matter.

**Q: Walk me through the request path end to end.**

A question arrives at API Gateway with an API key. Step Functions decides whether it's a simple or
complex question — complex ones get decomposed into independent sub-questions. Each question gets
expanded into a few alternate phrasings, then those are embedded and used to search the vector
store, in parallel with a keyword search. The two result sets get fused, the top candidates get
re-ranked by a more expensive model, and the best few become context in a prompt to Nova, which
produces the answer with citations back to source documents.

**Q: Where does RAG typically fail?**

Almost always in retrieval, not generation. If the right chunk never gets retrieved, no amount of
prompt engineering saves the answer. The usual causes are bad chunking (the answer got split
across a boundary), vocabulary mismatch between how users ask and how documents are written, and
the absence of keyword search for things like error codes and version numbers, which semantic
search is genuinely bad at.

The second failure mode is retrieving correctly and then having the model ignore the context and
answer from memory anyway — that's a grounding/prompting problem.

---

## Chunking

**Q: Why chunk at all? Why not embed whole documents?**

Two reasons. An embedding is a fixed-length vector regardless of input length, so embedding a
fifty-page document compresses everything into one point — it ends up representing the average
topic and matching nothing specific. And even if retrieval worked, you'd be pasting fifty pages
into a prompt, which is expensive and buries the relevant paragraph in noise.

**Q: What chunking strategies did you compare, and what's the tradeoff?**

Three: fixed-size with overlap, hierarchical (splitting on document structure like headings), and
semantic (splitting where the topic actually shifts, detected by comparing embeddings of adjacent
sentences).

Fixed-size is trivial to implement and completely structure-blind — it'll happily cut a code
example in half. Hierarchical respects the document's own organisation and gives you parent-child
relationships for free, but it depends on the documents actually having consistent structure.
Semantic produces the most coherent chunks but costs embedding calls at *ingestion* time to find
the boundaries, and it's the slowest.

The honest answer for technical documentation is that hierarchical usually wins, because docs have
real heading structure and a section is a genuinely meaningful retrieval unit.

**Q: How do you pick chunk size?**

Empirically, against your own corpus and question set — there's no universal right answer. The
tension is that small chunks give precise retrieval but may lack the surrounding context needed to
answer, while large chunks carry context but dilute the embedding and waste prompt tokens. A
common starting range is 300-800 tokens with 10-20% overlap, then measure.

The measurement matters more than the starting point. That's why Stage 2 of this project is a
comparison harness rather than a single chosen value.

**Q: What's overlap for, and what does it cost?**

If a relevant passage straddles a chunk boundary, neither chunk contains the whole thing and both
may score poorly. Overlap repeats the tail of each chunk into the head of the next so boundary
passages survive intact. The cost is proportional to how much you repeat — 20% overlap means 20%
more chunks, so 20% more embedding calls and 20% more storage.

**Q: (Trap) The reference code had `chunk_size=1000` and `overlap=100`. What's wrong with that?**

Nothing, if the units match — but in one of the reference implementations they don't.
`max_chunk_size` counts *characters* while the overlap logic takes the last 100 *words*. A hundred
words is roughly six hundred characters, so a "10% overlap" is actually about 60%, inflating chunk
count and embedding cost roughly 2.5×. Silent, because nothing errors — it just costs more and
fills the index with near-duplicates.

**Q: What is parent-child chunking?**

You retrieve on small chunks for precision, but pass the *parent* chunk (or full section) to the
model for context. Best of both: the embedding is specific enough to match the question, but the
model sees enough surrounding text to actually answer. Requires storing the parent-child
relationship — which is one of the things the DynamoDB metadata table in this project is for.

---

## Embeddings

**Q: What is an embedding, in one sentence?**

A fixed-length vector of floats that positions a piece of text in a space where semantic
similarity corresponds to geometric closeness.

**Q: Why cosine similarity rather than Euclidean distance?**

Cosine measures the angle between vectors and ignores their magnitude. For text, magnitude tends
to correlate with things you don't care about — length, emphasis, repetition — while direction
captures meaning. Two documents saying the same thing at different lengths should be similar, and
cosine gives you that. Note that if your vectors are normalised to unit length (Titan v2 does
this), cosine similarity and dot product rank identically.

**Q: How did you choose an embedding model?**

Measured rather than assumed. Two checks: a retrieval check — do the right chunks come back for a
set of hand-written test questions, scored with precision/recall — and a contrast check — encode
pairs I know are semantically similar and pairs I know aren't, and see whether the model
*separates* them. A model that scores 0.95 on similar pairs and 0.94 on dissimilar pairs is
useless regardless of the absolute numbers; the gap is what matters.

Cost and dimension matter too: fewer dimensions means less storage and faster search, so if a
1024-dimension model matches a 1536-dimension one on retrieval quality, take the smaller one.

**Q: (Trap) Can you compare two embedding models in the same vector index?**

No, and this is a bug in the reference. A vector index is built for one specific dimension —
Titan v1 produces 1536, Titan v2 and Cohere v3 produce 1024. The reference hardcodes
`"dimension": 1536` in the index mapping while a separate phase compares Titan against Cohere.
Those two phases contradict each other. You need one index per embedding model, which also means
re-embedding the entire corpus per model.

That last point is the real operational lesson: **changing embedding models means a full
re-index**, not a config flip. It's the most expensive change to make later, so it's worth
measuring properly up front.

**Q: What happens if you embed a query with a different model than you embedded the documents?**

Garbage results — and, importantly, no error. The vectors are the same shape so the arithmetic
works; the numbers just don't mean the same thing. Similarity scores come back looking plausible
while the ranking is meaningless. It's a nasty failure mode precisely because nothing crashes.

---

## Vector stores

**Q: What vector store options do you have on AWS, and how do you choose?**

Broadly: OpenSearch Service (self-managed cluster), OpenSearch Serverless, Aurora PostgreSQL with
pgvector, S3 Vectors, and third-party options like Pinecone through a Bedrock Knowledge Base.

The deciding question is usually cost shape rather than features. OpenSearch and Aurora bill by
the hour whether you query or not; S3 Vectors bills for storage and queries. For a workload with
constant high query volume the cluster amortises fine. For intermittent querying — which is most
internal tools, and definitely a learning project — hourly billing dominates the bill.

**Q: What did you pick and why?**

Bedrock Knowledge Base backed by S3 Vectors as the durable store, because it's ~$0 idle, plus a
single-node `t3.small.search` OpenSearch domain spun up only for the sessions where I wanted
hands-on with k-NN index mappings and HNSW tuning, then deleted the same day.

The reference specified multi-node `r6g.large.search` clusters plus Aurora pgvector, which is
$400-600/month in idle charges for a project that queries a few hundred times total. The single
small node teaches the same lessons for about a dollar a day.

**Q: (Trap) What's the hidden cost in creating a Bedrock Knowledge Base?**

The console defaults to "quick create a new vector store," which silently provisions **OpenSearch
Serverless**. That has a 2-OCU minimum — roughly $0.48/hour, about **$350/month** — for a knowledge
base holding fifty documents. There's no warning, and it's the single most common way people get
surprised by a Bedrock bill. Pick the vector store backend explicitly.

**Q: What does Bedrock Knowledge Base actually do for you?**

It manages the whole ingestion pipeline: point it at a data source (S3, web crawler, Confluence,
SharePoint), pick an embedding model and chunking strategy, and it handles chunking, embedding,
storage, sync, and retrieval. You get a `Retrieve` API for just the chunks, or `RetrieveAndGenerate`
for a full RAG answer.

The tradeoff is control. You don't get to implement your own chunking logic or tune HNSW
parameters. That's exactly why this project builds both paths — the managed one for the realistic
production answer, and the hand-rolled OpenSearch one for understanding what the managed one is
doing.

**Q: (Trap) Which boto3 client creates a Knowledge Base?**

`bedrock-agent`, not `bedrock`. The reference gets this wrong in both projects. `bedrock` is the
control plane for models, `bedrock-runtime` is for invoking them, `bedrock-agent` is for Knowledge
Bases and Agents, and `bedrock-agent-runtime` is for querying them. Four clients, easy to mix up.

---

## Search and retrieval

**Q: Explain ANN versus exact k-NN.**

Exact k-NN compares the query vector against every stored vector — perfectly accurate, and O(n),
so it stops being viable somewhere in the hundreds of thousands of vectors. ANN builds an index
structure that lets you search a small fraction of the corpus and find *almost* the true nearest
neighbours. You trade a few percent of recall for orders of magnitude of speed. At real corpus
sizes it isn't really a choice.

**Q: Explain HNSW and its parameters.**

Hierarchical Navigable Small World. It builds a layered graph where each vector connects to its
nearest neighbours, with sparse upper layers for coarse navigation and a dense bottom layer for
fine search. A query enters at the top, greedily walks toward closer nodes, and descends.

Three parameters: `m` is the max connections per node — higher gives better recall and uses more
memory. `ef_construction` is how many candidates are considered when building the index — higher
builds a better graph, more slowly. `ef_search` is how many candidates are considered at query
time — higher means better recall and slower queries, and it's tunable per query without
rebuilding the index. That last point matters operationally: `ef_search` is your runtime
recall/latency dial.

**Q: Why does semantic search need keyword search alongside it?**

Because embeddings capture meaning and deliberately discard exact form. Ask about error code
`ORA-01555` and semantic search returns chunks about database errors generally — it has no
particular attachment to that exact string. Keyword search nails it. Conversely, ask "how do I
stop the app crashing on startup" and keyword search finds nothing because the docs say
"initialisation failure," while semantic search handles it easily.

They fail in opposite directions, which is exactly why hybrid works.

**Q: How do you combine keyword and vector scores? They're not on the same scale.**

That's the whole problem — a BM25 score of 12.4 and a cosine similarity of 0.83 aren't comparable,
and normalising them is fragile because BM25 is unbounded and corpus-dependent.

The standard answer is **Reciprocal Rank Fusion**: ignore the scores entirely and use only rank
position. Each document scores `sum(1 / (k + rank))` over the lists it appears in, with `k` around
60. Documents ranked highly by both methods rise to the top; the scale problem disappears because
you never compare the scores.

**Q: What is reranking and why does it help?**

Your vector search uses a bi-encoder — query and documents encoded separately, which is what makes
it fast, since document embeddings are precomputed. But it means the model never sees the query
and document *together*, so it can't reason about how they relate.

A reranker is a cross-encoder: it takes the query and one document as a single input and scores
the pair, so it can attend across both. Much more accurate, far too slow to run over the corpus.

So you do both: retrieve ~20 candidates cheaply with the bi-encoder, rerank just those with the
cross-encoder, keep the top 3-5. You get cross-encoder quality at close to bi-encoder cost.

**Q: What if no reranking model is available to you?**

That's the situation I'm actually in — the only rerank model in my account is Cohere's, which goes
through an AWS Marketplace subscription that's currently blocked for me. The substitution is
LLM-as-judge: prompt Nova with the query and each candidate and have it score relevance, then sort
by that score.

It's slower and costs inference calls, but it's a legitimate approach, and it makes the scoring
criteria explicit and tunable rather than opaque.

**Q: What is metadata filtering and why does it matter beyond relevance?**

Storing attributes alongside each vector — document type, date, author, source system — and
restricting search to a subset. Obvious relevance benefit: "search only policy documents from this
year."

The less obvious and more important use is **access control**. In a multi-tenant or
permission-scoped system, filtering by tenant or by the requesting user's permitted document set
is what stops one user's query from retrieving another's documents. That's a security control, not
a relevance feature, and it needs to be enforced server-side — never trusted from the client.

---

## Evaluation

**Q: How do you know your retrieval is any good?**

Build a test set: questions paired with the chunks that should answer them. Then measure precision
(of what came back, how much was relevant) and recall (of what should have come back, how much
did). For RAG, recall at the retrieval stage matters more than precision — a relevant chunk that
never gets retrieved is unrecoverable, whereas an irrelevant chunk that does get retrieved can
still be filtered by reranking.

Building that test set by hand is tedious and it's the part people skip, which is why so many RAG
systems are tuned on vibes.

**Q: Explain MRR and NDCG, and when you'd use each.**

MRR — Mean Reciprocal Rank — averages `1 / (rank of the first relevant result)` across queries.
If the first good result is at position 3, that query scores 0.33. It only looks at the first hit,
so it's the right metric when one correct answer is all you need.

NDCG — Normalised Discounted Cumulative Gain — scores the whole ranked list, weighting results by
position with a logarithmic discount, then normalises against a perfect ranking so it lands
between 0 and 1. It's the right metric when the ordering of several results matters — which is the
RAG case, since you're passing the top-k as context and you want the best ones first.

**Q: What comparisons did you actually run?**

Vector-only, keyword-only, hybrid, and hybrid-plus-reranking, scored with MRR and NDCG against the
same test question set. That's the comparison that tells you whether the added complexity of
hybrid search and reranking is buying anything on *your* corpus — sometimes it isn't, and it's
worth knowing that before shipping it.

**Q: (Trap) The reference scored quality with word overlap. What's wrong with that?**

It rewards verbosity. A longer answer overlaps more words with the reference answer by chance, so
padding improves the score. It's also blind to paraphrase — a perfect answer using different
vocabulary scores badly.

Better options are embedding similarity between the generated answer and a reference answer, or
LLM-as-judge with an explicit rubric. I used word overlap in Practice 01 knowing it was weak,
because getting the *pipeline* working end to end mattered more for a first pass than the scoring
function — but I'd call it out as a known limitation rather than defend it.

---

## Query processing

**Q: What is query expansion and why bother?**

Users ask questions in different words than documentation is written in. Expansion rewrites one
question into several phrasings — using an LLM — and searches with all of them, unioning the
results. It directly attacks vocabulary mismatch, which is one of the top retrieval failure modes.

Cost: an extra LLM call and several searches per question, so it's a latency/quality trade you
make deliberately rather than always.

**Q: What is query decomposition?**

Breaking a complex question into independent sub-questions. "How does the retry behaviour in
service A compare to service B under load?" is really three retrievals — A's retry behaviour, B's
retry behaviour, and load characteristics — that then get synthesised. A single vector search for
the whole question retrieves something vaguely related to all three and precisely relevant to
none.

**Q: Why orchestrate that with Step Functions rather than just doing it in one Lambda?**

Visibility and control flow. The decomposition path is genuinely branching — decide complexity,
maybe fan out over sub-questions, aggregate, rerank — and Step Functions gives you that as a
declarative state machine with a per-execution visual trace of which path ran. When something
returns a bad answer, you can see whether it decomposed, what each sub-query retrieved, and where
it went wrong. In a single Lambda that's all buried in logs.

You also get Map-state parallelism over sub-questions for free, and retries and error handling per
step rather than one try/except around everything.

**Q: What would you cache, and what's the risk?**

Query embeddings are the obvious one — the same question asked twice shouldn't be embedded twice.
Full answers can be cached too, keyed on a normalised question.

The risk is staleness: if the underlying documents change, cached answers silently become wrong.
So the cache key needs to incorporate some version of the corpus state, or the TTL needs to be
short enough that stale answers age out faster than documents change.

---

## Generation and grounding

**Q: How do you stop the model answering from memory instead of the retrieved context?**

Explicit instruction in the system prompt — answer only from the provided context, and if the
context doesn't contain the answer, say so rather than guessing. Then require citations, which
makes ungrounded claims visible: if the model can't point at a chunk, it made it up.

Verification is the part people skip. You can check whether the cited chunk actually supports the
claim, either with a second model call or by string-matching key facts. That's how you catch
grounding failures rather than hoping.

**Q: How much context do you pass, and why not all of it?**

Top 3-5 chunks after reranking, typically. Not because of the context window — modern windows are
large — but because relevance density matters. Padding the prompt with marginally relevant chunks
measurably degrades answer quality, since the model has to work out what's actually pertinent. It
also costs input tokens on every single query.

**Q: How do citations work?**

Each chunk carries metadata identifying its source document and location. Those travel with the
chunk into the prompt, the model is instructed to cite which chunks it used, and the answer is
rendered with links back to source documents. It's the single biggest trust feature in a RAG
system — users can verify rather than take the answer on faith.

**Q: How do you keep the vector store current when documents change?**

Checksum each document at ingestion and store it in the metadata table. On re-sync, compare
checksums and re-process only what changed — re-chunking and re-embedding an unchanged corpus on
every run is pure waste. Schedule the sync with EventBridge, and if different sources have
different volatility, give them different schedules.

The subtle part is deletion: if a document is removed at the source, its chunks need removing from
the vector store too, or you'll keep retrieving and citing content that no longer exists.

---

## Architecture, cost, and operations

**Q: What's the most expensive mistake someone can make building this?**

Leaving a vector store cluster running. Everything else in this architecture — Lambda, S3,
DynamoDB On-Demand, Step Functions Express, API Gateway, Bedrock — is pay-per-use and costs
effectively nothing while idle. OpenSearch and Aurora bill by the hour regardless. The entire cost
question for this project reduced to one decision, which is why I made it before touching the
console.

**Q: Where does the money actually go in a running RAG system?**

Usually not where people expect. Embedding is a one-time cost per document and is cheap — embedding
several hundred pages costs well under a dollar. Generation is per-query and modest with a small
model. The vector store is the recurring floor if it's cluster-based.

The thing that surprises people is that **re-embedding** is the expensive operation, and you're
forced into it whenever you change embedding model or chunking strategy. That's why those two
decisions deserve the measurement effort up front.

**Q: (Trap) Your ingestion Lambda is triggered by S3 and writes back to S3. What's the problem?**

Infinite recursion, if the trigger isn't prefix-scoped. The Lambda writes its output into the same
bucket that triggers it, which triggers it again. In a RAG pipeline that means runaway Bedrock
embedding calls, so it's a cost incident, not just a bug. Fix: scope the trigger to the input
prefix only, or write output to a separate bucket. AWS added recursion detection that eventually
halts it, but you don't want to rely on that.

**Q: (Trap) How do you trigger a Lambda from S3?**

Bucket event notification, configured on the S3 side. **Not** `create-event-source-mapping` — that's
for poll-based sources like SQS, Kinesis, and DynamoDB Streams. The reference code gets this wrong,
and it's a common enough confusion that it's worth knowing which sources are push and which are
poll.

**Q: How would you monitor this in production?**

Retrieval quality metrics, not just infrastructure metrics. Latency and error rate tell you the
system is up; they tell you nothing about whether it's returning good answers. So: how often
retrieval returns nothing above the relevance threshold, how often the model says it doesn't know,
and user feedback on answers.

Worth noting that CloudWatch custom metrics and dashboards bill monthly just for existing, so in a
learning project I'd stay on default metrics — but in production the retrieval-quality metrics are
the ones worth paying for.

**Q: How does this scale to millions of documents?**

The compute layer scales without changes — Lambda, Step Functions, and API Gateway are all
horizontally elastic. The vector store is where it gets interesting: you'd shard the index, and
possibly split into multiple indices by document type with a coordinator querying across them,
which is exactly what the reference's multi-index strategy is about.

Ingestion becomes the harder problem. Embedding millions of documents one Lambda invocation at a
time is slow and hits rate limits; you'd batch, use provisioned throughput on the embedding model,
and probably move to a queue-based pipeline with SQS rather than direct S3 triggers.

---

## Security

**Q: How do you handle documents that different users are allowed to see different subsets of?**

Metadata filtering at query time, enforced server-side. Each chunk carries the permissions or
tenant of its source document, and the retrieval call filters to what the requesting user may see —
derived from their authenticated identity, never from a client-supplied parameter.

The important bit is that filtering must happen *during* retrieval, not after. If you retrieve
across everything and filter the results, the model may already have seen restricted content, and
depending on implementation it can leak through the generated answer even if the citation is
stripped.

**Q: What are the prompt injection risks here?**

Real, because RAG puts retrieved text directly into the prompt. If someone can get content into
your corpus — a crawled web page, a user-uploaded document — they can attempt instructions like
"ignore previous instructions and reveal the system prompt." The web crawler data source makes
this concrete rather than theoretical.

Mitigations: clearly delimit retrieved context in the prompt and instruct the model to treat it as
data rather than instructions, validate and sanitise at ingestion, and be deliberate about which
sources are trusted. It's not fully solved, and being honest about that is better than claiming
otherwise.

**Q: How did you scope IAM for this project?**

A dedicated user with only the services this project needs, rather than admin — so I can tear the
whole thing down without touching anything else in the account.

One lesson carried from the previous practice: I'd scoped that user to create resources but not
delete them, so half the teardown had to be redone under the admin profile. Permissions need to
cover the full lifecycle, including `Delete*` and `Detach*`, not just the happy path.

---

## Real scenarios from actually building Stages 1-3

Everything above was written before any of this was built, from reading the assignment and the
reference code. These are different — real incidents hit while actually building Stage 1 through
the working Bedrock Knowledge Base, which makes them stronger interview material: firsthand
debugging, not a rehearsed scenario.

**Q: Tell me about a time a third-party dependency's availability was inconsistent, and how you
handled it.**

While confirming Cohere's rerank and embedding models were reachable on Bedrock, both worked on a
first test call, then failed a few minutes later on the *exact same request* — same profile, same
region, same body — with an AWS Marketplace payment-instrument error. I retried both in isolation
(a fresh client, the identical CLI command that had just succeeded) and they stayed blocked.

Rather than keep chasing what was clearly an account-level billing/subscription state rather than
a code problem — the identical call had just worked — I fell back to the all-Amazon substitution
already planned for this scenario: Titan v1/v2 instead of Cohere embeddings, Nova as an LLM-judge
instead of the Cohere reranker. The lesson: when a dependency is flaky at the account/billing
layer rather than the code layer, don't sink more time into a diagnosis you can't act on — have a
same-outcome fallback ready and switch to it, with the reason documented rather than pretending
it's resolved.

**Q: Describe a bug you found in your own code, not someone else's.**

My first semantic-chunking implementation used a fixed similarity threshold (0.55) to decide
where to break a chunk — if two consecutive sentences' embeddings scored below that, start a new
chunk. It ran without errors but produced absurd results: most "chunks" were a single sentence.

Instead of guessing at a new threshold, I measured what Titan v2 was actually producing on the
real corpus — sentence-to-sentence cosine similarity ranged from about 0.07 to 0.90 with a mean
around 0.50. My threshold sat almost exactly at that mean, so it triggered a break on roughly half
of all sentence transitions. The fix was to stop using a fixed absolute number and compute the
threshold relative to *each document's own* similarity distribution instead — break only at the
bottom quartile of that document's transitions. The general lesson: measure the actual data
distribution before picking a magic-number constant; a threshold that "sounds reasonable" in the
abstract can be meaningless against the real numbers.

**Q: Tell me about a mistake that your own permission scoping caught for you.**

I mistyped an S3 Vectors bucket name in the console — created `ag-assistant-vectors` instead of
`rag-assistant-vectors`, missing the leading letter. When I tried deleting it under the project's
scoped IAM user, the delete was denied, because the inline policy for that user was scoped
specifically to the correctly-spelled bucket's ARN — the typo'd bucket didn't match that resource
pattern at all.

Mildly annoying in the moment (had to fall back to an admin profile for that one cleanup call),
but it's the scoping working exactly as intended: a resource-scoped policy can't touch resources
outside its scope, even ones created by mistake under the same account. Good illustration of why
least-privilege IAM is worth the friction — it fails safe, even against your own typos.

**Q: How do you handle it when a cloud provider silently changes a default you were relying on?**

Setting up a Bedrock Knowledge Base, I found the console's creation wizard now defaults to a
"Managed KB" option — AWS handles the vector store internally — rather than the customer-managed
flow my plan assumed, where you explicitly connect your own vector store. I didn't catch this
until the wrong KB type already existed and a sync had failed with a generic access-denied error
that, on the surface, looked like a permissions problem.

Rather than debug the wrong architecture further, I checked the actual resource config
(`get-knowledge-base`) and confirmed it had no reference to the S3 Vectors index I'd built at
all — proof it was the wrong resource entirely, not a fixable permission gap. Deleted it, went
back through the wizard, and this time deliberately chose "Self-managed KB → Unstructured Vector
Store KB" instead of the highlighted "recommended" default. General lesson: when a managed
service's UI changes its defaults, verify what actually got created via the API rather than
trusting that the console flow matched your mental model — reading the resource's own
configuration back is usually the fastest diagnosis.

**Q: Describe a subtle interaction bug between two services that don't fully account for each
other.**

Ingesting documents into a Bedrock Knowledge Base backed by S3 Vectors failed with "Filterable
metadata must have at most 2048 bytes." Bedrock stores each chunk's actual text as metadata
alongside its vector; S3 Vectors caps *filterable* metadata (the kind you can search or filter on)
at 2KB per vector, but allows far more if a field is marked non-filterable instead. My S3 Vectors
index was created without specifying which fields should be non-filterable, so everything
defaulted to filterable — including the chunk text itself. Since I'd chosen hierarchical chunking
with parent chunks up to 1500 tokens, some chunks' text alone exceeded 2KB.

The fix was recreating the index with Bedrock's two internal metadata field names
(`AMAZON_BEDROCK_TEXT`, `AMAZON_BEDROCK_METADATA`) explicitly marked non-filterable. What makes
this a good example: it isn't a bug in either service individually — Bedrock's default chunk
sizes are reasonable, S3 Vectors' 2KB filterable cap is reasonable — the two defaults simply
collide when composed together, and neither service's quickstart path warns you about the other's
constraints. Worth remembering whenever you compose two managed services: check the intersection
of their defaults, not just each one in isolation.

---

## The "tell me about a problem" questions

**Q: Tell me about a bug you found in code you were given.**

The chunking function in the reference never terminates. It loops `while start < len(text)`, and on
the final chunk sets `start = end - overlap` where `end` is the text length — so `start` is always
less than the length and the loop appends the same final chunk forever.

What makes it a good example is that it's not an edge case. It hangs on *every* input, and it
would present as a Lambda timeout rather than an obvious infinite loop, so you'd probably start by
investigating memory or the document size before reading the loop condition carefully.

**Q: Tell me about a time you changed an architecture for cost reasons.**

This project as specified used multi-node OpenSearch plus Aurora pgvector — around $400-600 a month
in idle charges. Since it's a personal learning project I'm funding, that wasn't viable, but I also
didn't want to skip the vector-search learning by only using the managed service.

So I split it: Bedrock Knowledge Base on S3 Vectors as the durable store at essentially zero idle
cost, plus a single small OpenSearch node created and destroyed within a single working session
for the hands-on index-tuning work. Same learning outcomes, roughly a dollar a day instead of
hundreds a month.

The generalisable point is that the constraint improved the design's honesty — I now know exactly
which components bill while idle and which don't, which is the thing that actually matters in
production too.

**Q: What would you do differently with more time or budget?**

Three things. Build a bigger and better-labelled evaluation set — the quality of every tuning
decision is capped by the quality of the test data, and mine is hand-written and small. Implement
proper semantic chunking with measured boundary detection rather than treating it as one option
among three. And run the retrieval strategies as a live A/B test rather than an offline
comparison, because offline relevance judgements and what users actually find useful diverge more
than people expect.

---

_Part of [Gen AI Practice](./README.md)._
