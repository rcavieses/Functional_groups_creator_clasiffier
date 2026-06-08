"""
config.py - Functional Groups Project Configuration
=====================================================
Global parameters, file paths, and evaluation criteria.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ─── Load environment variables from .env ──────────────────────────
load_dotenv(Path(__file__).parent / ".env", override=True)

# ─── Project paths ───────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

SPECIES_CSV = DATA_DIR / "species_list.csv"
INITIAL_GROUPS_JSON = DATA_DIR / "initial_groups.json"

# ─── Algorithm constraints ──────────────────────────────────────
MAX_GROUPS = 80                # Maximum number of functional groups
MAX_ITERATIONS = 10            # Maximum iterations for optimizer
MIN_SPECIES_PER_GROUP = 1      # Minimum species to consider a valid group
TARGET_UNASSIGNED_RATIO = 0.05 # Target: <5% of unassigned species

# ─── LLM Configuration with Ollama ────────────────────────────────
# Ollama is a local server that runs LLM models
# Recommended models: qwen3:8b, nous-hermes2 (⚡ FASTER), mistral, llama2, neural-chat
# To download a model: ollama pull <model_name>
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")  # Configured from .env
LLM_MAX_TOKENS = 8192  # Increased from 4096 to accommodate larger batch responses (187 species)
LLM_TEMPERATURE = 0.3  # Lower temperature for consistency in classification
OLLAMA_TIMEOUT = 600  # Timeout in seconds (increased for slower hardware)
LLM_STREAMING = os.environ.get("LLM_STREAMING", "1").lower() in ("1", "true", "yes")  # Show tokens in real-time

# ─── Scoring criteria for group importance ──────────────────
# Each criterion has a weight and description.
# Total group score = weighted sum of all criteria.
SCORING_CRITERIA = {
    "species_richness": {
        "weight": 0.20,
        "description": "Number of species in the group (normalized)",
    },
    "trophic_importance": {
        "weight": 0.20,
        "description": "Key trophic role in the ecosystem food web",
    },
    "commercial_value": {
        "weight": 0.15,
        "description": "Fishery/commercial importance of group species",
    },
    "ecological_role": {
        "weight": 0.20,
        "description": "Ecosystem function (e.g., bioengineering, bioturbation, primary production)",
    },
    "conservation_status": {
        "weight": 0.10,
        "description": "Presence of protected or endangered species",
    },
    "uniqueness": {
        "weight": 0.15,
        "description": "How unique the functional niche is (low redundancy with other groups)",
    },
}

# ─── Mapping of text values to numeric scores ──────────────────
COMMERCIAL_IMPORTANCE_MAP = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.3,
    "protected": 0.8,  # High conservation value
    "ecological": 0.7, # High ecological value
}

TROPHIC_IMPORTANCE_MAP = {
    "primary_producer": 1.0,
    "filter_feeder": 0.9,
    "herbivore": 0.8,
    "detritivore": 0.7,
    "planktivore": 0.9,
    "omnivore": 0.6,
    "carnivore": 0.7,
    "mixotroph": 0.8,
}
