"""
Cloud-compatible login helper for Playwright.
Uses email/password instead of Chrome profile for cloud deployment.
Place at: app/scraper/auth.py
"""
import os
from loguru import logger
from playwright.async_api import Page


# Credentials from environment variables
GEOSURVAI_EMAIL = os.getenv("GEOSURVAI_EMAIL", "")
GEOSURVAI_PASSWORD = os.getenv("GEOSURVAI_PASSWORD", "")
GEOSURVAI_LOGIN_URL = os.getenv("GEOSURVAI_LOGIN_URL", "https://geosurvai.com/login")


async def login_with_credentials(page: Page) -> bool:
    """
    Log in to GeoSurvAI using email/password form.
    Returns True if login succeeded.
    """
    if not GEOSURVAI_EMAIL or not GEOSURVAI_PASSWORD:
        logger.error("GEOSURVAI_EMAIL and GEOSURVAI_PASSWORD env vars are required")
        return False

    try:
        logger.info(f"Navigating to login page: {GEOSURVAI_LOGIN_URL}")
        await page.goto(GEOSURVAI_LOGIN_URL, wait_until="networkidle", timeout=30000)

        # Fill in "Enter email" field
        await page.fill(
            'input[type="email"], input[placeholder*="email" i], input[name="email"]',
            GEOSURVAI_EMAIL
        )

        # Fill in "Enter Password" field
        await page.fill(
            'input[type="password"], input[placeholder*="password" i], input[name="password"]',
            GEOSURVAI_PASSWORD
        )

        # Click the submit/login button
        await page.click('button[type="submit"], input[type="submit"]')

        # Wait for navigation after login
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Verify login succeeded
        current_url = page.url
        if "login" not in current_url.lower():
            logger.info(f"Login successful! Redirected to: {current_url}")
            return True
        else:
            logger.error(f"Login may have failed - still on: {current_url}")
            await page.screenshot(path="screenshots/login_debug.png")
            return False

    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        try:
            await page.screenshot(path="screenshots/login_error.png")
        except Exception:
            pass
        return False
