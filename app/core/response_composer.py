"""
Response Composer (Gemini API Powered)
Converts raw data results into natural language answers.
"""
import json
from loguru import logger

# Import Gemini
from google import genai
from google.genai import types

try:
    gemini_client = genai.Client()
except Exception as e:
    logger.error("Failed to initialize Gemini Client for response composer.")
    gemini_client = None

from app.llm.prompts import RESPONSE_SYSTEM_PROMPT


def compose_response(
    question: str,
    sql: str = None,
    data: list = None,
    row_count: int = 0,
    error: str = None,
    precomputed: str = None,
) -> str:
    """
    Generate a natural language response from query results.

    For precomputed results (executive brief, risks), returns directly.
    For SQL results, uses Gemini to compose a natural response.
    """
    # If precomputed content is available, return it directly (no LLM needed)
    if precomputed:
        return precomputed

    # If SQL query had an error
    if error and not data:
        return (
            f"Maaf, saya mengalami kesulitan memproses pertanyaan Anda.\n\n"
            f"Detail teknis: {error}\n\n"
            f"Coba ulangi dengan pertanyaan yang lebih spesifik, misalnya:\n"
            f"• \"Berapa total survei di Sulawesi?\"\n"
            f"• \"Daftar survei yang belum mulai\"\n"
            f"• \"Top 5 potensi resource terbesar\""
        )

    # For simple results (single number), format directly without LLM
    if data and len(data) == 1 and len(data[0]) <= 3:
        return format_simple_result(question, data[0], sql)

    # For complex results, use Gemini to compose response
    prompt = _build_response_prompt(
        question=question,
        sql=sql,
        data=data or [],
        row_count=row_count,
        error=error,
    )

    try:
        if gemini_client is None:
            return format_fallback(question, data, row_count)

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=RESPONSE_SYSTEM_PROMPT,
                temperature=0.3,
            )
        )
        return response.text
    except Exception as e:
        logger.error(f"Response composition failed: {e}")
        return format_fallback(question, data, row_count)


def _build_response_prompt(question: str, sql: str, data: list, row_count: int, error: str = None) -> str:
    """Build the response composition prompt."""
    if error:
        return (
            f"Pertanyaan user: {question}\n"
            f"SQL: {sql}\nError: {error}\n"
            f"Jelaskan bahwa terjadi error dan sarankan pertanyaan yang lebih spesifik."
        )

    if row_count == 0:
        data_str = "(Tidak ada data yang cocok dengan query)"
    elif row_count <= 20:
        data_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    else:
        data_str = json.dumps(data[:20], indent=2, ensure_ascii=False, default=str)
        data_str += f"\n... dan {row_count - 20} baris lainnya"

    return (
        f"Pertanyaan user: {question}\n\n"
        f"SQL yang dieksekusi: {sql}\n"
        f"Jumlah hasil: {row_count} baris\n\n"
        f"Data:\n{data_str}\n\n"
        f"Berdasarkan data di atas, jawab pertanyaan user dengan ringkas dan informatif.\n"
        f"Sertakan angka-angka penting dan highlight jika ada yang perlu perhatian khusus."
    )


def format_simple_result(question: str, row: dict, sql: str = None) -> str:
    """Format simple single-row results without LLM."""
    parts = []
    for key, value in row.items():
        label = key.replace("_", " ").title()
        if isinstance(value, float):
            if abs(value) > 1_000_000:
                formatted = f"${value:,.0f}"
            elif abs(value) > 100:
                formatted = f"{value:,.1f}"
            else:
                formatted = f"{value:.1f}%"
        elif isinstance(value, int):
            formatted = f"{value:,}"
        else:
            formatted = str(value)
        parts.append(f"**{label}**: {formatted}")

    return "\n".join(parts)


def format_fallback(question: str, data: list, row_count: int) -> str:
    """Fallback formatting when LLM is unavailable."""
    if not data:
        return "Tidak ada data yang sesuai dengan pertanyaan Anda."

    text = f"Ditemukan {row_count} hasil:\n\n"

    for i, row in enumerate(data[:10]):
        parts = []
        for key, value in row.items():
            if value is not None and str(value).strip() and str(value) != "nan":
                parts.append(f"{key}: {value}")
        text += f"{i+1}. " + " | ".join(parts[:5]) + "\n"

    if row_count > 10:
        text += f"\n... dan {row_count - 10} hasil lainnya."

    return text