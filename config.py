"""
GeoSurvAI RAG — Configuration
Semua settings terpusat di sini.
"""
import os
from pathlib import Path

# === Paths ===
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "raw"
DB_DIR = BASE_DIR / "db"
CACHE_DIR = BASE_DIR / "data" / "cache"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# === Ollama Server ===
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://117.54.250.177:5162")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:12b")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest")

# === Database ===
DUCKDB_PATH = str(DB_DIR / "geosurvai.duckdb")

# === API ===
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_TITLE = os.getenv("APP_TITLE", "GeoSurvAI")

# === GeoSurvAI Data Sources ===
SURVEY_EXCEL_URL = "https://geosurvai.com/survey-tables"
STUDY_EXCEL_URL = "https://geosurvai.com/study-tables"
SURVEY_DASHBOARD_URL = "https://geosurvai.com/survey-dashboard"
STUDY_DASHBOARD_URL = "https://geosurvai.com/study-dashboard"

# === LLM Settings ===
LLM_TEMPERATURE = 0.1  # Low for SQL generation accuracy
LLM_MAX_TOKENS = 2048
SQL_MAX_RETRIES = 2     # Retry SQL generation if execution fails
