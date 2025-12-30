"""
MSHA (Mine Safety and Health Administration) Content Downloader

Downloads:
- 30 CFR regulations (mine safety federal regulations)
- Policy and Program Information Bulletins (PIBs)
- Procedure Instruction Letters (PILs)
- Training materials
- Fatality reports and statistics
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
from config import (
    MSHA_SOURCES,
    DOWNLOADS_DIR,
    LOGS_DIR,
    REQUEST_CONFIG,
    LOGGING_CONFIG,
)

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG["level"]),
    format=LOGGING_CONFIG["format"],
    handlers=[
        logging.FileHandler(LOGS_DIR / "msha_download.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("msha_downloader")

# Create MSHA-specific download directory
MSHA_DIR = DOWNLOADS_DIR / "msha"
MSHA_DIR.mkdir(exist_ok=True)


class MSHADownloader:
    """Downloads content from MSHA website."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": REQUEST_CONFIG["user_agent"]})
        self.downloaded_urls = set()
        self.metadata = []
        self.base_url = MSHA_SOURCES["base_url"]

        # Load previously downloaded URLs
        self.history_file = MSHA_DIR / "download_history.json"
        self._load_history()

    def _load_history(self):
        """Load download history to avoid re-downloading."""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    self.downloaded_urls = set(data.get("urls", []))
                    logger.info(f"Loaded {len(self.downloaded_urls)} previously downloaded URLs")
            except Exception as e:
                logger.warning(f"Could not load history: {e}")

    def _save_history(self):
        """Save download history."""
        with open(self.history_file, "w") as f:
            json.dump({"urls": list(self.downloaded_urls)}, f)

    def _save_metadata(self):
        """Save metadata about downloaded files."""
        metadata_file = MSHA_DIR / "metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(self.metadata, f, indent=2, default=str)

    def _get_safe_filename(self, url: str, title: str = None) -> str:
        """Generate a safe filename from URL or title."""
        if title:
            # Clean title for filename
            safe_name = re.sub(r'[^\w\s-]', '', title)
            safe_name = re.sub(r'\s+', '_', safe_name)[:100]
        else:
            # Use URL path
            parsed = urlparse(url)
            safe_name = parsed.path.replace("/", "_").strip("_")

        # Add hash for uniqueness
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"{safe_name}_{url_hash}"

    def _fetch_page(self, url: str, retries: int = None) -> requests.Response:
        """Fetch a page with retry logic."""
        retries = retries or REQUEST_CONFIG["retry_attempts"]

        for attempt in range(retries):
            try:
                response = self.session.get(
                    url,
                    timeout=REQUEST_CONFIG["timeout"],
                    allow_redirects=True,
                )
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{retries} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(REQUEST_CONFIG["retry_delay"])

        logger.error(f"Failed to fetch {url} after {retries} attempts")
        return None

    def _download_file(self, url: str, subdir: str = "") -> dict:
        """Download a file (PDF, DOC, etc.) and return metadata."""
        if url in self.downloaded_urls:
            logger.debug(f"Skipping already downloaded: {url}")
            return None

        response = self._fetch_page(url)
        if not response:
            return None

        # Determine file extension
        content_type = response.headers.get("Content-Type", "")
        if "pdf" in content_type:
            ext = ".pdf"
        elif "msword" in content_type or "wordprocessingml" in content_type:
            ext = ".docx"
        elif "html" in content_type:
            ext = ".html"
        else:
            # Try to get from URL
            parsed = urlparse(url)
            ext = Path(parsed.path).suffix or ".bin"

        # Create subdirectory
        save_dir = MSHA_DIR / subdir if subdir else MSHA_DIR
        save_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        filename = self._get_safe_filename(url) + ext
        filepath = save_dir / filename

        # Save file
        with open(filepath, "wb") as f:
            f.write(response.content)

        self.downloaded_urls.add(url)
        logger.info(f"Downloaded: {filepath.name} ({len(response.content)} bytes)")

        metadata = {
            "url": url,
            "filepath": str(filepath),
            "filename": filename,
            "size_bytes": len(response.content),
            "content_type": content_type,
            "downloaded_at": datetime.now().isoformat(),
            "category": subdir or "general",
        }
        self.metadata.append(metadata)

        # Rate limiting
        time.sleep(REQUEST_CONFIG["rate_limit_delay"])

        return metadata

    def _extract_links(self, html: str, base_url: str, pattern: str = None) -> list:
        """Extract links from HTML content."""
        soup = BeautifulSoup(html, "html.parser")
        links = []

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            full_url = urljoin(base_url, href)

            # Filter by pattern if provided
            if pattern and not re.search(pattern, full_url, re.IGNORECASE):
                continue

            # Only include MSHA domain links or direct file downloads
            if self.base_url in full_url or any(
                ext in full_url.lower() for ext in [".pdf", ".doc", ".docx"]
            ):
                links.append({"url": full_url, "text": a.get_text(strip=True)})

        return links

    def download_regulations(self):
        """Download 30 CFR mining regulations."""
        logger.info("=" * 50)
        logger.info("Downloading MSHA Regulations (30 CFR)")
        logger.info("=" * 50)

        for path in MSHA_SOURCES["regulations"]:
            url = urljoin(self.base_url, path)
            logger.info(f"Processing: {url}")

            response = self._fetch_page(url)
            if not response:
                continue

            # Save the main page
            self._save_html_content(response.text, url, "regulations")

            # Find PDF links
            links = self._extract_links(response.text, url, r"\.(pdf|doc|docx)$")
            logger.info(f"Found {len(links)} document links")

            for link in links:
                self._download_file(link["url"], "regulations")

    def download_pibs_and_pils(self):
        """Download Policy Information Bulletins and Procedure Instruction Letters."""
        logger.info("=" * 50)
        logger.info("Downloading PIBs and PILs")
        logger.info("=" * 50)

        # These are critical guidance documents
        paths = [
            "/regulations/policy-and-program-information-bulletins",
            "/regulations/program-information-bulletins",
            "/regulations/procedure-instruction-letters",
        ]

        for path in paths:
            url = urljoin(self.base_url, path)
            logger.info(f"Processing: {url}")

            response = self._fetch_page(url)
            if not response:
                continue

            # Save the main page
            self._save_html_content(response.text, url, "guidance")

            # Find all document links
            links = self._extract_links(response.text, url)

            for link in links:
                if any(ext in link["url"].lower() for ext in [".pdf", ".doc"]):
                    self._download_file(link["url"], "guidance")
                elif "/pib/" in link["url"].lower() or "/pil/" in link["url"].lower():
                    # Follow link to get the actual document
                    sub_response = self._fetch_page(link["url"])
                    if sub_response:
                        sub_links = self._extract_links(sub_response.text, link["url"], r"\.pdf$")
                        for sub_link in sub_links:
                            self._download_file(sub_link["url"], "guidance")

    def download_training_materials(self):
        """Download training materials and educational content."""
        logger.info("=" * 50)
        logger.info("Downloading Training Materials")
        logger.info("=" * 50)

        for path in MSHA_SOURCES["training"]:
            url = urljoin(self.base_url, path)
            logger.info(f"Processing: {url}")

            response = self._fetch_page(url)
            if not response:
                continue

            self._save_html_content(response.text, url, "training")

            # Get all PDF/document links
            links = self._extract_links(response.text, url, r"\.(pdf|doc|docx|ppt|pptx)$")
            logger.info(f"Found {len(links)} training documents")

            for link in links:
                self._download_file(link["url"], "training")

    def download_fatality_reports(self):
        """Download fatality reports - critical safety information."""
        logger.info("=" * 50)
        logger.info("Downloading Fatality Reports")
        logger.info("=" * 50)

        # Fatality reports page
        url = urljoin(self.base_url, "/data-and-reports/fatality-reports")
        response = self._fetch_page(url)

        if response:
            self._save_html_content(response.text, url, "fatality_reports")

            # These are typically PDFs with detailed incident analysis
            links = self._extract_links(response.text, url, r"\.pdf$")
            logger.info(f"Found {len(links)} fatality report PDFs")

            for link in links:
                self._download_file(link["url"], "fatality_reports")

    def download_compliance_assistance(self):
        """Download compliance assistance materials."""
        logger.info("=" * 50)
        logger.info("Downloading Compliance Assistance")
        logger.info("=" * 50)

        for path in MSHA_SOURCES["guidance"]:
            url = urljoin(self.base_url, path)
            logger.info(f"Processing: {url}")

            response = self._fetch_page(url)
            if not response:
                continue

            self._save_html_content(response.text, url, "compliance")

            links = self._extract_links(response.text, url, r"\.(pdf|doc|docx)$")
            for link in links:
                self._download_file(link["url"], "compliance")

    def _save_html_content(self, html: str, url: str, subdir: str):
        """Save HTML content with extracted text."""
        save_dir = MSHA_DIR / subdir
        save_dir.mkdir(parents=True, exist_ok=True)

        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Get main content
        main_content = soup.find("main") or soup.find("article") or soup.find("body")
        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Clean up text
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        if len(text) > 500:  # Only save if meaningful content
            filename = self._get_safe_filename(url) + ".txt"
            filepath = save_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"Source: {url}\n")
                f.write(f"Downloaded: {datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                f.write(text)

            self.metadata.append({
                "url": url,
                "filepath": str(filepath),
                "filename": filename,
                "size_bytes": len(text),
                "content_type": "text/plain",
                "downloaded_at": datetime.now().isoformat(),
                "category": subdir,
            })

            logger.info(f"Saved HTML content: {filename}")

    def run(self):
        """Run all downloads."""
        logger.info("Starting MSHA content download")
        start_time = datetime.now()

        try:
            self.download_regulations()
            self.download_pibs_and_pils()
            self.download_training_materials()
            self.download_fatality_reports()
            self.download_compliance_assistance()

        except KeyboardInterrupt:
            logger.info("Download interrupted by user")
        except Exception as e:
            logger.error(f"Download error: {e}")
        finally:
            # Save progress
            self._save_history()
            self._save_metadata()

            elapsed = datetime.now() - start_time
            logger.info("=" * 50)
            logger.info(f"MSHA Download Complete")
            logger.info(f"Total files downloaded: {len(self.metadata)}")
            logger.info(f"Time elapsed: {elapsed}")
            logger.info("=" * 50)


if __name__ == "__main__":
    downloader = MSHADownloader()
    downloader.run()
