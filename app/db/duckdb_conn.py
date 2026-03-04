"""
DuckDB Connection Manager
Manages connection to the structured data database.
"""
import duckdb
from loguru import logger

_connection = None


def get_connection(db_path: str = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Get or create DuckDB connection (singleton)."""
    global _connection
    if _connection is None:
        from config import DUCKDB_PATH
        path = db_path or DUCKDB_PATH
        _connection = duckdb.connect(path, read_only=read_only)
        logger.info(f"DuckDB connected: {path}")
    return _connection


def close_connection():
    """Close the DuckDB connection."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None
        logger.info("DuckDB connection closed")


def get_schema_info(conn: duckdb.DuckDBPyConnection = None) -> str:
    """Extract schema information for prompt engineering."""
    conn = conn or get_connection(read_only=True)
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()

    schema_parts = []
    for (table,) in tables:
        cols = conn.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = '{table}'
            ORDER BY ordinal_position
        """).fetchall()
        col_lines = [f"  - {name} ({dtype})" for name, dtype in cols]
        schema_parts.append(f"TABLE {table}:\n" + "\n".join(col_lines))

    return "\n\n".join(schema_parts)


def get_table_stats(conn: duckdb.DuckDBPyConnection = None) -> dict:
    """Get row counts per table."""
    conn = conn or get_connection(read_only=True)
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()

    stats = {}
    for (table,) in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[table] = count
    return stats
