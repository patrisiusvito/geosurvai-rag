"""
Scraper Configuration - Place at: app/scraper/config.py

Multi-target: scrapes survey dashboard, study dashboard,
and downloads Excel from both table pages.
"""
import os
from pathlib import Path

# ============================================================
# CHROME PROFILE (reuse your saved login session)
# ============================================================
# Playwright will use your Chrome profile so it picks up
# your saved email/password cookies automatically.
#
# Common Chrome user data paths:
#   Windows: C:/Users/<YOU>/AppData/Local/Google/Chrome/User Data
#   macOS:   ~/Library/Application Support/Google/Chrome
#   Linux:   ~/.config/google-chrome
#
# IMPORTANT: Chrome must be CLOSED when Playwright runs,
# otherwise it can't access the profile.

CHROME_USER_DATA = os.getenv(
    "CHROME_USER_DATA",
    str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data")
)
CHROME_PROFILE = os.getenv("CHROME_PROFILE", "Default")  # or "Profile 1", etc.


# ============================================================
# SCRAPING TARGETS
# ============================================================
# Each target defines: what to visit, what to screenshot,
# and optionally what to download.

TARGETS = [
    # ── Target 1: Survey Dashboard (screenshot + chart analysis) ──
    {
        "name": "survey_dashboard",
        "url": "https://geosurvai.com/survey-dashboard",
        "action": "screenshot",          # screenshot | download | both
        "chart_selectors": [
            # Add CSS selectors for specific charts you want analyzed:
            # "canvas",                  # All canvas charts
            # ".chart-container",
            # "#survey-progress-chart",
        ],
    },

    # ── Target 2: Study Dashboard (screenshot + chart analysis) ──
    {
        "name": "study_dashboard",
        "url": "https://geosurvai.com/study-dashboard",
        "action": "screenshot",
        "chart_selectors": [],
    },

    # ── Target 3: Survey Tables (download Excel) ──
    {
        "name": "survey_excel",
        "url": "https://geosurvai.com/survey-tables",
        "action": "download",
        "export_button": "Export as Excel",  # Button text or CSS selector
        "save_as": "survey_data.xlsx",       # Filename in data_dir
    },

    # ── Target 4: Study Tables (download Excel) ──
    {
        "name": "study_excel",
        "url": "https://geosurvai.com/study-tables",
        "action": "download",
        "export_button": "Export as Excel",
        "save_as": "study_data.xlsx",
    },
]


# ============================================================
# LOGIN (fallback if Chrome profile doesn't have session)
# ============================================================
# Only used if the scraper detects a login page.
# Set via environment variables for security.

LOGIN_CONFIG = {
    "login_url": "https://geosurvai.com/login",       # Adjust if different
    "username": os.getenv("GEOSURVAI_USER", ""),
    "password": os.getenv("GEOSURVAI_PASS", ""),
    "username_field": "input[type='email']",           # Adjust to your login form
    "password_field": "input[type='password']",
    "login_button": "button[type='submit']",
    "wait_after_login": 5,
}


# ============================================================
# DIRECTORIES
# ============================================================
DOWNLOAD_DIR = "./downloads"
DATA_DIR = "./data"
SCREENSHOTS_DIR = "./screenshots"


# ============================================================
# BROWSER SETTINGS
# ============================================================
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
WAIT_FOR_LOAD = int(os.getenv("WAIT_FOR_LOAD", "10"))


# ============================================================
# SCHEDULE (cron expression)
# ============================================================
# "0 */6 * * *"       = every 6 hours
# "0 6,12,18,0 * * *" = 4x/day at 00:00, 06:00, 12:00, 18:00
# "0 8 * * 1-5"       = weekdays at 8 AM
# "*/30 * * * *"       = every 30 min (testing)

SYNC_SCHEDULE = os.getenv("SYNC_SCHEDULE", "0 */6 * * *")


# ============================================================
# Assembled config (used by browser.py and scheduler.py)
# ============================================================
SCRAPER_CONFIG = {
    "targets": TARGETS,
    "login": LOGIN_CONFIG,
    "chrome_user_data": CHROME_USER_DATA,
    "chrome_profile": CHROME_PROFILE,
    "download_dir": DOWNLOAD_DIR,
    "data_dir": DATA_DIR,
    "screenshots_dir": SCREENSHOTS_DIR,
    "headless": HEADLESS,
    "wait_for_load": WAIT_FOR_LOAD,
}
