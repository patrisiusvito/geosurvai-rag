"""
Text-to-SQL Engine (Gemini API Powered)
Converts natural language questions to SQL, validates, and executes.
"""
import os
import re
import json
from typing import Optional
from loguru import logger
from app.db.duckdb_conn import get_connection
from config import SQL_MAX_RETRIES

# Import the new Google GenAI SDK
from google import genai
from google.genai import types

# Initialize the Gemini Client (it automatically picks up the GEMINI_API_KEY env variable)
try:
    gemini_client = genai.Client()
except Exception as e:
    logger.error("Failed to initialize Gemini Client. Did you set GEMINI_API_KEY?")
    raise e


# Dangerous patterns that should never appear in generated SQL
FORBIDDEN_PATTERNS = [
    r"\bDROP\b", r"\bDELETE\b", r"\bINSERT\b", r"\bUPDATE\b",
    r"\bALTER\b", r"\bCREATE\b", r"\bTRUNCATE\b", r"\bEXEC\b",
    r"\bGRANT\b", r"\bREVOKE\b", r"--", r";.*;"
]

VALID_TABLES = {
    "survey_main", "survey_receiver", "survey_recording",
    "survey_shotpoint", "study_main"
}


def validate_sql(sql: str) -> tuple[bool, str]:
    """Validate generated SQL for safety and correctness."""
    sql_upper = sql.upper().strip()

    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return False, "Query must start with SELECT or WITH"

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, sql_upper):
            return False, f"Forbidden SQL pattern detected: {pattern}"

    from_matches = re.findall(r'\bFROM\s+(\w+)', sql, re.IGNORECASE)
    join_matches = re.findall(r'\bJOIN\s+(\w+)', sql, re.IGNORECASE)
    referenced_tables = set(from_matches + join_matches)

    invalid_tables = referenced_tables - VALID_TABLES - {"_ingestion_log"}
    if invalid_tables:
        return False, f"Invalid table(s): {invalid_tables}. Valid tables: {VALID_TABLES}"

    return True, ""


def extract_sql(raw_llm_output: str) -> str:
    """Extracts and sanitizes a SQL query from raw LLM output."""
    if not raw_llm_output:
        return ""

    code_block_pattern = r"```(?:sql)?\s*(.*?)\s*```"
    match = re.search(code_block_pattern, raw_llm_output, re.IGNORECASE | re.DOTALL)
    sql_candidate = match.group(1) if match else raw_llm_output

    sql_start_pattern = r"(?i)(SELECT|WITH)\b(.*)"
    match = re.search(sql_start_pattern, sql_candidate, re.IGNORECASE | re.DOTALL)
    
    if match:
        cleaned_sql = match.group(1).upper() + match.group(2)
    else:
        cleaned_sql = sql_candidate

    cleaned_sql = cleaned_sql.strip()
    if ";" in cleaned_sql:
        cleaned_sql = cleaned_sql.split(";")[0].strip()

    return cleaned_sql


def generate_sql(question: str) -> str:
    """Use Gemini API to generate SQL from natural language."""
    from app.llm.prompts import get_sql_system_prompt, FEW_SHOT_EXAMPLES, HARDCODED_SCHEMA

    prompt = f"""You are an expert DuckDB SQL generator. Write a SQL query to answer the user's question.

<schema>
{HARDCODED_SCHEMA}
</schema>

<examples>
{FEW_SHOT_EXAMPLES}
</examples>

<rules>
1. Output ONLY the raw SQL query.
2. Do NOT wrap the query in markdown formatting.
3. NEVER output conversational text. NEVER ask for clarification.
4. If you are unsure of the table, make your best logical guess based on the schema.
5. You MUST use DuckDB syntax strictly (e.g., use CURRENT_DATE, not CURDATE()).
6. The query MUST strictly start with the word SELECT or WITH.
</rules>

<question>
{question}
</question>

SQL:"""

    try:
        # Call Gemini 2.5 Flash (Super fast, cheap, and excellent at coding tasks)
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are an automated Text-to-SQL engine. Output only valid DuckDB SQL. No conversation.",
                temperature=0.0, # Zero creativity, strictly factual SQL
            )
        )
        
        raw_output = response.text
    except Exception as e:
        logger.error(f"Gemini API Error: {str(e)}")
        return ""
    
    # Pass through our robust cleaner just in case
    sql = extract_sql(raw_output)
    
    logger.debug(f"Generated SQL: {sql}")
    return sql


def execute_sql(sql: str) -> dict:
    """Execute SQL query and return results."""
    conn = get_connection(read_only=True)
    try:
        result_df = conn.execute(sql).fetchdf()
        data = result_df.to_dict(orient="records")
        return {
            "success": True,
            "data": data,
            "columns": list(result_df.columns),
            "row_count": len(result_df),
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "data": [],
            "columns": [],
            "row_count": 0,
            "error": str(e),
        }


def run_query(question: str) -> dict:
    """Full pipeline: question → SQL → validate → execute → retry if needed."""
    attempts = []

    for attempt in range(SQL_MAX_RETRIES + 1):
        if attempt == 0:
            sql = generate_sql(question)
        else:
            last_error = attempts[-1]["error"]
            retry_prompt = (
                f"The previous SQL query failed with this error:\n"
                f"SQL: {attempts[-1]['sql']}\n"
                f"Error: {last_error}\n\n"
                f"Please fix the SQL for this question: {question}"
            )
            sql = generate_sql(retry_prompt)

        is_valid, validation_error = validate_sql(sql)
        if not is_valid:
            logger.warning(f"SQL validation failed (attempt {attempt + 1}): {validation_error}")
            attempts.append({"sql": sql, "error": f"Validation: {validation_error}"})
            continue

        result = execute_sql(sql)
        attempts.append({"sql": sql, "error": result.get("error")})

        if result["success"]:
            logger.info(f"SQL executed successfully (attempt {attempt + 1}): {result['row_count']} rows")
            return {
                "success": True,
                "sql": sql,
                "data": result["data"],
                "columns": result["columns"],
                "row_count": result["row_count"],
                "error": None,
                "attempts": len(attempts),
            }
        else:
            logger.warning(f"SQL execution failed (attempt {attempt + 1}): {result['error']}")

    last_sql = attempts[-1]["sql"] if attempts else ""
    last_error = attempts[-1]["error"] if attempts else "Unknown error"
    logger.error(f"All SQL attempts failed for: {question}")

    return {
        "success": False,
        "sql": last_sql,
        "data": [],
        "columns": [],
        "row_count": 0,
        "error": last_error,
        "attempts": len(attempts),
    }