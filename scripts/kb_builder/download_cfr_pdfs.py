#!/usr/bin/env python3
"""
CFR PDF Downloader - Downloads official Code of Federal Regulations PDFs

Downloads Title 30 (Mineral Resources) and relevant OSHA regulations (Title 29)
from GovInfo.gov - the official source for federal regulations.

These are the actual law PDFs - the authoritative source for mining safety regulations.
"""

import os
import sys
import logging
import requests
from pathlib import Path
from datetime import datetime

# Setup paths
BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
LOGS_DIR = BASE_DIR / "logs"
PDF_DIR = DOWNLOADS_DIR / "cfr_pdfs"

# Create directories
DOWNLOADS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
PDF_DIR.mkdir(exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "cfr_pdf_download.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("cfr_pdf_downloader")

# GovInfo CFR PDF URLs (2024 edition - most recent complete)
# Format: https://www.govinfo.gov/content/pkg/CFR-{year}-title{num}-vol{vol}/pdf/CFR-{year}-title{num}-vol{vol}.pdf
CFR_PDFS = {
    # Title 30 - Mineral Resources (MSHA regulations)
    "title30": {
        "name": "Mineral Resources - Mining Safety",
        "volumes": [
            ("vol1", "Parts 1-199: MSHA Regulations"),      # ~5MB - Core mining safety
            ("vol2", "Parts 200-699: Bureau of Safety"),    # Environmental & Safety
            ("vol3", "Parts 700-End: Surface Mining"),      # Surface mining rules
        ]
    },
    # Title 29 - Labor (OSHA regulations) - relevant parts
    "title29": {
        "name": "Labor - OSHA Safety Standards",
        "volumes": [
            ("vol5", "Parts 1900-1910: General Industry"),  # ~15MB - OSHA general
            ("vol8", "Parts 1926: Construction Safety"),    # ~8MB - Construction
        ]
    },
}


def download_pdf(url: str, filepath: Path) -> bool:
    """Download a PDF file with progress."""
    try:
        logger.info(f"Downloading: {filepath.name}")
        logger.info(f"  URL: {url}")

        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"  Size: {total_size / 1024 / 1024:.1f} MB")

        with open(filepath, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    # Progress update every 1MB
                    if downloaded % (1024 * 1024) < 8192:
                        pct = (downloaded / total_size * 100) if total_size else 0
                        logger.info(f"  Progress: {pct:.0f}%")

        logger.info(f"  ✓ Saved: {filepath.name}")
        return True

    except Exception as e:
        logger.error(f"  ✗ Failed: {e}")
        return False


def download_all_cfr_pdfs():
    """Download all CFR PDF volumes."""
    logger.info("=" * 60)
    logger.info("CFR PDF DOWNLOADER")
    logger.info("Downloading official mining safety regulations")
    logger.info("=" * 60)

    year = "2024"  # Most recent complete edition
    downloaded = []
    failed = []

    for title_key, title_info in CFR_PDFS.items():
        title_num = title_key.replace("title", "")
        logger.info(f"\n{'='*40}")
        logger.info(f"Title {title_num}: {title_info['name']}")
        logger.info(f"{'='*40}")

        title_dir = PDF_DIR / title_key
        title_dir.mkdir(exist_ok=True)

        for vol_id, vol_desc in title_info["volumes"]:
            pkg_name = f"CFR-{year}-{title_key}-{vol_id}"
            url = f"https://www.govinfo.gov/content/pkg/{pkg_name}/pdf/{pkg_name}.pdf"
            filepath = title_dir / f"{pkg_name}.pdf"

            logger.info(f"\n{vol_desc}")

            if filepath.exists():
                size_mb = filepath.stat().st_size / 1024 / 1024
                logger.info(f"  Already exists: {filepath.name} ({size_mb:.1f} MB)")
                downloaded.append(str(filepath))
                continue

            if download_pdf(url, filepath):
                downloaded.append(str(filepath))
            else:
                failed.append(url)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("DOWNLOAD SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Successfully downloaded: {len(downloaded)} PDFs")

    total_size = sum(Path(f).stat().st_size for f in downloaded if Path(f).exists())
    logger.info(f"Total size: {total_size / 1024 / 1024:.1f} MB")

    if failed:
        logger.warning(f"Failed downloads: {len(failed)}")
        for url in failed:
            logger.warning(f"  - {url}")

    # List downloaded files
    logger.info("\nDownloaded PDFs:")
    for f in downloaded:
        p = Path(f)
        size_mb = p.stat().st_size / 1024 / 1024 if p.exists() else 0
        logger.info(f"  - {p.name} ({size_mb:.1f} MB)")

    return downloaded


def main():
    start_time = datetime.now()
    downloaded = download_all_cfr_pdfs()
    elapsed = datetime.now() - start_time

    logger.info(f"\nCompleted in {elapsed}")
    logger.info(f"PDFs saved to: {PDF_DIR}")

    return downloaded


if __name__ == "__main__":
    main()
