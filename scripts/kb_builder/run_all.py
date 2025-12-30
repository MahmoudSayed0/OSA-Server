#!/usr/bin/env python3
"""
Knowledge Base Builder - Main Orchestrator

Runs all downloaders and processors to build the mining safety knowledge base.

Usage:
    python run_all.py              # Run everything
    python run_all.py --download   # Only download
    python run_all.py --process    # Only process
    python run_all.py --upload     # Only upload to vector store
"""

import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import LOGS_DIR, LOGGING_CONFIG

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG["level"]),
    format=LOGGING_CONFIG["format"],
    handlers=[
        logging.FileHandler(LOGS_DIR / "kb_builder.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("kb_builder")


def run_downloaders():
    """Run all content downloaders."""
    logger.info("=" * 70)
    logger.info("PHASE 1: DOWNLOADING CONTENT")
    logger.info("=" * 70)

    # MSHA website content (regulations, training, guidance)
    logger.info("\n[1/3] MSHA Website Content")
    try:
        from download_msha import MSHADownloader
        downloader = MSHADownloader()
        downloader.run()
    except Exception as e:
        logger.error(f"MSHA download failed: {e}")

    # eCFR regulations (Title 30 + OSHA)
    logger.info("\n[2/3] eCFR Federal Regulations")
    try:
        from download_ecfr import ECFRDownloader
        downloader = ECFRDownloader()
        downloader.run()
    except Exception as e:
        logger.error(f"eCFR download failed: {e}")

    # MSHA bulk data (accidents, violations, mines)
    logger.info("\n[3/3] MSHA Open Government Data")
    try:
        from download_msha_data import MSHADataDownloader
        downloader = MSHADataDownloader()
        downloader.run()
    except Exception as e:
        logger.error(f"MSHA data download failed: {e}")


def run_processing():
    """Process all downloaded content into chunks."""
    logger.info("=" * 70)
    logger.info("PHASE 2: PROCESSING DOCUMENTS")
    logger.info("=" * 70)

    try:
        from process_documents import DocumentProcessor
        processor = DocumentProcessor()
        output_file = processor.export_for_vectorstore()
        logger.info(f"Chunks exported to: {output_file}")
    except Exception as e:
        logger.error(f"Processing failed: {e}")


def run_upload():
    """Upload processed chunks to vector store."""
    logger.info("=" * 70)
    logger.info("PHASE 3: UPLOADING TO VECTOR STORE")
    logger.info("=" * 70)

    try:
        from upload_to_vectorstore import VectorStoreUploader
        uploader = VectorStoreUploader()
        uploader.upload_chunks()
    except Exception as e:
        logger.error(f"Upload failed: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Mining Safety Knowledge Base Builder"
    )
    parser.add_argument(
        "--download", action="store_true",
        help="Only run downloaders"
    )
    parser.add_argument(
        "--process", action="store_true",
        help="Only run document processor"
    )
    parser.add_argument(
        "--upload", action="store_true",
        help="Only upload to vector store"
    )
    args = parser.parse_args()

    start_time = datetime.now()

    logger.info("=" * 70)
    logger.info("MINING SAFETY KNOWLEDGE BASE BUILDER")
    logger.info(f"Started: {start_time.isoformat()}")
    logger.info("=" * 70)

    # If no specific phase requested, run everything
    run_all = not (args.download or args.process or args.upload)

    if args.download or run_all:
        run_downloaders()

    if args.process or run_all:
        run_processing()

    if args.upload or run_all:
        run_upload()

    elapsed = datetime.now() - start_time
    logger.info("=" * 70)
    logger.info("KNOWLEDGE BASE BUILD COMPLETE")
    logger.info(f"Total time: {elapsed}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
