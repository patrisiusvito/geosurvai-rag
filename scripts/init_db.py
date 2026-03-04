"""
Initialize Database
Load Excel files into DuckDB and refresh pre-computed analytics.

Usage:
    python scripts/init_db.py --survey path/to/survey.xlsx --study path/to/study.xlsx
    python scripts/init_db.py  (uses default paths in data/raw/)
"""
import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from config import DATA_DIR, DUCKDB_PATH
from app.data.ingestion import ingest_all
from app.core.precomputed import refresh_cache
from app.db.duckdb_conn import get_connection, get_schema_info


def find_latest_excel(directory: Path, prefix: str) -> Path | None:
    """Find the most recent Excel file matching a prefix."""
    files = sorted(directory.glob(f"{prefix}*.xlsx"), reverse=True)
    return files[0] if files else None


def main():
    parser = argparse.ArgumentParser(description="Initialize GeoSurvAI database")
    parser.add_argument("--survey", type=str, help="Path to survey Excel file")
    parser.add_argument("--study", type=str, help="Path to study Excel file")
    parser.add_argument("--db", type=str, help="Path to DuckDB file", default=DUCKDB_PATH)
    args = parser.parse_args()

    # Find Excel files
    survey_path = args.survey
    study_path = args.study

    if not survey_path:
        found = find_latest_excel(DATA_DIR, "KegiatanSurvey")
        if found:
            survey_path = str(found)
        else:
            logger.error(f"No survey Excel found in {DATA_DIR}. Use --survey flag.")
            sys.exit(1)

    if not study_path:
        found = find_latest_excel(DATA_DIR, "KegiatanStudy")
        if found:
            study_path = str(found)
        else:
            logger.error(f"No study Excel found in {DATA_DIR}. Use --study flag.")
            sys.exit(1)

    logger.info(f"Survey file: {survey_path}")
    logger.info(f"Study file:  {study_path}")
    logger.info(f"Database:    {args.db}")

    # Ingest data
    stats = ingest_all(survey_path, study_path, args.db)

    # Refresh pre-computed analytics
    logger.info("Refreshing pre-computed analytics...")
    try:
        cache = refresh_cache()
        logger.info(f"Pre-computed brief generated at: {cache['updated_at']}")
        logger.info(f"Risk alerts detected: {len(cache['risks'])}")
    except Exception as e:
        logger.warning(f"Pre-computed analytics failed: {e}")
        logger.warning("This is OK if survey_main failed to load — fix the error and re-run.")

    # Print schema
    logger.info("\n" + "=" * 60)
    logger.info("DATABASE SCHEMA:")
    logger.info("=" * 60)
    schema = get_schema_info()
    print(schema)

    # Quick validation queries
    conn = get_connection(read_only=True)
    logger.info("\n" + "=" * 60)
    logger.info("VALIDATION QUERIES:")
    logger.info("=" * 60)

    queries = [
        ("Total survei", "SELECT COUNT(*) FROM survey_main"),
        ("Total studi", "SELECT COUNT(*) FROM study_main"),
        ("Total AFE survei", "SELECT ROUND(SUM(NILAI_AFE_INVESTASI), 0) FROM survey_main"),
        ("Total MMBOE", "SELECT ROUND(SUM(RR_TOTAL_P50_MMBOE), 2) FROM survey_main"),
        ("Survei per status", "SELECT REALISASI_STATUS_PELAKSANAAN, COUNT(*) FROM survey_main GROUP BY 1"),
        ("Studi per tipe", "SELECT TIPE_STUDI, COUNT(*) FROM study_main GROUP BY 1"),
    ]

    for label, query in queries:
        result = conn.execute(query).fetchall()
        logger.info(f"  {label}: {result}")

    logger.info("\n✅ Database initialization complete!")
    logger.info(f"Start the server with: python -m app.main")


if __name__ == "__main__":
    main()
