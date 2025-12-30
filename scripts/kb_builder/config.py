"""
Knowledge Base Builder Configuration

Sources for Mining Safety Knowledge Base:
- MSHA (Mine Safety and Health Administration)
- OSHA (Occupational Safety and Health Administration)
- eCFR (Electronic Code of Federal Regulations)
- NIOSH (National Institute for Occupational Safety and Health)
- data.gov mining datasets
"""

import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
PROCESSED_DIR = BASE_DIR / "processed"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DOWNLOADS_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# =============================================================================
# MSHA SOURCES
# =============================================================================
MSHA_SOURCES = {
    "base_url": "https://www.msha.gov",

    # Main regulation pages
    "regulations": [
        "/regulations/30-cfr",
        "/regulations/policy-and-program-information-bulletins",
        "/regulations/program-information-bulletins",
        "/regulations/procedure-instruction-letters",
    ],

    # Training materials
    "training": [
        "/training/training-materials",
        "/training/miner-training",
    ],

    # Guidance documents
    "guidance": [
        "/compliance-and-enforcement/compliance-assistance",
        "/technical-support/health-safety-information",
    ],

    # Data and reports
    "data_pages": [
        "/data-and-reports/fatality-reports",
        "/data-and-reports/statistics",
    ],
}

# =============================================================================
# OSHA SOURCES
# =============================================================================
OSHA_SOURCES = {
    "base_url": "https://www.osha.gov",

    # Mining-specific pages
    "mining": [
        "/mining",
        "/laws-regs/regulations/standardnumber/1910",
        "/laws-regs/regulations/standardnumber/1926",
    ],

    # General safety that applies to mining
    "general_safety": [
        "/hazards",
        "/personal-protective-equipment",
        "/respiratory-protection",
        "/confined-spaces",
        "/hazard-communication",
    ],

    # Compliance assistance
    "compliance": [
        "/compliance-assistance",
        "/training/outreach/construction",
    ],
}

# =============================================================================
# eCFR (Code of Federal Regulations)
# =============================================================================
ECFR_SOURCES = {
    "base_url": "https://www.ecfr.gov",
    "api_base": "https://www.ecfr.gov/api/versioner/v1",

    # Title 30 - Mineral Resources (Primary mining regulations)
    "title_30": {
        "title": 30,
        "name": "Mineral Resources",
        "chapters": [
            {"chapter": "I", "name": "MSHA - Department of Labor"},
            {"chapter": "II", "name": "Bureau of Safety and Environmental Enforcement"},
            {"chapter": "IV", "name": "Geological Survey"},
            {"chapter": "V", "name": "Bureau of Ocean Energy Management"},
            {"chapter": "VII", "name": "Office of Surface Mining"},
        ]
    },

    # Title 29 - Labor (OSHA regulations)
    "title_29": {
        "title": 29,
        "name": "Labor",
        "parts": [1910, 1926],  # General Industry and Construction
    },
}

# =============================================================================
# NIOSH/CDC SOURCES
# =============================================================================
NIOSH_SOURCES = {
    "base_url": "https://www.cdc.gov/niosh",

    "mining": [
        "/mining/",
        "/mining/topics/",
        "/mining/works/",
    ],

    "publications": [
        "/mining/pubs/",
    ],
}

# =============================================================================
# DATA.GOV DATASETS
# =============================================================================
DATAGOV_DATASETS = {
    "base_url": "https://catalog.data.gov",

    # Direct dataset URLs (CSV/JSON downloads)
    "msha_datasets": [
        # Mine information
        "https://arlweb.msha.gov/OpenGovernmentData/OGIMSHA.asp",

        # These are the actual data files
        "https://arlweb.msha.gov/OpenGovernmentData/DataSets/Mines.zip",
        "https://arlweb.msha.gov/OpenGovernmentData/DataSets/MinesProdQuarterly.zip",
        "https://arlweb.msha.gov/OpenGovernmentData/DataSets/Accidents.zip",
        "https://arlweb.msha.gov/OpenGovernmentData/DataSets/Violations.zip",
        "https://arlweb.msha.gov/OpenGovernmentData/DataSets/Inspections.zip",
        "https://arlweb.msha.gov/OpenGovernmentData/DataSets/ContractorProdQuarterly.zip",
    ],
}

# =============================================================================
# PROCESSING CONFIGURATION
# =============================================================================
PROCESSING_CONFIG = {
    # Chunk settings for vector storage
    "chunk_size": 1000,  # characters
    "chunk_overlap": 200,  # characters

    # PDF extraction settings
    "pdf_extract_images": False,
    "pdf_extract_tables": True,

    # File types to process
    "supported_extensions": [".pdf", ".html", ".htm", ".txt", ".md", ".doc", ".docx"],

    # Metadata to extract
    "extract_metadata": True,
}

# =============================================================================
# REQUEST CONFIGURATION
# =============================================================================
REQUEST_CONFIG = {
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Mining Safety KB Builder/1.0",
    "timeout": 30,
    "retry_attempts": 3,
    "retry_delay": 5,  # seconds
    "rate_limit_delay": 1,  # seconds between requests
    "respect_robots_txt": True,
}

# =============================================================================
# LOGGING
# =============================================================================
LOGGING_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": LOGS_DIR / "kb_builder.log",
}
