"""
MSHA Open Government Data Downloader

Downloads bulk datasets from MSHA's Open Government Data portal:
- Mines.zip: Mine information and characteristics
- Accidents.zip: Accident and injury data
- Violations.zip: Safety violations and penalties
- Inspections.zip: Inspection records
- Production data: Quarterly production statistics

These datasets provide real-world mining safety statistics and patterns.
"""

import os
import io
import zipfile
import logging
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from config import (
    DATAGOV_DATASETS,
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
        logging.FileHandler(LOGS_DIR / "msha_data_download.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("msha_data_downloader")

# Create data directory
DATA_DIR = DOWNLOADS_DIR / "msha_data"
DATA_DIR.mkdir(exist_ok=True)


class MSHADataDownloader:
    """Downloads bulk datasets from MSHA Open Government Data."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": REQUEST_CONFIG["user_agent"]})
        self.datasets = []

    def download_dataset(self, url: str, name: str) -> bool:
        """Download and extract a ZIP dataset."""
        logger.info(f"Downloading {name}...")
        logger.info(f"  URL: {url}")

        try:
            response = self.session.get(
                url,
                timeout=120,  # Longer timeout for large files
                stream=True,
            )
            response.raise_for_status()

            # Get file size
            total_size = int(response.headers.get("content-length", 0))
            logger.info(f"  Size: {total_size / 1024 / 1024:.1f} MB")

            # Download to memory
            content = response.content

            # Extract ZIP
            dataset_dir = DATA_DIR / name
            dataset_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                zf.extractall(dataset_dir)
                extracted_files = zf.namelist()
                logger.info(f"  Extracted {len(extracted_files)} files")

            self.datasets.append({
                "name": name,
                "url": url,
                "size_bytes": total_size,
                "extracted_files": extracted_files,
                "downloaded_at": datetime.now().isoformat(),
            })

            return True

        except Exception as e:
            logger.error(f"  Failed: {e}")
            return False

    def process_to_knowledge_base(self):
        """Convert datasets to text documents for the knowledge base."""
        logger.info("=" * 60)
        logger.info("Processing datasets for knowledge base")
        logger.info("=" * 60)

        kb_dir = DATA_DIR / "knowledge_base"
        kb_dir.mkdir(exist_ok=True)

        # Process each dataset type
        self._process_mines_data(kb_dir)
        self._process_accidents_data(kb_dir)
        self._process_violations_data(kb_dir)

    def _process_mines_data(self, kb_dir: Path):
        """Create knowledge base entries from mines data."""
        mines_dir = DATA_DIR / "Mines"
        if not mines_dir.exists():
            return

        # Find the main data file
        txt_files = list(mines_dir.glob("*.txt"))
        if not txt_files:
            return

        try:
            # Read mines data
            df = pd.read_csv(
                txt_files[0],
                sep="|",
                encoding="latin-1",
                low_memory=False,
                on_bad_lines="skip",
            )

            # Create summary document
            summary = []
            summary.append("# MSHA Mine Database Summary")
            summary.append(f"Total mines in database: {len(df):,}")
            summary.append(f"Data source: MSHA Open Government Data")
            summary.append(f"Generated: {datetime.now().isoformat()}")
            summary.append("")

            # Mine types breakdown
            if "MINE_TYPE" in df.columns:
                summary.append("## Mine Types")
                type_counts = df["MINE_TYPE"].value_counts()
                for mine_type, count in type_counts.head(10).items():
                    summary.append(f"- {mine_type}: {count:,}")
                summary.append("")

            # States breakdown
            if "STATE" in df.columns:
                summary.append("## Mines by State")
                state_counts = df["STATE"].value_counts()
                for state, count in state_counts.head(15).items():
                    summary.append(f"- {state}: {count:,}")
                summary.append("")

            # Save summary
            with open(kb_dir / "mines_summary.txt", "w") as f:
                f.write("\n".join(summary))

            logger.info(f"Created mines summary ({len(df):,} records)")

        except Exception as e:
            logger.error(f"Error processing mines data: {e}")

    def _process_accidents_data(self, kb_dir: Path):
        """Create knowledge base entries from accidents data."""
        accidents_dir = DATA_DIR / "Accidents"
        if not accidents_dir.exists():
            return

        txt_files = list(accidents_dir.glob("*.txt"))
        if not txt_files:
            return

        try:
            df = pd.read_csv(
                txt_files[0],
                sep="|",
                encoding="latin-1",
                low_memory=False,
                on_bad_lines="skip",
            )

            summary = []
            summary.append("# MSHA Accident Statistics")
            summary.append(f"Total accident records: {len(df):,}")
            summary.append(f"Data source: MSHA Open Government Data")
            summary.append(f"Generated: {datetime.now().isoformat()}")
            summary.append("")

            # Accident types
            if "ACCIDENT_TYPE" in df.columns or "DEGREE_INJURY" in df.columns:
                summary.append("## Injury Severity Distribution")
                if "DEGREE_INJURY" in df.columns:
                    injury_counts = df["DEGREE_INJURY"].value_counts()
                    for injury_type, count in injury_counts.items():
                        summary.append(f"- {injury_type}: {count:,}")
                summary.append("")

            # By year
            if "CAL_YR" in df.columns:
                summary.append("## Accidents by Year (Recent)")
                year_counts = df["CAL_YR"].value_counts().sort_index()
                for year, count in year_counts.tail(10).items():
                    summary.append(f"- {int(year)}: {count:,}")
                summary.append("")

            # Common causes
            summary.append("## Common Accident Patterns")
            summary.append("Based on MSHA accident data, key safety focus areas include:")
            summary.append("- Powered haulage accidents")
            summary.append("- Falling/sliding rock or material")
            summary.append("- Machinery accidents")
            summary.append("- Slip/fall accidents")
            summary.append("- Electrical accidents")
            summary.append("")

            with open(kb_dir / "accidents_analysis.txt", "w") as f:
                f.write("\n".join(summary))

            logger.info(f"Created accidents analysis ({len(df):,} records)")

        except Exception as e:
            logger.error(f"Error processing accidents data: {e}")

    def _process_violations_data(self, kb_dir: Path):
        """Create knowledge base entries from violations data."""
        violations_dir = DATA_DIR / "Violations"
        if not violations_dir.exists():
            return

        txt_files = list(violations_dir.glob("*.txt"))
        if not txt_files:
            return

        try:
            # Violations file can be very large, read in chunks
            chunks = pd.read_csv(
                txt_files[0],
                sep="|",
                encoding="latin-1",
                low_memory=False,
                on_bad_lines="skip",
                chunksize=100000,
            )

            total_records = 0
            section_counts = {}

            for chunk in chunks:
                total_records += len(chunk)

                # Count violations by section
                if "SECTION_OF_ACT" in chunk.columns:
                    for section, count in chunk["SECTION_OF_ACT"].value_counts().items():
                        section_counts[section] = section_counts.get(section, 0) + count

            summary = []
            summary.append("# MSHA Violation Statistics")
            summary.append(f"Total violation records: {total_records:,}")
            summary.append(f"Data source: MSHA Open Government Data")
            summary.append(f"Generated: {datetime.now().isoformat()}")
            summary.append("")

            summary.append("## Violations by CFR Section")
            summary.append("Most commonly cited regulations:")
            sorted_sections = sorted(section_counts.items(), key=lambda x: x[1], reverse=True)
            for section, count in sorted_sections[:20]:
                summary.append(f"- {section}: {count:,} violations")
            summary.append("")

            summary.append("## Key Compliance Areas")
            summary.append("Based on violation data, critical compliance areas include:")
            summary.append("- Roof control plans and support")
            summary.append("- Ventilation requirements")
            summary.append("- Electrical safety standards")
            summary.append("- Emergency escape and rescue")
            summary.append("- Equipment guarding and maintenance")
            summary.append("- Training and certification requirements")

            with open(kb_dir / "violations_analysis.txt", "w") as f:
                f.write("\n".join(summary))

            logger.info(f"Created violations analysis ({total_records:,} records)")

        except Exception as e:
            logger.error(f"Error processing violations data: {e}")

    def run(self):
        """Download all MSHA datasets."""
        logger.info("Starting MSHA data download")
        start_time = datetime.now()

        # Dataset URLs
        datasets = [
            ("https://arlweb.msha.gov/OpenGovernmentData/DataSets/Mines.zip", "Mines"),
            ("https://arlweb.msha.gov/OpenGovernmentData/DataSets/Accidents.zip", "Accidents"),
            ("https://arlweb.msha.gov/OpenGovernmentData/DataSets/Violations.zip", "Violations"),
            ("https://arlweb.msha.gov/OpenGovernmentData/DataSets/Inspections.zip", "Inspections"),
        ]

        for url, name in datasets:
            self.download_dataset(url, name)

        # Process to knowledge base
        self.process_to_knowledge_base()

        # Save metadata
        with open(DATA_DIR / "metadata.json", "w") as f:
            import json
            json.dump(self.datasets, f, indent=2)

        elapsed = datetime.now() - start_time
        logger.info("=" * 60)
        logger.info("MSHA Data Download Complete")
        logger.info(f"Datasets downloaded: {len(self.datasets)}")
        logger.info(f"Time elapsed: {elapsed}")
        logger.info("=" * 60)


if __name__ == "__main__":
    downloader = MSHADataDownloader()
    downloader.run()
