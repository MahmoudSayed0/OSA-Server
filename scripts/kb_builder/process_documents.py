"""
Document Processing Pipeline

Processes downloaded content into chunks suitable for the vector database:
1. Extract text from PDFs
2. Clean and normalize text
3. Split into chunks with metadata
4. Export in format ready for vector store upload
"""

import os
import re
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Generator
from dataclasses import dataclass, asdict

from config import (
    DOWNLOADS_DIR,
    PROCESSED_DIR,
    LOGS_DIR,
    PROCESSING_CONFIG,
    LOGGING_CONFIG,
)

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG["level"]),
    format=LOGGING_CONFIG["format"],
    handlers=[
        logging.FileHandler(LOGS_DIR / "processing.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("document_processor")


@dataclass
class DocumentChunk:
    """A chunk of text with metadata for the vector store."""
    content: str
    source: str
    source_type: str  # msha, osha, ecfr, niosh
    category: str  # regulations, training, guidance, fatality_reports
    title: str
    chunk_index: int
    total_chunks: int
    word_count: int
    char_count: int
    content_hash: str
    processed_at: str


class PDFExtractor:
    """Extract text from PDF files."""

    def __init__(self):
        self.extractors = []
        self._init_extractors()

    def _init_extractors(self):
        """Initialize available PDF extractors in order of preference."""
        # Try PyMuPDF (fitz) first - fastest and most accurate
        try:
            import fitz
            self.extractors.append(("pymupdf", self._extract_pymupdf))
            logger.info("PDF extractor: PyMuPDF available")
        except ImportError:
            pass

        # Try pdfplumber - good for tables
        try:
            import pdfplumber
            self.extractors.append(("pdfplumber", self._extract_pdfplumber))
            logger.info("PDF extractor: pdfplumber available")
        except ImportError:
            pass

        # Try PyPDF2 as fallback
        try:
            import PyPDF2
            self.extractors.append(("pypdf2", self._extract_pypdf2))
            logger.info("PDF extractor: PyPDF2 available")
        except ImportError:
            pass

        if not self.extractors:
            logger.warning("No PDF extractors available! Install: pip install PyMuPDF pdfplumber PyPDF2")

    def _extract_pymupdf(self, filepath: Path) -> str:
        """Extract using PyMuPDF (fitz)."""
        import fitz
        text_parts = []
        with fitz.open(filepath) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        return "\n\n".join(text_parts)

    def _extract_pdfplumber(self, filepath: Path) -> str:
        """Extract using pdfplumber."""
        import pdfplumber
        text_parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n\n".join(text_parts)

    def _extract_pypdf2(self, filepath: Path) -> str:
        """Extract using PyPDF2."""
        import PyPDF2
        text_parts = []
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n\n".join(text_parts)

    def extract(self, filepath: Path) -> str:
        """Extract text from PDF using available extractor."""
        for name, extractor in self.extractors:
            try:
                text = extractor(filepath)
                if text and len(text.strip()) > 100:
                    return text
            except Exception as e:
                logger.warning(f"{name} failed for {filepath.name}: {e}")
                continue

        logger.error(f"All extractors failed for {filepath.name}")
        return ""


class TextCleaner:
    """Clean and normalize extracted text."""

    @staticmethod
    def clean(text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        # Remove page numbers and headers/footers patterns
        text = re.sub(r'\n\d+\n', '\n', text)
        text = re.sub(r'Page \d+ of \d+', '', text, flags=re.IGNORECASE)

        # Remove common PDF artifacts
        text = re.sub(r'\x00', '', text)  # null bytes
        text = re.sub(r'[\x80-\x9f]', '', text)  # control characters

        # Fix common OCR issues
        text = text.replace('ﬁ', 'fi')
        text = text.replace('ﬂ', 'fl')
        text = text.replace('ﬀ', 'ff')

        # Normalize quotes
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")

        # Clean up lines
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line:
                lines.append(line)

        return '\n'.join(lines)


class TextChunker:
    """Split text into chunks for vector storage."""

    def __init__(
        self,
        chunk_size: int = PROCESSING_CONFIG["chunk_size"],
        chunk_overlap: int = PROCESSING_CONFIG["chunk_overlap"],
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        if not text:
            return []

        # Try to split on paragraph boundaries first
        paragraphs = text.split('\n\n')

        chunks = []
        current_chunk = ""

        for para in paragraphs:
            # If paragraph alone is larger than chunk size, split it
            if len(para) > self.chunk_size:
                # Save current chunk if exists
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""

                # Split large paragraph by sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) > self.chunk_size:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        current_chunk += " " + sentence if current_chunk else sentence

            # If adding paragraph exceeds chunk size, start new chunk
            elif len(current_chunk) + len(para) + 2 > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # Include overlap from previous chunk
                overlap_text = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else ""
                current_chunk = overlap_text + "\n\n" + para if overlap_text else para
            else:
                current_chunk += "\n\n" + para if current_chunk else para

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk.strip())

        # Filter out tiny chunks
        chunks = [c for c in chunks if len(c) >= 100]

        return chunks


class DocumentProcessor:
    """Main document processing pipeline."""

    def __init__(self):
        self.pdf_extractor = PDFExtractor()
        self.cleaner = TextCleaner()
        self.chunker = TextChunker()
        self.processed_count = 0
        self.total_chunks = 0

    def _get_source_info(self, filepath: Path) -> Dict:
        """Determine source type and category from file path."""
        path_str = str(filepath).lower()

        # Determine source
        if "msha" in path_str:
            source_type = "msha"
        elif "osha" in path_str:
            source_type = "osha"
        elif "ecfr" in path_str:
            source_type = "ecfr"
        elif "niosh" in path_str:
            source_type = "niosh"
        else:
            source_type = "other"

        # Determine category
        if "regulation" in path_str or "cfr" in path_str:
            category = "regulations"
        elif "training" in path_str:
            category = "training"
        elif "guidance" in path_str or "pib" in path_str or "pil" in path_str:
            category = "guidance"
        elif "fatality" in path_str or "accident" in path_str:
            category = "incident_reports"
        elif "compliance" in path_str:
            category = "compliance"
        else:
            category = "general"

        return {"source_type": source_type, "category": category}

    def process_file(self, filepath: Path) -> Generator[DocumentChunk, None, None]:
        """Process a single file into chunks."""
        logger.info(f"Processing: {filepath.name}")

        # Get source info
        source_info = self._get_source_info(filepath)

        # Extract text based on file type
        suffix = filepath.suffix.lower()

        if suffix == ".pdf":
            text = self.pdf_extractor.extract(filepath)
        elif suffix in [".txt", ".md"]:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif suffix in [".html", ".htm"]:
            from bs4 import BeautifulSoup
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
                text = soup.get_text(separator="\n", strip=True)
        else:
            logger.warning(f"Unsupported file type: {suffix}")
            return

        if not text or len(text) < 100:
            logger.warning(f"No usable text extracted from {filepath.name}")
            return

        # Clean text
        text = self.cleaner.clean(text)

        # Chunk text
        chunks = self.chunker.chunk(text)

        if not chunks:
            logger.warning(f"No chunks generated from {filepath.name}")
            return

        logger.info(f"  Generated {len(chunks)} chunks")

        # Generate chunk objects
        for i, chunk_text in enumerate(chunks):
            content_hash = hashlib.md5(chunk_text.encode()).hexdigest()

            yield DocumentChunk(
                content=chunk_text,
                source=str(filepath),
                source_type=source_info["source_type"],
                category=source_info["category"],
                title=filepath.stem,
                chunk_index=i,
                total_chunks=len(chunks),
                word_count=len(chunk_text.split()),
                char_count=len(chunk_text),
                content_hash=content_hash,
                processed_at=datetime.now().isoformat(),
            )

        self.processed_count += 1
        self.total_chunks += len(chunks)

    def process_directory(self, directory: Path) -> Generator[DocumentChunk, None, None]:
        """Process all documents in a directory."""
        supported_extensions = PROCESSING_CONFIG["supported_extensions"]

        for filepath in directory.rglob("*"):
            if filepath.is_file() and filepath.suffix.lower() in supported_extensions:
                try:
                    yield from self.process_file(filepath)
                except Exception as e:
                    logger.error(f"Error processing {filepath}: {e}")

    def export_for_vectorstore(self, output_file: Path = None):
        """Export all processed chunks to JSON for vector store upload."""
        output_file = output_file or (PROCESSED_DIR / "chunks.jsonl")

        logger.info("=" * 60)
        logger.info("Processing all downloaded documents")
        logger.info("=" * 60)

        with open(output_file, "w") as f:
            for chunk in self.process_directory(DOWNLOADS_DIR):
                # Write as JSON Lines format
                f.write(json.dumps(asdict(chunk)) + "\n")

        logger.info("=" * 60)
        logger.info(f"Processing complete!")
        logger.info(f"Documents processed: {self.processed_count}")
        logger.info(f"Total chunks generated: {self.total_chunks}")
        logger.info(f"Output file: {output_file}")
        logger.info("=" * 60)

        return output_file


def main():
    """Process all downloaded documents."""
    processor = DocumentProcessor()
    processor.export_for_vectorstore()


if __name__ == "__main__":
    main()
