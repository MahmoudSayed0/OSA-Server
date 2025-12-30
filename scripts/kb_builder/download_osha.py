#!/usr/bin/env python3
"""
OSHA Content Downloader

Downloads OSHA safety materials relevant to mining:
- Safety fact sheets and guides
- Hazard alerts
- Training materials
- Industry-specific guidance
- PPE requirements
"""

import os
import re
import time
import json
import logging
import hashlib
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# Setup paths
BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
LOGS_DIR = BASE_DIR / "logs"
OSHA_DIR = DOWNLOADS_DIR / "osha"

# Create directories
DOWNLOADS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
OSHA_DIR.mkdir(exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "osha_download.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("osha_downloader")

# OSHA content sources
OSHA_SOURCES = {
    "base_url": "https://www.osha.gov",

    # Direct PDF publication links
    "publications": [
        # Safety and Health Topics
        "/publications/OSHA3071.pdf",  # Job Hazard Analysis
        "/publications/OSHA3990.pdf",  # Recommended Practices for Safety & Health Programs
        "/publications/OSHA3885.pdf",  # Worker Safety Series - Construction
        "/publications/OSHA3170.pdf",  # PPE Guide
        "/publications/OSHA3079.pdf",  # Respiratory Protection
        "/publications/OSHA3138.pdf",  # Hand and Power Tools
        "/publications/OSHA3075.pdf",  # Hearing Conservation
        "/publications/OSHA3084.pdf",  # Excavation Hazards
        "/publications/OSHA3146.pdf",  # Fall Protection
        "/publications/OSHA3177.pdf",  # Lockout/Tagout
        "/publications/OSHA3120.pdf",  # Control of Hazardous Energy
        "/publications/OSHA3151.pdf",  # Confined Spaces
        "/publications/OSHA3173.pdf",  # Fire Safety
        "/publications/OSHA3080.pdf",  # Hazard Communication
        "/publications/OSHA3493.pdf",  # Recommended Practices for Anti-Retaliation
        "/publications/OSHA3439.pdf",  # Hazard Identification
        "/publications/OSHA3992.pdf",  # Silica Safety
    ],

    # Topic pages to scrape
    "topic_pages": [
        "/safety-management",
        "/personal-protective-equipment",
        "/respiratory-protection",
        "/fall-protection",
        "/confined-spaces",
        "/hazard-communication",
        "/electrical",
        "/machine-guarding",
        "/ergonomics",
        "/heat",
        "/noise",
        "/silica-crystalline",
    ],
}


class OSHADownloader:
    """Downloads OSHA safety content."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Mining Safety KB Builder/1.0"
        })
        self.downloaded = []
        self.metadata = []

    def download_pdf(self, url: str, subdir: str = "") -> bool:
        """Download a PDF file."""
        try:
            logger.info(f"Downloading: {url}")

            response = self.session.get(url, timeout=60)
            response.raise_for_status()

            # Get filename from URL
            filename = url.split("/")[-1]

            # Create subdirectory
            save_dir = OSHA_DIR / subdir if subdir else OSHA_DIR
            save_dir.mkdir(parents=True, exist_ok=True)

            filepath = save_dir / filename

            with open(filepath, "wb") as f:
                f.write(response.content)

            size_kb = len(response.content) / 1024
            logger.info(f"  ✓ Saved: {filename} ({size_kb:.1f} KB)")

            self.downloaded.append(str(filepath))
            self.metadata.append({
                "url": url,
                "filepath": str(filepath),
                "size_bytes": len(response.content),
                "category": subdir or "general",
                "downloaded_at": datetime.now().isoformat(),
            })

            time.sleep(0.5)  # Rate limiting
            return True

        except Exception as e:
            logger.error(f"  ✗ Failed: {e}")
            return False

    def download_publications(self):
        """Download OSHA publication PDFs."""
        logger.info("=" * 60)
        logger.info("Downloading OSHA Publications (PDFs)")
        logger.info("=" * 60)

        for path in OSHA_SOURCES["publications"]:
            url = urljoin(OSHA_SOURCES["base_url"], path)
            self.download_pdf(url, "publications")

    def scrape_topic_page(self, path: str):
        """Scrape a topic page for content and PDF links."""
        url = urljoin(OSHA_SOURCES["base_url"], path)
        topic_name = path.strip("/").replace("-", "_")

        logger.info(f"\nScraping topic: {path}")

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Extract main content
            main_content = soup.find("main") or soup.find("article") or soup.find("div", class_="content")

            if main_content:
                # Remove script/style elements
                for element in main_content(["script", "style", "nav", "footer"]):
                    element.decompose()

                text = main_content.get_text(separator="\n", strip=True)

                # Clean up text
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                text = "\n".join(lines)

                if len(text) > 500:
                    # Save as text file
                    save_dir = OSHA_DIR / "topics"
                    save_dir.mkdir(exist_ok=True)

                    filepath = save_dir / f"{topic_name}.txt"
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"Source: {url}\n")
                        f.write(f"Topic: {topic_name}\n")
                        f.write(f"Downloaded: {datetime.now().isoformat()}\n")
                        f.write("=" * 50 + "\n\n")
                        f.write(text)

                    logger.info(f"  ✓ Saved topic content: {filepath.name}")
                    self.downloaded.append(str(filepath))

            # Find PDF links on the page
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if ".pdf" in href.lower():
                    pdf_url = urljoin(url, href)
                    if "osha.gov" in pdf_url:
                        self.download_pdf(pdf_url, f"topics/{topic_name}")

            time.sleep(1)  # Rate limiting

        except Exception as e:
            logger.error(f"  ✗ Failed to scrape {path}: {e}")

    def download_quick_cards(self):
        """Download OSHA QuickCards (safety pocket guides)."""
        logger.info("\n" + "=" * 60)
        logger.info("Downloading OSHA QuickCards")
        logger.info("=" * 60)

        # QuickCards are numbered OSHA 34xx series
        quickcard_numbers = [
            "3469", "3470", "3471", "3472", "3473", "3474", "3475",
            "3476", "3477", "3478", "3479", "3480", "3481", "3482",
        ]

        for num in quickcard_numbers:
            url = f"https://www.osha.gov/sites/default/files/publications/OSHA{num}.pdf"
            self.download_pdf(url, "quickcards")

    def run(self):
        """Run all downloads."""
        logger.info("=" * 60)
        logger.info("OSHA CONTENT DOWNLOADER")
        logger.info("=" * 60)

        start_time = datetime.now()

        # Download publications
        self.download_publications()

        # Download QuickCards
        self.download_quick_cards()

        # Scrape topic pages
        logger.info("\n" + "=" * 60)
        logger.info("Scraping OSHA Topic Pages")
        logger.info("=" * 60)

        for path in OSHA_SOURCES["topic_pages"]:
            self.scrape_topic_page(path)

        # Save metadata
        with open(OSHA_DIR / "metadata.json", "w") as f:
            json.dump(self.metadata, f, indent=2)

        elapsed = datetime.now() - start_time

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("OSHA DOWNLOAD SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Files downloaded: {len(self.downloaded)}")

        # Count by type
        pdf_count = sum(1 for f in self.downloaded if f.endswith(".pdf"))
        txt_count = sum(1 for f in self.downloaded if f.endswith(".txt"))
        logger.info(f"  - PDFs: {pdf_count}")
        logger.info(f"  - Text files: {txt_count}")

        # Total size
        total_size = sum(
            Path(f).stat().st_size for f in self.downloaded if Path(f).exists()
        )
        logger.info(f"Total size: {total_size / 1024 / 1024:.1f} MB")
        logger.info(f"Time elapsed: {elapsed}")

        return self.downloaded


if __name__ == "__main__":
    downloader = OSHADownloader()
    downloader.run()
