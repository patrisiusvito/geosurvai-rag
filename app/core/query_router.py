"""
Query Router
Classifies user intent and routes to the appropriate handler.
Uses keyword matching first (fast, free), LLM as fallback.
"""
import re
import json
from loguru import logger
from app.llm.client import chat
from app.llm.prompts import ROUTER_SYSTEM_PROMPT


# Keyword-based routing (fast, no LLM call needed)
KEYWORD_RULES = [
    # Precomputed (highest priority)
    {
        "route": "precomputed",
        "patterns": [
            r"\b(executive|brief|rangkum|rangkuman|snapshot|overview)\b",
            r"\b(kondisi\s+terkini|status\s+keseluruhan|situasi\s+terkini)\b",
            r"\b(rekomendasi\s+(?:umum|keseluruhan|strategis))\b",
        ],
        "tables": ["both"],
    },
    # Quantitative
    {
        "route": "quantitative",
        "patterns": [
            r"\b(berapa|total|jumlah|hitung|count)\b",
            r"\b(daftar|list|sebutkan|tampilkan)\b",
            r"\b(tertinggi|terendah|terbesar|terkecil|top\s*\d+|ranking)\b",
            r"\b(rata-rata|average|persentase|persen)\b",
            r"\b(bandingkan|perbandingan|compare|vs)\b",
            r"\b(per\s+(?:region|wilayah|holding|tipe))\b",
            r"\b(breakdown|rincian|distribusi)\b",
            r"\b(progress.+rendah|potensi.+besar|belum.+mulai)\b",
            r"\b(status\s+pelaksanaan)\b",
        ],
        "tables": None,
    },
    # Qualitative
    {
        "route": "qualitative",
        "patterns": [
            r"\b(kenapa|mengapa|alasan)\b",
            r"\b(jelaskan|ceritakan|deskripsikan)\b",
            r"\b(apa\s+(?:kendala|masalah|hambatan|objektif|outlook))\b",
        ],
        "tables": None,
    },
]

# Table inference keywords
SURVEY_KEYWORDS = [
    "survei", "survey", "seismik", "seismic", "recording", "receiver",
    "shot point", "onshore", "offshore", "fold", "offset", "afe",
    "mmboe", "resource", "prospect", "lead", "play"
]
STUDY_KEYWORDS = [
    "studi", "study", "reprocessing", "g&g", "lab", "analisis",
    "mnk", "vendor", "validator"
]


def infer_tables(question: str) -> list:
    """Infer which tables are relevant based on question content."""
    lower = question.lower()
    has_survey = any(kw in lower for kw in SURVEY_KEYWORDS)
    has_study = any(kw in lower for kw in STUDY_KEYWORDS)

    if has_survey and has_study:
        return ["both"]
    elif has_study:
        return ["study_main"]
    elif has_survey:
        return ["survey_main"]
    else:
        return ["both"]  # Default to both


def route_by_keywords(question: str) -> dict | None:
    """Try to route using keyword matching (no LLM call)."""
    lower = question.lower()

    for rule in KEYWORD_RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, lower):
                tables = rule["tables"] or infer_tables(question)
                return {
                    "route": rule["route"],
                    "tables": tables,
                    "intent": f"Keyword match: {pattern}",
                    "method": "keyword",
                }
    return None


def route_by_llm(question: str) -> dict:
    """Route using LLM (slower but handles ambiguous queries)."""
    try:
        response = chat(
            prompt=question,
            system=ROUTER_SYSTEM_PROMPT,
            temperature=0.0,
        )
        # Try to parse JSON from response
        # Handle cases where LLM wraps in markdown
        text = response.strip()
        if "```" in text:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)

        result = json.loads(text)
        result["method"] = "llm"

        # Validate route value
        valid_routes = {"quantitative", "qualitative", "precomputed", "composite"}
        if result.get("route") not in valid_routes:
            result["route"] = "quantitative"  # Safe default

        return result

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"LLM router parse error: {e}, defaulting to quantitative")
        return {
            "route": "quantitative",
            "tables": infer_tables(question),
            "intent": question,
            "method": "llm_fallback",
        }


def classify(question: str) -> dict:
    """
    Main routing function: keyword first, LLM as fallback.

    Returns:
        {
            "route": "quantitative|qualitative|precomputed|composite",
            "tables": ["survey_main"|"study_main"|"both"],
            "intent": "description",
            "method": "keyword|llm|llm_fallback"
        }
    """
    # Try keyword matching first (instant, free)
    result = route_by_keywords(question)
    if result:
        logger.info(f"Route (keyword): {result['route']} → {result['tables']}")
        return result

    # Fallback to LLM
    result = route_by_llm(question)
    logger.info(f"Route (LLM): {result['route']} → {result.get('tables', 'unknown')}")
    return result
