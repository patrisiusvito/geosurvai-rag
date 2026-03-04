import os, sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import APP_HOST, APP_PORT, APP_TITLE
from app.db.duckdb_conn import get_connection
from app.api.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting GeoSurvAI...")
    try:
        conn = get_connection(read_only=True)
        tables = conn.execute("SHOW TABLES").fetchall()
        for t in ["survey_main", "study_main"]:
            if t in [x[0] for x in tables]:
                count = conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
                logger.info("  " + t + ": " + str(count) + " rows")
    except Exception as e:
        logger.warning("DB check failed: " + str(e))

    try:
        from app.scraper.config import SCRAPER_CONFIG, SYNC_SCHEDULE
        url = SCRAPER_CONFIG.get("dashboard_url", "")
        if url.startswith("https://") and "your-dashboard" not in url:
            from app.scraper.scheduler import start_scheduler
            start_scheduler(SCRAPER_CONFIG, SYNC_SCHEDULE)
            logger.info("Auto-sync scheduler activated")
        else:
            logger.info("Auto-sync: Configure dashboard_url in app/scraper/config.py")
    except ImportError:
        logger.info("Auto-sync: Scraper module not found (optional)")
    except Exception as e:
        logger.warning("Auto-sync init failed: " + str(e))

    logger.info("Chat UI: http://localhost:" + str(APP_PORT) + "/")
    logger.info("API docs: http://localhost:" + str(APP_PORT) + "/docs")
    yield
    try:
        from app.scraper.scheduler import stop_scheduler
        stop_scheduler()
    except: pass


app = FastAPI(title=APP_TITLE, version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(chat_router)


@app.get("/health")
async def health():
    status = {"status": "ok", "tables": {}}
    try:
        conn = get_connection(read_only=True)
        for t in ["survey_main", "survey_receiver", "survey_recording", "survey_shotpoint", "study_main"]:
            try: status["tables"][t] = conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
            except: status["tables"][t] = 0
    except Exception as e:
        status["status"] = "degraded"
        status["error"] = str(e)
    return status


@app.post("/api/sync")
async def trigger_sync():
    try:
        from app.scraper.config import SCRAPER_CONFIG
        from app.scraper.scheduler import run_sync_job
        result = run_sync_job(SCRAPER_CONFIG, run_ingestion=True)
        return {"success": result["success"], "excel_path": result.get("excel_path"), "errors": result.get("errors", [])}
    except ImportError:
        return JSONResponse(status_code=501, content={"success": False, "error": "Scraper not configured"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/api/sync/status")
async def sync_status():
    try:
        from app.scraper.scheduler import get_scheduler_status, get_sync_log
        return {"scheduler": get_scheduler_status(), "recent_syncs": get_sync_log()}
    except ImportError:
        return {"scheduler": {"running": False}, "recent_syncs": []}


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def serve_ui():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse(content={"message": "GeoSurvAI running", "hint": "Place index.html in app/static/", "docs": "/docs"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=True)
