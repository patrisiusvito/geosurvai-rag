"""
Chat API Endpoint
Main entry point for the RAG system.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from loguru import logger

from app.core.query_router import classify
from app.core.sql_engine import run_query
from app.core.precomputed import get_cached_brief, get_cached_risks, format_executive_brief, compute_executive_brief, compute_risk_alerts
from app.core.response_composer import compose_response

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    user_level: Optional[str] = "executive"  # executive | engineer


class ChatResponse(BaseModel):
    response: str
    metadata: dict


@router.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Main chat endpoint.
    
    Flow: Question → Route → Handle → Compose → Respond
    """
    start_time = datetime.now()
    question = req.message.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    logger.info(f"[CHAT] Question: {question}")

    # Step 1: Route the query
    route_result = classify(question)
    route = route_result["route"]
    logger.info(f"[CHAT] Route: {route} (method: {route_result.get('method', 'unknown')})")

    # Step 2: Handle based on route
    response_text = ""
    metadata = {
        "route": route,
        "method": route_result.get("method", ""),
        "tables": route_result.get("tables", []),
    }

    try:
        if route == "precomputed":
            # Serve cached executive brief / risk alerts
            response_text = get_cached_brief()
            if not response_text:
                # Cache miss — compute fresh
                brief = compute_executive_brief()
                risks = compute_risk_alerts()
                response_text = format_executive_brief(brief, risks)
            metadata["sql"] = None
            metadata["source"] = "precomputed_cache"

        elif route == "quantitative":
            # Generate SQL, execute, compose response
            sql_result = run_query(question)
            metadata["sql"] = sql_result["sql"]
            metadata["row_count"] = sql_result["row_count"]
            metadata["attempts"] = sql_result["attempts"]

            response_text = compose_response(
                question=question,
                sql=sql_result["sql"],
                data=sql_result["data"],
                row_count=sql_result["row_count"],
                error=sql_result.get("error"),
            )

        elif route == "qualitative":
            # For qualitative, still use SQL to get relevant data, then compose
            sql_result = run_query(question)
            metadata["sql"] = sql_result["sql"]
            metadata["row_count"] = sql_result["row_count"]

            response_text = compose_response(
                question=question,
                sql=sql_result["sql"],
                data=sql_result["data"],
                row_count=sql_result["row_count"],
                error=sql_result.get("error"),
            )

        elif route == "composite":
            # Combine SQL data + precomputed insights
            sql_result = run_query(question)
            cached_brief = get_cached_brief()
            risks = get_cached_risks()

            # Build enriched context
            context_parts = []
            if sql_result["success"]:
                import json
                context_parts.append(f"Query Data:\n{json.dumps(sql_result['data'][:15], indent=2, ensure_ascii=False, default=str)}")
            if risks:
                risk_text = "\n".join(f"- [{r['severity']}] {r['message']}" for r in risks)
                context_parts.append(f"Risk Alerts:\n{risk_text}")

            enriched_prompt = (
                f"Pertanyaan user: {question}\n\n"
                + "\n\n".join(context_parts)
                + "\n\nBerikan analisis komprehensif berdasarkan data di atas."
            )

            # Use Gemini instead of Ollama
            from google import genai
            from google.genai import types
            from app.llm.prompts import RESPONSE_SYSTEM_PROMPT

            try:
                client = genai.Client()
                gemini_response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=enriched_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=RESPONSE_SYSTEM_PROMPT,
                        temperature=0.3,
                    )
                )
                response_text = gemini_response.text
            except Exception as e:
                logger.error(f"Gemini composite response failed: {e}")
                response_text = compose_response(
                    question=question,
                    sql=sql_result.get("sql"),
                    data=sql_result.get("data", []),
                    row_count=sql_result.get("row_count", 0),
                )

            metadata["sql"] = sql_result.get("sql")
            metadata["row_count"] = sql_result.get("row_count", 0)

            from app.llm.client import chat as llm_chat
            from app.llm.prompts import RESPONSE_SYSTEM_PROMPT
            response_text = llm_chat(
                prompt=enriched_prompt,
                system=RESPONSE_SYSTEM_PROMPT,
                temperature=0.3,
            )
            metadata["sql"] = sql_result.get("sql")
            metadata["row_count"] = sql_result.get("row_count", 0)

        else:
            # Unknown route — try SQL as default
            sql_result = run_query(question)
            response_text = compose_response(
                question=question,
                sql=sql_result["sql"],
                data=sql_result["data"],
                row_count=sql_result["row_count"],
                error=sql_result.get("error"),
            )

    except Exception as e:
        logger.error(f"[CHAT] Error: {e}")
        response_text = (
            f"Maaf, terjadi error saat memproses pertanyaan Anda.\n"
            f"Silakan coba lagi atau gunakan pertanyaan yang lebih spesifik.\n\n"
            f"Contoh pertanyaan:\n"
            f"• \"Berapa total survei seismik tahun ini?\"\n"
            f"• \"Executive brief survei terkini\"\n"
            f"• \"Top 5 potensi resource terbesar\""
        )
        metadata["error"] = str(e)

    # Calculate response time
    elapsed = (datetime.now() - start_time).total_seconds()
    metadata["response_time_seconds"] = round(elapsed, 2)
    logger.info(f"[CHAT] Response in {elapsed:.2f}s, route={route}")

    return ChatResponse(response=response_text, metadata=metadata)


@router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    from app.db.duckdb_conn import get_table_stats
    from app.llm.client import test_connection

    db_ok = False
    llm_ok = False

    try:
        stats = get_table_stats()
        db_ok = len(stats) > 0
    except Exception:
        pass

    try:
        llm_ok = test_connection()
    except Exception:
        pass

    return {
        "status": "healthy" if (db_ok and llm_ok) else "degraded",
        "database": {"ok": db_ok, "tables": stats if db_ok else {}},
        "llm": {"ok": llm_ok},
        "timestamp": datetime.now().isoformat(),
    }
