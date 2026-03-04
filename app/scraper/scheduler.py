"""
Auto-Sync Scheduler (Multi-Target) - Place at: app/scraper/scheduler.py
Runs multi-dashboard scraping + data ingestion on cron schedule.
"""
import asyncio
import json
import concurrent.futures
from datetime import datetime
from pathlib import Path
from loguru import logger

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

_scheduler = None
_sync_log = []


def get_sync_log():
    return _sync_log[-20:]


def run_sync_job(scraper_config: dict, run_ingestion: bool = True):
    """
    Full sync job: scrape all targets -> download Excels -> run ingestion.
    """
    from app.scraper.browser import MultiDashboardScraper
    from app.scraper.semantic import extract_dashboard_text_and_visuals

    job = {
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "excel_files": [],
        "screenshots": [],
        "semantic_summary": "",
        "errors": [],
    }

    try:
        logger.info("=== AUTO-SYNC START (multi-target) ===")

        # Step 1: Run multi-target scraper in an isolated thread
        # This avoids "Cannot run event loop while another is running"
        # when called from FastAPI (uvicorn's loop) or APScheduler threads.
        def _scrape_in_isolated_thread():
            import sys
            # Windows needs ProactorEventLoop for subprocess support (Playwright)
            if sys.platform == "win32":
                _loop = asyncio.ProactorEventLoop()
            else:
                _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
            try:
                _scraper = MultiDashboardScraper(scraper_config)
                return _loop.run_until_complete(_scraper.run())
            finally:
                _loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_scrape_in_isolated_thread)
            res = future.result(timeout=600)  # 10 min timeout

        job["excel_files"] = res.get("excel_files", [])
        job["screenshots"] = res.get("screenshots", [])
        job["errors"].extend(res.get("errors", []))

        # Log per-target results
        for name, target_res in res.get("targets", {}).items():
            status = "OK" if not target_res.get("errors") else "WARN"
            excel = target_res.get("excel_path", "none")
            ss_count = len(target_res.get("screenshots", []))
            logger.info(f"  [{status}] {name}: excel={excel}, screenshots={ss_count}")

        # Step 2: Semantic analysis of dashboard screenshots
        if res.get("screenshots"):
            logger.info("Running semantic analysis on screenshots...")
            # Build a fake single-scraper result for the semantic analyzer
            combined = {
                "screenshots": res["screenshots"],
                "page_text": "",
            }
            # Combine page text from all targets
            for target_res in res.get("targets", {}).values():
                if target_res.get("page_text"):
                    combined["page_text"] += f"\n\n--- {target_res['name']} ---\n"
                    combined["page_text"] += target_res["page_text"][:3000]

            enriched = extract_dashboard_text_and_visuals(combined)
            job["semantic_summary"] = enriched.get("combined_summary", "")

            # Save analysis
            try:
                ss_dir = Path(scraper_config.get("screenshots_dir", "./screenshots"))
                ss_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                analysis_path = ss_dir / f"analysis_{ts}.json"
                analysis_path.write_text(
                    json.dumps(enriched, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8"
                )
                logger.info(f"Analysis saved: {analysis_path}")
            except Exception as e:
                logger.warning(f"Failed to save analysis: {e}")

        # Step 3: Run data ingestion if any Excel was downloaded
        if run_ingestion and res.get("excel_files"):
            logger.info(f"Running ingestion for {len(res['excel_files'])} Excel file(s)...")
            try:
                from app.data.ingestion import ingest_all
                from app.core.precomputed import refresh_cache
                from app.db.duckdb_conn import get_connection

                # Extract paths from per-target results
                survey_path = None
                study_path = None
                for name, target_res in res.get("targets", {}).items():
                    excel = target_res.get("excel_path")
                    if not excel:
                        continue
                    if "survey" in name.lower():
                        survey_path = excel
                    elif "study" in name.lower():
                        study_path = excel

                if survey_path and study_path:
                    # DuckDB allows only ONE write connection at a time.
                    # Close the main app's cached connection so ingestion can write,
                    # then reconnect after ingestion is done.
                    import app.db.duckdb_conn as db_module
                    try:
                        old_conn = getattr(db_module, '_conn', None) or getattr(db_module, '_connection', None)
                        if old_conn:
                            old_conn.close()
                        # Reset the cached reference so get_connection() creates a fresh one
                        if hasattr(db_module, '_conn'):
                            db_module._conn = None
                        if hasattr(db_module, '_connection'):
                            db_module._connection = None
                        logger.info("Released main DB connection for ingestion")
                    except Exception as e:
                        logger.warning(f"Could not release main connection: {e}")

                    try:
                        ingest_all(survey_path=survey_path, study_path=study_path)
                        logger.info("Data ingestion completed successfully")
                    finally:
                        # Reconnect read-only so the app can continue serving queries
                        try:
                            get_connection(read_only=True)
                            logger.info("Reconnected main DB connection")
                        except Exception as e:
                            logger.warning(f"Reconnection issue: {e}")

                    refresh_cache()
                else:
                    missing = []
                    if not survey_path:
                        missing.append("survey")
                    if not study_path:
                        missing.append("study")
                    logger.warning(f"Skipping ingestion - missing Excel: {', '.join(missing)}")

                job["success"] = True

            except Exception as e:
                error_msg = f"Ingestion failed: {str(e)}"
                logger.error(error_msg)
                job["errors"].append(error_msg)
                # Scrape was still successful even if ingestion failed
                job["success"] = True
        elif res.get("excel_files"):
            job["success"] = True
        else:
            if not job["errors"]:
                job["errors"].append("No Excel files downloaded from any target")

    except Exception as e:
        error_msg = f"Sync job failed: {str(e)}"
        logger.error(error_msg)
        job["errors"].append(error_msg)

    _sync_log.append(job)
    status_text = "OK" if job["success"] else "FAIL"
    logger.info(f"=== AUTO-SYNC {status_text}: {len(job['excel_files'])} files ===")
    return job


def start_scheduler(scraper_config: dict, schedule: str = "0 */6 * * *"):
    """
    Start background scheduler.

    Args:
        scraper_config: Full config dict from config.py
        schedule: Cron expression (default: every 6 hours)
    """
    global _scheduler

    if not HAS_APSCHEDULER:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        return None

    if _scheduler:
        stop_scheduler()

    _scheduler = BackgroundScheduler()

    parts = schedule.split()
    if len(parts) == 5:
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1],
            day=parts[2], month=parts[3], day_of_week=parts[4]
        )
    else:
        logger.warning(f"Invalid cron: '{schedule}', defaulting to every 6 hours")
        trigger = CronTrigger(hour="*/6")

    _scheduler.add_job(
        run_sync_job,
        trigger=trigger,
        kwargs={"scraper_config": scraper_config, "run_ingestion": True},
        id="dashboard_sync",
        name="GeoSurvAI Dashboard Sync",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(f"Scheduler started: {schedule}")
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")


def get_scheduler_status():
    if not _scheduler:
        return {"running": False, "next_run": None, "total_syncs": len(_sync_log)}

    jobs = _scheduler.get_jobs()
    return {
        "running": True,
        "next_run": str(jobs[0].next_run_time) if jobs else None,
        "total_syncs": len(_sync_log),
        "last_sync": _sync_log[-1] if _sync_log else None,
    }
