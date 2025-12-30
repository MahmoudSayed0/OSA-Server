#!/usr/bin/env python3
"""
Standalone Vector Store Uploader

Uploads chunks directly to PostgreSQL/pgvector without Django.
Can connect to local or remote database.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime

# Setup paths
BASE_DIR = Path(__file__).parent
PROCESSED_DIR = BASE_DIR / "processed"
LOGS_DIR = BASE_DIR / "logs"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "upload.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("uploader")


def upload_to_vectorstore(
    chunks_file: Path,
    connection_string: str,
    collection_name: str = "foundation_knowledge_base",
    batch_size: int = 100,
):
    """Upload chunks to PGVector database."""

    from langchain_postgres import PGVector
    from langchain_openai import OpenAIEmbeddings

    logger.info("=" * 60)
    logger.info("VECTOR STORE UPLOADER")
    logger.info(f"Collection: {collection_name}")
    logger.info(f"Chunks file: {chunks_file}")
    logger.info("=" * 60)

    # Initialize embeddings
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    # Connect to vector store
    logger.info("Connecting to database...")
    vectorstore = PGVector(
        connection=connection_string,
        collection_name=collection_name,
        embeddings=embeddings,
    )

    # Count total chunks
    total_chunks = sum(1 for _ in open(chunks_file))
    logger.info(f"Total chunks to upload: {total_chunks:,}")

    # Upload in batches
    texts = []
    metadatas = []
    uploaded_count = 0
    batch_num = 0
    start_time = datetime.now()

    with open(chunks_file, "r") as f:
        for line_num, line in enumerate(f, 1):
            try:
                chunk = json.loads(line)

                texts.append(chunk["content"])
                metadatas.append({
                    "source": chunk.get("source", ""),
                    "source_type": chunk.get("source_type", ""),
                    "category": chunk.get("category", ""),
                    "title": chunk.get("title", ""),
                    "chunk_index": chunk.get("chunk_index", 0),
                    "total_chunks": chunk.get("total_chunks", 0),
                    "word_count": chunk.get("word_count", 0),
                    "content_hash": chunk.get("content_hash", ""),
                })

                # Upload batch
                if len(texts) >= batch_size:
                    batch_num += 1
                    progress = (line_num / total_chunks) * 100
                    logger.info(f"Uploading batch {batch_num} ({progress:.1f}% - {line_num:,}/{total_chunks:,})...")

                    try:
                        vectorstore.add_texts(texts=texts, metadatas=metadatas)
                        uploaded_count += len(texts)
                    except Exception as e:
                        logger.error(f"Batch {batch_num} failed: {e}")

                    texts = []
                    metadatas = []

            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON at line {line_num}: {e}")
                continue

    # Upload remaining
    if texts:
        batch_num += 1
        logger.info(f"Uploading final batch {batch_num} ({len(texts)} chunks)...")
        try:
            vectorstore.add_texts(texts=texts, metadatas=metadatas)
            uploaded_count += len(texts)
        except Exception as e:
            logger.error(f"Final batch failed: {e}")

    elapsed = datetime.now() - start_time

    logger.info("=" * 60)
    logger.info("UPLOAD COMPLETE")
    logger.info(f"Chunks uploaded: {uploaded_count:,}")
    logger.info(f"Time elapsed: {elapsed}")
    logger.info("=" * 60)

    return uploaded_count


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Upload chunks to vector store")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL connection string"
    )
    parser.add_argument(
        "--collection",
        default="foundation_knowledge_base",
        help="Collection name"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for uploads"
    )
    args = parser.parse_args()

    if not args.db_url:
        logger.error("DATABASE_URL not set. Use --db-url or set DATABASE_URL environment variable.")
        logger.info("Example: postgresql://user:pass@host:5432/dbname")
        return

    chunks_file = PROCESSED_DIR / "chunks.jsonl"
    if not chunks_file.exists():
        logger.error(f"Chunks file not found: {chunks_file}")
        return

    upload_to_vectorstore(
        chunks_file=chunks_file,
        connection_string=args.db_url,
        collection_name=args.collection,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
