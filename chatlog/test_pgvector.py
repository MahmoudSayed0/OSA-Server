import os
from langchain.docstore.document import Document
from langchain_community.vectorstores import PGVector
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import TokenTextSplitter


# 1. Create embeddings (FREE, local)
# This downloads a small SentenceTransformers model on first run (~80MB)
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# 2. Connection string to Postgresimport os

# NOTE: Connection string should come from environment variables
CONNECTION_STRING = os.getenv('PGVECTOR_CONNECTION') or os.getenv('DATABASE_URL', '')

# 3. Name of the collection (table)
COLLECTION_NAME = "chunked_document"

# 4. Initialize vector store
vectorstore = PGVector(
    connection_string=CONNECTION_STRING,
    embedding_function=embeddings,
    collection_name="chunked_docs",
)

# 5. Large Paragraph
large_text = """
Artificial intelligence (AI) is rapidly transforming industries and society at large.
From healthcare and finance to transportation and education, AI is enabling new possibilities
and efficiencies that were previously unimaginable. One of the most significant advancements
in AI has been in the area of natural language processing (NLP). NLP allows computers to
understand, interpret, and generate human language, enabling applications like chatbots,
translation services, and intelligent search engines. However, with these advancements come
ethical challenges, such as bias in AI models, data privacy concerns, and the potential impact
on employment. As AI continues to evolve, it will be critical for policymakers, researchers,
and industry leaders to collaborate on guidelines and frameworks that ensure AI is developed
responsibly and used for the benefit of all.
"""

# 6. Chunking by token
text_splitter = TokenTextSplitter(chunk_size=50, chunk_overlap=10)
chunks = text_splitter.split_text(large_text)

docs = [Document(page_content=chunk, metadata={"chunk": i}) for i, chunk in enumerate(chunks)]

print("📖 Chunks created:")
for i, d in enumerate(docs):
    print(f"Chunk {i}: {d.page_content[:80]}...")

# 7. Insert chunks into PGVector
vectorstore.add_documents(docs)
print("✅ Chunked documents inserted into pgvector")

# 8. Test a query
query = "What are the risks of AI?"
results = vectorstore.similarity_search(query, k=2)

print("🔎 Query:", query)
for r in results:
    print("-", r.page_content)