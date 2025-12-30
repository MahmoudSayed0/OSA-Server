"""
eCFR (Electronic Code of Federal Regulations) Downloader

Downloads Title 30 (Mineral Resources) - The primary mining safety regulations.
Uses the official eCFR API for structured data access.

Title 30 Structure:
- Chapter I: Mine Safety and Health Administration (Parts 1-199)
- Chapter II: Bureau of Safety and Environmental Enforcement (Parts 200-299)
- Chapter IV: Geological Survey (Parts 400-499)
- Chapter V: Bureau of Ocean Energy Management (Parts 500-599)
- Chapter VII: Office of Surface Mining Reclamation and Enforcement (Parts 700-999)
"""

import os
import re
import time
import json
import logging
import requests
from pathlib import Path
from datetime import datetime
from config import (
    ECFR_SOURCES,
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
        logging.FileHandler(LOGS_DIR / "ecfr_download.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ecfr_downloader")

# Create eCFR-specific download directory
ECFR_DIR = DOWNLOADS_DIR / "ecfr"
ECFR_DIR.mkdir(exist_ok=True)


class ECFRDownloader:
    """Downloads federal regulations from eCFR API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": REQUEST_CONFIG["user_agent"],
            "Accept": "application/json",
        })
        self.api_base = ECFR_SOURCES["api_base"]
        self.metadata = []

    def _fetch_json(self, url: str) -> dict:
        """Fetch JSON from API endpoint."""
        try:
            response = self.session.get(url, timeout=REQUEST_CONFIG["timeout"])
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"API request failed: {url} - {e}")
            return None

    def _fetch_xml(self, url: str) -> str:
        """Fetch XML content from API."""
        try:
            headers = {"Accept": "application/xml"}
            response = self.session.get(url, timeout=REQUEST_CONFIG["timeout"], headers=headers)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"XML request failed: {url} - {e}")
            return None

    def get_title_structure(self, title: int) -> dict:
        """Get the structure of a CFR title (chapters, parts, sections)."""
        url = f"{self.api_base}/structure/{datetime.now().strftime('%Y-%m-%d')}/title-{title}.json"
        logger.info(f"Fetching Title {title} structure...")
        return self._fetch_json(url)

    def get_part_content(self, title: int, part: int) -> str:
        """Get the full text content of a CFR part."""
        date = datetime.now().strftime("%Y-%m-%d")
        url = f"{self.api_base}/full/{date}/title-{title}/part-{part}.xml"
        return self._fetch_xml(url)

    def download_title_30(self):
        """Download Title 30 - Mineral Resources (primary mining regulations)."""
        logger.info("=" * 60)
        logger.info("Downloading Title 30 - Mineral Resources")
        logger.info("=" * 60)

        title_dir = ECFR_DIR / "title_30"
        title_dir.mkdir(exist_ok=True)

        # Get title structure
        structure = self.get_title_structure(30)
        if not structure:
            logger.error("Could not fetch Title 30 structure")
            return

        # Save structure
        with open(title_dir / "structure.json", "w") as f:
            json.dump(structure, f, indent=2)

        # Key parts for mining safety (30 CFR)
        # Part 1-199: MSHA regulations
        key_mining_parts = [
            # Part 1-2: General
            (1, "Definitions and General Provisions"),
            (2, "Publication Fees and Charges"),

            # Part 40-49: Training
            (46, "Training and Retraining of Miners"),
            (48, "Training and Retraining of Miners"),

            # Part 50-57: Safety Standards
            (50, "Notification, Investigation, Reports and Records"),
            (56, "Safety and Health Standards - Surface Metal and Nonmetal Mines"),
            (57, "Safety and Health Standards - Underground Metal and Nonmetal Mines"),

            # Part 62-75: Health and Coal Mining
            (62, "Occupational Noise Exposure"),
            (70, "Mandatory Health Standards - Underground Coal Mines"),
            (71, "Mandatory Health Standards - Surface Coal Mines"),
            (72, "Health Standards for Coal Mines"),
            (74, "Coal Mine Dust Sampling Devices"),
            (75, "Mandatory Safety Standards - Underground Coal Mines"),

            # Part 77: Surface Coal
            (77, "Mandatory Safety Standards - Surface Coal Mines"),

            # Part 100: Penalties
            (100, "Criteria and Procedures for Civil Penalties"),

            # Part 104: Citations
            (104, "Pattern of Violations"),
        ]

        for part_num, part_name in key_mining_parts:
            logger.info(f"Downloading Part {part_num}: {part_name}")

            part_dir = title_dir / f"part_{part_num}"
            part_dir.mkdir(exist_ok=True)

            # Get XML content
            xml_content = self.get_part_content(30, part_num)
            if xml_content:
                # Save XML
                xml_file = part_dir / f"part_{part_num}.xml"
                with open(xml_file, "w", encoding="utf-8") as f:
                    f.write(xml_content)

                # Convert to plain text for easier processing
                text_content = self._xml_to_text(xml_content)
                text_file = part_dir / f"part_{part_num}.txt"
                with open(text_file, "w", encoding="utf-8") as f:
                    f.write(f"30 CFR Part {part_num}: {part_name}\n")
                    f.write(f"Source: eCFR (Electronic Code of Federal Regulations)\n")
                    f.write(f"Downloaded: {datetime.now().isoformat()}\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(text_content)

                self.metadata.append({
                    "title": 30,
                    "part": part_num,
                    "name": part_name,
                    "xml_file": str(xml_file),
                    "text_file": str(text_file),
                    "downloaded_at": datetime.now().isoformat(),
                })

                logger.info(f"  Saved Part {part_num} ({len(text_content)} chars)")

            time.sleep(REQUEST_CONFIG["rate_limit_delay"])

    def download_title_29_osha(self):
        """Download relevant OSHA regulations from Title 29."""
        logger.info("=" * 60)
        logger.info("Downloading Title 29 - Labor (OSHA)")
        logger.info("=" * 60)

        title_dir = ECFR_DIR / "title_29"
        title_dir.mkdir(exist_ok=True)

        # Key OSHA parts relevant to mining
        osha_parts = [
            (1910, "Occupational Safety and Health Standards"),
            (1926, "Safety and Health Regulations for Construction"),
        ]

        for part_num, part_name in osha_parts:
            logger.info(f"Downloading Part {part_num}: {part_name}")

            part_dir = title_dir / f"part_{part_num}"
            part_dir.mkdir(exist_ok=True)

            xml_content = self.get_part_content(29, part_num)
            if xml_content:
                xml_file = part_dir / f"part_{part_num}.xml"
                with open(xml_file, "w", encoding="utf-8") as f:
                    f.write(xml_content)

                text_content = self._xml_to_text(xml_content)
                text_file = part_dir / f"part_{part_num}.txt"
                with open(text_file, "w", encoding="utf-8") as f:
                    f.write(f"29 CFR Part {part_num}: {part_name}\n")
                    f.write(f"Source: eCFR (OSHA Regulations)\n")
                    f.write(f"Downloaded: {datetime.now().isoformat()}\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(text_content)

                self.metadata.append({
                    "title": 29,
                    "part": part_num,
                    "name": part_name,
                    "xml_file": str(xml_file),
                    "text_file": str(text_file),
                    "downloaded_at": datetime.now().isoformat(),
                })

                logger.info(f"  Saved Part {part_num} ({len(text_content)} chars)")

            time.sleep(REQUEST_CONFIG["rate_limit_delay"])

    def _xml_to_text(self, xml_content: str) -> str:
        """Convert XML regulation content to readable text."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(xml_content, "xml")

        # Extract structured text
        lines = []

        # Get all sections
        for section in soup.find_all(["DIV5", "DIV6", "DIV8", "SECTION", "P"]):
            # Get section number and heading
            head = section.find("HEAD")
            if head:
                lines.append("\n" + "=" * 40)
                lines.append(head.get_text(strip=True))
                lines.append("=" * 40)

            # Get paragraph content
            for p in section.find_all("P", recursive=False):
                text = p.get_text(separator=" ", strip=True)
                if text:
                    lines.append(text)

            # Get auth/source notes
            auth = section.find("AUTH")
            if auth:
                lines.append(f"\n[Authority: {auth.get_text(strip=True)}]")

        if not lines:
            # Fallback: just get all text
            text = soup.get_text(separator="\n", strip=True)
            return text

        return "\n\n".join(lines)

    def _save_metadata(self):
        """Save metadata about downloaded regulations."""
        metadata_file = ECFR_DIR / "metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(self.metadata, f, indent=2)

    def run(self):
        """Run all downloads."""
        logger.info("Starting eCFR download")
        start_time = datetime.now()

        try:
            self.download_title_30()
            self.download_title_29_osha()

        except KeyboardInterrupt:
            logger.info("Download interrupted by user")
        except Exception as e:
            logger.error(f"Download error: {e}", exc_info=True)
        finally:
            self._save_metadata()

            elapsed = datetime.now() - start_time
            logger.info("=" * 60)
            logger.info("eCFR Download Complete")
            logger.info(f"Total regulations downloaded: {len(self.metadata)}")
            logger.info(f"Time elapsed: {elapsed}")
            logger.info("=" * 60)


if __name__ == "__main__":
    downloader = ECFRDownloader()
    downloader.run()
