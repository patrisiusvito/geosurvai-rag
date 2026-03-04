"""
Multi-Target Dashboard Scraper (Playwright)
Place at: app/scraper/browser.py

Opens ONE browser session, logs in once, then visits all targets:
- Dashboard pages: screenshot + text extraction
- Table pages: click Export and download Excel
"""
import asyncio
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from loguru import logger


class MultiDashboardScraper:
    """
    Scrapes multiple dashboard/table URLs in a single browser session.
    Reuses Chrome profile for saved login cookies.
    """

    def __init__(self, config: dict):
        self.config = config
        self.targets = config.get("targets", [])
        self.login = config.get("login", {})
        self.chrome_user_data = config.get("chrome_user_data", "")
        self.chrome_profile = config.get("chrome_profile", "Default")
        self.headless = config.get("headless", True)
        self.wait_for_load = config.get("wait_for_load", 10)

        self.download_dir = Path(config.get("download_dir", "./downloads"))
        self.data_dir = Path(config.get("data_dir", "./data"))
        self.screenshots_dir = Path(config.get("screenshots_dir", "./screenshots"))

        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    async def run(self) -> dict:
        """Run all targets sequentially in one browser session."""
        from playwright.async_api import async_playwright

        result = {
            "success": False,
            "targets": {},
            "excel_files": [],
            "screenshots": [],
            "errors": [],
            "timestamp": datetime.now().isoformat(),
        }

        if not self.targets:
            result["errors"].append("No targets configured")
            return result

        async with async_playwright() as p:
            # Launch browser with Chrome profile for saved cookies
            launch_args = {
                "headless": self.headless,
                "downloads_path": str(self.download_dir),
            }

            # Try to use Chrome user data dir for saved login
            context_args = {
                "accept_downloads": True,
                "viewport": {"width": 1920, "height": 1080},
            }

            use_chrome_profile = (
                self.chrome_user_data
                and Path(self.chrome_user_data).exists()
            )

            if use_chrome_profile:
                logger.info(f"Using Chrome profile: {self.chrome_user_data}")
                try:
                    # Launch persistent context (reuses Chrome cookies)
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=str(Path(self.chrome_user_data) / self.chrome_profile),
                        headless=self.headless,
                        accept_downloads=True,
                        viewport={"width": 1920, "height": 1080},
                        downloads_path=str(self.download_dir),
                    )
                    page = context.pages[0] if context.pages else await context.new_page()
                    browser = None  # persistent context manages its own browser
                    logger.info("Chrome profile loaded successfully")
                except Exception as e:
                    logger.warning(f"Chrome profile failed: {e}. Falling back to fresh browser.")
                    use_chrome_profile = False

            if not use_chrome_profile:
                browser = await p.chromium.launch(**launch_args)
                context = await browser.new_context(**context_args)
                page = await context.new_page()

            try:
                # Check if login is needed (try first target URL)
                first_url = self.targets[0]["url"]
                await page.goto(first_url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(3000)

                # Detect login page (check if redirected to login)
                current_url = page.url.lower()
                if "login" in current_url or "signin" in current_url or "auth" in current_url:
                    logger.info("Login page detected, attempting login...")
                    await self._login(page)
                    # After login, navigate back to first target
                    await page.goto(first_url, wait_until="networkidle", timeout=60000)

                # Process each target
                for target in self.targets:
                    target_result = await self._process_target(page, target)
                    result["targets"][target["name"]] = target_result

                    if target_result.get("excel_path"):
                        result["excel_files"].append(target_result["excel_path"])
                    if target_result.get("screenshots"):
                        result["screenshots"].extend(target_result["screenshots"])
                    if target_result.get("errors"):
                        result["errors"].extend(target_result["errors"])

                # Success if at least one Excel was downloaded
                result["success"] = len(result["excel_files"]) > 0

            except Exception as e:
                error_msg = f"Scraping session failed: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
            finally:
                await context.close()
                if browser:
                    await browser.close()

        downloaded = len(result["excel_files"])
        captured = len(result["screenshots"])
        logger.info(f"Scraping complete: {downloaded} Excel files, {captured} screenshots")
        return result

    async def _login(self, page):
        """Handle login using configured credentials."""
        login_cfg = self.login
        if not login_cfg.get("username") or not login_cfg.get("password"):
            logger.warning("No login credentials configured. Set GEOSURVAI_USER and GEOSURVAI_PASS env vars.")
            return

        login_url = login_cfg.get("login_url", "")
        if login_url and login_url not in page.url:
            await page.goto(login_url, wait_until="networkidle", timeout=30000)

        try:
            await page.fill(
                login_cfg.get("username_field", "input[type='email']"),
                login_cfg["username"]
            )
            await page.fill(
                login_cfg.get("password_field", "input[type='password']"),
                login_cfg["password"]
            )
            await page.click(
                login_cfg.get("login_button", "button[type='submit']")
            )
            wait_s = login_cfg.get("wait_after_login", 5)
            await page.wait_for_timeout(wait_s * 1000)
            logger.info("Login completed")
        except Exception as e:
            logger.error(f"Login failed: {e}")

    async def _process_target(self, page, target: dict) -> dict:
        """Process a single target (screenshot and/or download)."""
        name = target["name"]
        url = target["url"]
        action = target.get("action", "screenshot")

        target_result = {
            "name": name,
            "url": url,
            "screenshots": [],
            "excel_path": None,
            "page_text": "",
            "errors": [],
        }

        try:
            logger.info(f"[{name}] Navigating to: {url}")
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(self.wait_for_load * 1000)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Screenshot actions
            if action in ("screenshot", "both"):
                # Full page screenshot
                ss_path = self.screenshots_dir / f"{name}_{ts}.png"
                await page.screenshot(path=str(ss_path), full_page=True)
                target_result["screenshots"].append(str(ss_path))
                logger.info(f"[{name}] Screenshot saved: {ss_path}")

                # Individual chart screenshots
                for i, sel in enumerate(target.get("chart_selectors", [])):
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=3000):
                            chart_path = self.screenshots_dir / f"{name}_chart{i}_{ts}.png"
                            await el.screenshot(path=str(chart_path))
                            target_result["screenshots"].append(str(chart_path))
                    except Exception as e:
                        logger.warning(f"[{name}] Chart {i} failed: {e}")

                # Extract page text
                target_result["page_text"] = await page.inner_text("body")

            # Download actions
            if action in ("download", "both"):
                excel_path = await self._download_excel(page, target, ts, target_result)
                if excel_path:
                    target_result["excel_path"] = str(excel_path)

        except Exception as e:
            error_msg = f"[{name}] Failed: {str(e)}"
            logger.error(error_msg)
            target_result["errors"].append(error_msg)

            # Error screenshot
            try:
                err_path = self.screenshots_dir / f"{name}_error_{ts}.png"
                await page.screenshot(path=str(err_path))
                target_result["screenshots"].append(str(err_path))
            except:
                pass

        return target_result

    async def _download_excel(self, page, target: dict, timestamp: str, target_result: dict) -> Optional[Path]:
        """Click export button and download Excel for a target."""
        export_btn = target.get("export_button", "Export as Excel")
        save_as = target.get("save_as", f"{target['name']}_{timestamp}.xlsx")

        # Strategies to find the export button
        strategies = [
            ("Button role", lambda: page.get_by_role("button", name=export_btn)),
            ("Text match", lambda: page.get_by_text(export_btn, exact=False).first),
            ("CSS selector", lambda: page.locator(export_btn).first),
        ]

        # Fallback selectors
        for sel in [
            "button:has-text('Export')", "button:has-text('Download')",
            "a:has-text('Export')", "a:has-text('Download')",
            "[class*='export']", ".btn-export",
        ]:
            strategies.append((f"Fallback: {sel}", lambda s=sel: page.locator(s).first))

        for strategy_name, strategy_fn in strategies:
            try:
                el = strategy_fn()
                if await el.is_visible(timeout=3000):
                    logger.info(f"[{target['name']}] Export found via: {strategy_name}")
                    async with page.expect_download(timeout=60000) as dl_info:
                        await el.click()
                    download = await dl_info.value
                    return await self._save_download(download, save_as, target["name"])
            except:
                continue

        error_msg = f"[{target['name']}] Export button not found: '{export_btn}'"
        logger.error(error_msg)
        target_result["errors"].append(error_msg)
        return None

    async def _save_download(self, download, save_as: str, target_name: str) -> Path:
        """Save downloaded file with proper naming."""
        # Save to temp download dir first
        original = download.suggested_filename or save_as
        temp_path = self.download_dir / original
        await download.save_as(str(temp_path))

        # Copy to data dir with configured name
        final_path = self.data_dir / save_as
        shutil.copy2(str(temp_path), str(final_path))

        # Also keep timestamped backup
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.data_dir / f"{Path(save_as).stem}_{ts}.xlsx"
        shutil.copy2(str(temp_path), str(backup_path))

        size_kb = temp_path.stat().st_size / 1024
        logger.info(f"[{target_name}] Excel saved: {final_path} ({size_kb:.1f} KB)")
        return final_path


def run_scraper(config: dict) -> dict:
    """Synchronous wrapper."""
    scraper = MultiDashboardScraper(config)
    return asyncio.run(scraper.run())
