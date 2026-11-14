

# Retrieve data and generate AI responses with Amazon Bedrock Knowledge Bases
<a name="knowledge-base"></a>

While foundation models have general knowledge, you can further improve their responses by using Retrieval Augmented Generation (RAG). RAG is a technique that uses information from data sources to improve the relevancy and accuracy of generated responses. With Amazon Bedrock Knowledge Bases, you can integrate proprietary information into your generative-AI applications. When a query is made, a knowledge base searches your data to find relevant information to answer the query. The retrieved information can then be used to improve generated responses. Amazon Bedrock Knowledge Bases helps build secure, enterprise-grade agentic AI applications by leveraging retrieval securely over large-scale datasets.

**Important**  
For optimized retrieval accuracy and a managed experience, we recommend [Amazon Bedrock Managed Knowledge Base](kb-build-managed.md).

Amazon Bedrock Knowledge Bases offers two types of knowledge bases:
+ **Managed Knowledge Base** – Amazon Bedrock manages the underlying data ingestion, indexing, storage, and retrieval infrastructure so you can focus on your application and agent logic. Managed Knowledge Base offers advanced capabilities including ingestion of multi-modal data, storage auto-scaling, agentic retrieval for multi-hop reasoning and more while continuing to offer key customizations so you can tailor agents to your use case. You connect your data sources and Amazon Bedrock manages embedding, re-ranking, and reasoning with service-managed models by default (with option to choose your own models). Managed Knowledge Base integrates natively with AgentCore Gateway so any MCP-compatible agent framework can discover and invoke your Knowledge Base as a tool without custom code. Managed Knowledge offers connectors for Amazon S3, SharePoint, Confluence, Google Drive, OneDrive, Web Crawler, along with document-level permission filtering using Access Control Lists (except for Web Crawler) at retrieval time. The Smart Parsing feature auto-selects parsing strategy per document type including PDFs, PPTX, DOCX, documents with embedded visuals, audio, video, and scanned documents. Agentic Retrieval supports multi-hop reasoning, decomposes complex queries into sub-queries, retrieves iteratively across multiple knowledge bases, and evaluates sufficiency of responses. Native integration with AgentCore Observability offers built-in monitoring, retrieval traces, agentic traces, and per-knowledge base metrics.
+ **Customer-managed Knowledge Base** – This enables you set up and manage your own RAG pipeline, including the vector store (such as Amazon OpenSearch Serverless, Amazon Aurora, and Amazon Neptune), and have full control over data ingestion, parsing, indexing and storage configurations. You will need to setup and manage related infrastructure and configurations such as parsing for multimodal data. Note that several capabilities such as third-party connectors, document-level permissions and native AgentCore Gateway integration are only available for Managed Knowledge Bases.

With Amazon Bedrock Knowledge Bases, you can:
+ Answer user queries by returning relevant information from data sources.
+ Use retrieved information from data sources to help generate an accurate and relevant response to user queries.
+ Augment your own prompts by feeding the returned relevant information into the prompt.
+ Include citations in the generated response so the original data source can be referenced and accuracy can be checked.
+ Include documents with copious visual resources, from which images can be extracted and retrieved in responses to queries. If you generate a response based on the retrieved data, the model can deliver additional insights based on these images.
+ Search using images as queries to find visually similar content, or combine text and images in queries for more precise results using multimodal embedding models.
+ Use reranking models to influence the results that are retrieved from your data source.

**Topics**
+ [How knowledge bases work](kb-how-it-works.md)
+ [Supported models and Regions](knowledge-base-supported.md)
+ [Chat with your document with zero setup](knowledge-base-chatdoc.md)
+ [Set up permissions to create and manage knowledge bases](knowledge-base-prereq-permissions-general.md)
+ [Build a managed knowledge base](kb-build-managed.md)
+ [Build a knowledge base with vector stores](knowledge-base-build.md)
+ [Build a knowledge base by connecting to a structured data store](knowledge-base-build-structured.md)
+ [Build a knowledge base with an Amazon Kendra GenAI index](knowledge-base-build-kendra-genai-index.md)
+ [Build a knowledge base with Amazon Neptune Analytics graphs](knowledge-base-build-graphs.md)
+ [Test your knowledge base with queries and responses](knowledge-base-test.md)
+ [Deploy your knowledge base for your application](knowledge-base-deploy.md)
+ [View information about a knowledge base](kb-info.md)
+ [Modify a knowledge base](kb-update.md)
+ [Delete a knowledge base](kb-delete.md)