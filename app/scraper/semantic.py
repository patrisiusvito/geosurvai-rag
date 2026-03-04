"""
Semantic Dashboard Analyzer (Gemini Vision)
Place at: app/scraper/semantic.py
"""
import base64
from pathlib import Path
from loguru import logger
from google import genai
from google.genai import types

try:
    gemini_client = genai.Client()
except Exception:
    gemini_client = None

CHART_ANALYSIS_PROMPT = """Anda adalah analis data SKK Migas. Analisis gambar dashboard/chart ini:
1. Tipe Visualisasi (bar/line/pie/table/map)
2. Data Utama (angka kunci)
3. Tren/Insight
4. Anomali yang perlu perhatian
Format: Bahasa Indonesia, ringkas, fokus angka."""


def analyze_screenshot(image_path: str, custom_prompt: str = None) -> dict:
    if gemini_client is None:
        return {"success": False, "analysis": "", "error": "Gemini not initialized"}
    path = Path(image_path)
    if not path.exists():
        return {"success": False, "analysis": "", "error": f"Not found: {image_path}"}
    try:
        image_bytes = path.read_bytes()
        suffix = path.suffix.lower().lstrip(".")
        media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix, "image/png")
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(role="user", parts=[
                types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                types.Part.from_text(text=custom_prompt or CHART_ANALYSIS_PROMPT),
            ])],
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return {"success": True, "analysis": response.text, "error": None}
    except Exception as e:
        logger.error(f"Chart analysis failed: {e}")
        return {"success": False, "analysis": "", "error": str(e)}


def analyze_all_screenshots(paths: list) -> list:
    return [analyze_screenshot(p) for p in paths]


def extract_dashboard_text_and_visuals(scraper_result: dict) -> dict:
    enriched = {"page_text": scraper_result.get("page_text", ""), "chart_analyses": [], "combined_summary": ""}
    screenshots = scraper_result.get("screenshots", [])
    if screenshots:
        enriched["chart_analyses"] = analyze_all_screenshots(screenshots)
    if gemini_client and (enriched["page_text"] or enriched["chart_analyses"]):
        try:
            parts = []
            if enriched["page_text"]:
                parts.append(f"Teks dashboard:\n{enriched['page_text'][:5000]}")
            for i, ca in enumerate(enriched["chart_analyses"]):
                if ca["success"]:
                    parts.append(f"Chart {i+1}:\n{ca['analysis']}")
            if parts:
                resp = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents="Buat ringkasan eksekutif (max 500 kata) status survei dan studi:\n\n" + "\n\n---\n\n".join(parts),
                    config=types.GenerateContentConfig(temperature=0.2),
                )
                enriched["combined_summary"] = resp.text
        except Exception as e:
            logger.error(f"Summary failed: {e}")
    return enriched
