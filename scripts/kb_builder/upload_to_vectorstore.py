"""
Vector Store Uploader

Uploads processed document chunks to the PostgreSQL/pgvector database
used by the Safety Agent.

This integrates with the existing LangChain PGVector setup in the main app.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path for Django imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import PROCESSED_DIR, LOGS_DIR, LOGGING_CONFIG

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG["level"]),
    format=LOGGING_CONFIG["format"],
    handlers=[
        logging.FileHandler(LOGS_DIR / "upload.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("vectorstore_uploader")


class VectorStoreUploader:
    """Upload chunks to the vector database."""

    def __init__(self):
        self.chunks_file = PROCESSED_DIR / "chunks.jsonl"
        self.collection_name = "foundation_knowledge_base"
        self.batch_size = 100
        self.uploaded_count = 0

    def _setup_django(self):
        """Initialize Django settings for database access."""
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Safety_agent_Django.settings")
        import django
        django.setup()

    def _get_vectorstore(self):
        """Get the PGVector store connection."""
        from langchain_postgres import PGVector
        from langchain_openai import OpenAIEmbeddings

        # Use same connection as main app
        connection_string = os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/safety_agent"
        )

        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

        vectorstore = PGVector(
            connection=connection_string,
            collection_name=self.collection_name,
            embeddings=embeddings,
        )

        return vectorstore

    def upload_chunks(self):
        """Upload all processed chunks to vector store."""
        if not self.chunks_file.exists():
            logger.error(f"Chunks file not found: {self.chunks_file}")
            logger.info("Run the document processor first: python process_documents.py")
            return

        logger.info("=" * 60)
        logger.info("Uploading to Vector Store")
        logger.info(f"Collection: {self.collection_name}")
        logger.info("=" * 60)

        # Setup Django and get vectorstore
        self._setup_django()
        vectorstore = self._get_vectorstore()

        # Read and upload chunks in batches
        texts = []
        metadatas = []
        batch_num = 0

        with open(self.chunks_file, "r") as f:
            for line in f:
                chunk = json.loads(line)

                texts.append(chunk["content"])
                metadatas.append({
                    "source": chunk["source"],
                    "source_type": chunk["source_type"],
                    "category": chunk["category"],
                    "title": chunk["title"],
                    "chunk_index": chunk["chunk_index"],
                    "total_chunks": chunk["total_chunks"],
                    "word_count": chunk["word_count"],
                    "content_hash": chunk["content_hash"],
                })

                # Upload in batches
                if len(texts) >= self.batch_size:
                    batch_num += 1
                    logger.info(f"Uploading batch {batch_num} ({len(texts)} chunks)...")

                    try:
                        vectorstore.add_texts(texts=texts, metadatas=metadatas)
                        self.uploaded_count += len(texts)
                    except Exception as e:
                        logger.error(f"Batch {batch_num} failed: {e}")

                    texts = []
                    metadatas = []

        # Upload remaining chunks
        if texts:
            batch_num += 1
            logger.info(f"Uploading final batch {batch_num} ({len(texts)} chunks)...")
            try:
                vectorstore.add_texts(texts=texts, metadatas=metadatas)
                self.uploaded_count += len(texts)
            except Exception as e:
                logger.error(f"Final batch failed: {e}")

        logger.info("=" * 60)
        logger.info(f"Upload complete!")
        logger.info(f"Total chunks uploaded: {self.uploaded_count}")
        logger.info("=" * 60)

    def verify_upload(self):
        """Verify uploaded content with test queries."""
        logger.info("\nVerifying upload with test queries...")

        self._setup_django()
        vectorstore = self._get_vectorstore()

        test_queries = [
            "What are the requirements for underground coal mine ventilation?",
            "What PPE is required in mining operations?",
            "What are the training requirements for new miners?",
        ]

        for query in test_queries:
            logger.info(f"\nQuery: {query}")
            results = vectorstore.similarity_search(query, k=2)
            for i, doc in enumerate(results, 1):
                logger.info(f"  Result {i}: {doc.page_content[:100]}...")
                logger.info(f"    Source: {doc.metadata.get('source_type', 'unknown')}")


def main():
    uploader = VectorStoreUploader()
    uploader.upload_chunks()
    uploader.verify_upload()


if __name__ == "__main__":
    main()
