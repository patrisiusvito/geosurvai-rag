"""
Data Ingestion Pipeline
Loads Excel exports from geosurvai.com into DuckDB.
"""
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime
from loguru import logger


def clean_survey_main(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and enrich survey_main data."""
    # Parse date columns
    date_cols = [c for c in df.columns if "WAKTU" in c]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # Clean percentage columns (ensure 0-100)
    for col in df.columns:
        if col.startswith("P_") and df[col].dtype in ("float64", "int64"):
            df[col] = df[col].fillna(0).clip(0, 100)

    # Numeric cleanup
    for col in ["NILAI_AFE_INVESTASI", "REALISASI_AFE_INVESTASI", "RR_TOTAL_P50_MMBOE",
                 "RR_P50_OIL_MMBOE", "RR_P50_GAS_BSCF", "RENCANA_KUANTITAS_PEKERJAAN",
                 "REALISASI_KUANTITAS_PEKERJAAN"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Add computed columns
    # Handle timezone: Excel dates come as UTC-aware, Timestamp.now() is naive
    now = pd.Timestamp.now(tz="UTC")

    df["IS_DELAYED"] = False
    df["DAYS_SINCE_PLANNED_START"] = 0

    if "RENCANA_WAKTU_MULAI" in df.columns and df["RENCANA_WAKTU_MULAI"].notna().any():
        # Ensure timezone consistency
        rencana = df["RENCANA_WAKTU_MULAI"]
        if rencana.dt.tz is None:
            rencana = rencana.dt.tz_localize("UTC")

        df["IS_DELAYED"] = (
            (df["REALISASI_STATUS_PELAKSANAAN"] == "Belum Mulai")
            & (rencana < now)
            & (rencana.notna())
        )

        df["DAYS_SINCE_PLANNED_START"] = (
            (now - rencana).dt.days.clip(lower=0)
        )
        df["DAYS_SINCE_PLANNED_START"] = df["DAYS_SINCE_PLANNED_START"].fillna(0).astype(int)
    df["DAYS_SINCE_PLANNED_START"] = df["DAYS_SINCE_PLANNED_START"].fillna(0).astype(int)

    # Standardize text columns
    for col in ["REGION_SKK", "PROVINSI", "HOLDING", "KKKS", "WK",
                 "JENIS_KEGIATAN", "AREA_KEGIATAN", "STATUS_WK",
                 "REALISASI_STATUS_PELAKSANAAN"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    logger.info(f"survey_main cleaned: {len(df)} rows, {len(df.columns)} cols")
    return df


def clean_study_main(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and enrich study_main data."""
    # Parse dates
    date_cols = [c for c in df.columns if "WAKTU" in c or "TGL" in c]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # Numeric cleanup
    for col in ["RENCANA_ANGGARAN_AFE_INVESTASI", "REALISASI_ANGGARAN_AFE_INVESTASI",
                 "P_PROGRESS_PELAKSANAAN", "LUAS_WK_AWAL_KM2", "LUAS_WK_SAAT_INI_KM2"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Standardize text
    for col in ["KKKS", "HOLDING", "WK", "STATUS_WK", "TIPE_STUDI",
                 "WILAYAH_SKK_MIGAS", "REALISASI_STATUS_PELAKSANAAN",
                 "STATUS_USULAN_KEGIATAN", "TIPE_KONTRAK"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    logger.info(f"study_main cleaned: {len(df)} rows, {len(df.columns)} cols")
    return df


def ingest_survey_excel(filepath: str, conn: duckdb.DuckDBPyConnection = None):
    """
    Load Survey Excel (4 sheets) into DuckDB.

    Sheets: Main, Receiver, Recording, Shot Point
    """
    if conn is None:
        from app.db.duckdb_conn import get_connection
        conn = get_connection()

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Survey Excel not found: {filepath}")

    logger.info(f"Ingesting survey data from: {filepath}")

    sheet_mapping = {
        "Main": ("survey_main", clean_survey_main),
        "Receiver": ("survey_receiver", None),
        "Recording": ("survey_recording", None),
        "Shot Point": ("survey_shotpoint", None),
    }

    for sheet_name, (table_name, cleaner) in sheet_mapping.items():
        try:
            df = pd.read_excel(filepath, sheet_name=sheet_name)

            if cleaner:
                df = cleaner(df)

            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")

            row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            logger.info(f"  ✓ {table_name}: {row_count} rows loaded from sheet '{sheet_name}'")
        except Exception as e:
            logger.error(f"  ✗ Failed to load sheet '{sheet_name}': {e}")

    # Record ingestion timestamp
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _ingestion_log (
            source VARCHAR, ingested_at TIMESTAMP, filepath VARCHAR, rows_total INTEGER
        )
    """)
    try:
        total = conn.execute("SELECT COUNT(*) FROM survey_main").fetchone()[0]
        conn.execute(
            "INSERT INTO _ingestion_log VALUES (?, ?, ?, ?)",
            ["survey", datetime.now(), str(filepath), total]
        )
    except Exception:
        logger.warning("  ⚠️ survey_main not created — skipping ingestion log")


def ingest_study_excel(filepath: str, conn: duckdb.DuckDBPyConnection = None):
    """
    Load Study Excel (1 sheet) into DuckDB.
    """
    if conn is None:
        from app.db.duckdb_conn import get_connection
        conn = get_connection()

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Study Excel not found: {filepath}")

    logger.info(f"Ingesting study data from: {filepath}")

    df = pd.read_excel(filepath, sheet_name="Main")
    df = clean_study_main(df)

    conn.execute("DROP TABLE IF EXISTS study_main")
    conn.execute("CREATE TABLE study_main AS SELECT * FROM df")

    row_count = conn.execute("SELECT COUNT(*) FROM study_main").fetchone()[0]
    logger.info(f"  ✓ study_main: {row_count} rows loaded")

    # Log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _ingestion_log (
            source VARCHAR, ingested_at TIMESTAMP, filepath VARCHAR, rows_total INTEGER
        )
    """)
    conn.execute(
        "INSERT INTO _ingestion_log VALUES (?, ?, ?, ?)",
        ["study", datetime.now(), str(filepath), row_count]
    )


def ingest_all(survey_path: str, study_path: str, db_path: str = None):
    """Full ingestion pipeline."""
    from app.db.duckdb_conn import get_connection
    conn = get_connection(db_path)

    ingest_survey_excel(survey_path, conn)
    ingest_study_excel(study_path, conn)

    # Print summary
    stats = {}
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' AND table_name NOT LIKE '_%'"
    ).fetchall()
    for (t,) in tables:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        stats[t] = n

    logger.info("=" * 50)
    logger.info("INGESTION COMPLETE:")
    for t, n in stats.items():
        logger.info(f"  {t}: {n} rows")
    logger.info("=" * 50)

    return stats
