"""
Manual Sync Trigger (Multi-Target) - Place at: scripts/sync_now.py
Usage:
    python scripts/sync_now.py                    # Full sync (all targets)
    python scripts/sync_now.py --no-headless      # Show browser window (debug)
    python scripts/sync_now.py --skip-ingestion   # Download only
    python scripts/sync_now.py --target survey_excel  # Single target only
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger


def main():
    parser = argparse.ArgumentParser(description="Manual GeoSurvAI dashboard sync")
    parser.add_argument("--no-headless", action="store_true", help="Show browser (debug mode)")
    parser.add_argument("--skip-ingestion", action="store_true", help="Download only, skip DB ingestion")
    parser.add_argument("--target", help="Run only a specific target by name (e.g. survey_excel)")
    args = parser.parse_args()

    from app.scraper.config import SCRAPER_CONFIG
    config = {**SCRAPER_CONFIG}

    if args.no_headless:
        config["headless"] = False

    # Filter to single target if specified
    if args.target:
        matching = [t for t in config["targets"] if t["name"] == args.target]
        if not matching:
            all_names = [t["name"] for t in config["targets"]]
            logger.error(f"Target '{args.target}' not found. Available: {all_names}")
            sys.exit(1)
        config["targets"] = matching
        logger.info(f"Running single target: {args.target}")

    logger.info("=== Manual Sync ===")
    logger.info(f"Targets: {[t['name'] for t in config['targets']]}")
    logger.info(f"Headless: {config['headless']}")

    from app.scraper.scheduler import run_sync_job
    result = run_sync_job(config, run_ingestion=not args.skip_ingestion)

    if result["success"]:
        logger.info("Sync completed successfully!")
        for f in result.get("excel_files", []):
            logger.info(f"  Excel: {f}")
        for s in result.get("screenshots", []):
            logger.info(f"  Screenshot: {s}")
        if result.get("semantic_summary"):
            logger.info(f"\nDashboard Summary:\n{result['semantic_summary'][:800]}")
    else:
        logger.error(f"Sync failed: {result['errors']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
