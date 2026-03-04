"""
Pre-computed Analytics
Batch-computed insights that don't need real-time LLM calls.
Updated every time data is refreshed.
"""
import json
from datetime import datetime
from pathlib import Path
from loguru import logger
from app.db.duckdb_conn import get_connection
from config import CACHE_DIR


def compute_executive_brief(conn=None) -> dict:
    """Generate comprehensive executive brief from current data."""
    conn = conn or get_connection(read_only=True)

    # Survey stats
    survey = conn.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN REALISASI_STATUS_PELAKSANAAN LIKE 'Sedang%' THEN 1 END) as berjalan,
            COUNT(CASE WHEN REALISASI_STATUS_PELAKSANAAN = 'Selesai' THEN 1 END) as selesai,
            COUNT(CASE WHEN REALISASI_STATUS_PELAKSANAAN = 'Belum Mulai' THEN 1 END) as belum_mulai,
            ROUND(SUM(NILAI_AFE_INVESTASI), 0) as total_afe,
            ROUND(SUM(REALISASI_AFE_INVESTASI), 0) as realisasi_afe,
            ROUND(SUM(RR_TOTAL_P50_MMBOE), 2) as total_mmboe,
            ROUND(AVG(P_REALISASI_KEGIATAN), 1) as avg_progress,
            COUNT(CASE WHEN JENIS_KEGIATAN = 'Seismik 2D' THEN 1 END) as seismik_2d,
            COUNT(CASE WHEN JENIS_KEGIATAN = 'Seismik 3D' THEN 1 END) as seismik_3d,
            COUNT(CASE WHEN JENIS_KEGIATAN = 'Survey Lainnya' THEN 1 END) as survey_lain,
            COUNT(CASE WHEN AREA_KEGIATAN = 'Onshore' THEN 1 END) as onshore,
            COUNT(CASE WHEN AREA_KEGIATAN = 'Offshore' THEN 1 END) as offshore
        FROM survey_main
    """).fetchdf().iloc[0].to_dict()

    # Study stats
    study = conn.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN REALISASI_STATUS_PELAKSANAAN = 'Belum Mulai' THEN 1 END) as belum_mulai,
            COUNT(CASE WHEN REALISASI_STATUS_PELAKSANAAN = 'Selesai' THEN 1 END) as selesai,
            ROUND(SUM(RENCANA_ANGGARAN_AFE_INVESTASI), 0) as total_anggaran,
            ROUND(SUM(REALISASI_ANGGARAN_AFE_INVESTASI), 0) as realisasi_anggaran
        FROM study_main
    """).fetchdf().iloc[0].to_dict()

    # Study by type
    study_by_type = conn.execute("""
        SELECT TIPE_STUDI as tipe, COUNT(*) as jumlah
        FROM study_main GROUP BY TIPE_STUDI ORDER BY jumlah DESC
    """).fetchdf().to_dict(orient="records")

    # Region breakdown
    by_region = conn.execute("""
        SELECT REGION_SKK as region, COUNT(*) as jumlah_survei,
               ROUND(AVG(P_REALISASI_KEGIATAN), 1) as avg_progress,
               ROUND(SUM(RR_TOTAL_P50_MMBOE), 1) as total_mmboe,
               ROUND(SUM(NILAI_AFE_INVESTASI), 0) as total_afe
        FROM survey_main GROUP BY REGION_SKK ORDER BY total_mmboe DESC
    """).fetchdf().to_dict(orient="records")

    # Top holdings
    top_holdings = conn.execute("""
        SELECT HOLDING, COUNT(*) as jumlah,
               ROUND(AVG(P_REALISASI_KEGIATAN), 1) as avg_progress,
               ROUND(SUM(RR_TOTAL_P50_MMBOE), 1) as total_mmboe
        FROM survey_main GROUP BY HOLDING ORDER BY jumlah DESC LIMIT 5
    """).fetchdf().to_dict(orient="records")

    return {
        "survey": survey,
        "study": study,
        "study_by_type": study_by_type,
        "by_region": by_region,
        "top_holdings": top_holdings,
        "generated_at": datetime.now().isoformat(),
    }


def compute_risk_alerts(conn=None) -> list:
    """Detect risks from current data."""
    conn = conn or get_connection(read_only=True)
    risks = []

    # Risk 1: Delayed surveys with high resource potential
    delayed = conn.execute("""
        SELECT NAMA_KEGIATAN, WK, RR_TOTAL_P50_MMBOE, DAYS_SINCE_PLANNED_START
        FROM survey_main WHERE IS_DELAYED = true AND RR_TOTAL_P50_MMBOE > 0
        ORDER BY RR_TOTAL_P50_MMBOE DESC
    """).fetchdf()
    if len(delayed) > 0:
        total_mmboe = delayed["RR_TOTAL_P50_MMBOE"].sum()
        risks.append({
            "severity": "HIGH",
            "category": "Keterlambatan Survei",
            "message": f"{len(delayed)} survei terlambat dengan potensi total {total_mmboe:.1f} MMBOE",
            "details": delayed.head(3).to_dict(orient="records"),
            "action": "Eskalasi perizinan dan pengadaan untuk survei dengan potensi tertinggi",
        })

    # Risk 2: Low AFE absorption
    afe_stats = conn.execute("""
        SELECT ROUND(SUM(REALISASI_AFE_INVESTASI), 0) as realisasi,
               ROUND(SUM(NILAI_AFE_INVESTASI), 0) as total
        FROM survey_main WHERE NILAI_AFE_INVESTASI > 0
    """).fetchone()
    if afe_stats[1] and afe_stats[1] > 0:
        pct = (afe_stats[0] / afe_stats[1]) * 100
        if pct < 25:
            risks.append({
                "severity": "MEDIUM",
                "category": "Absorpsi Anggaran Rendah",
                "message": f"Realisasi AFE survei hanya {pct:.1f}% (${afe_stats[0]:,.0f} dari ${afe_stats[1]:,.0f})",
                "action": "Review timeline procurement dan percepat proses AFE",
            })

    # Risk 3: All studies not started
    study_stats = conn.execute("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN REALISASI_STATUS_PELAKSANAAN = 'Belum Mulai' THEN 1 END) as belum
        FROM study_main
    """).fetchone()
    if study_stats[0] > 0 and study_stats[1] == study_stats[0]:
        risks.append({
            "severity": "HIGH",
            "category": "Studi Belum Dimulai",
            "message": f"Seluruh {study_stats[0]} studi masih berstatus 'Belum Mulai'",
            "action": "Koordinasi kick-off segera dengan KKKS, prioritaskan Reprocessing (durasi terpendek)",
        })

    # Risk 4: Permit bottlenecks
    permit_issues = conn.execute("""
        SELECT NAMA_KEGIATAN, WK,
               P_IZIN_PPKH, P_IZIN_UKL_UPL, P_PENGADAAN_KONTRAKTOR_SURVEI
        FROM survey_main
        WHERE REALISASI_STATUS_PELAKSANAAN = 'Belum Mulai'
        AND (P_IZIN_PPKH < 100 OR P_IZIN_UKL_UPL < 100 OR P_PENGADAAN_KONTRAKTOR_SURVEI < 100)
        AND RENCANA_WAKTU_MULAI IS NOT NULL
    """).fetchdf()
    if len(permit_issues) > 0:
        risks.append({
            "severity": "MEDIUM",
            "category": "Bottleneck Perizinan",
            "message": f"{len(permit_issues)} survei tertunda karena perizinan belum lengkap",
            "action": "Eskalasi izin PPKH ke kementerian, jalankan pengadaan kontraktor paralel",
        })

    return risks


def format_executive_brief(brief: dict, risks: list) -> str:
    """Format executive brief as readable text for chat response."""
    s = brief["survey"]
    st = brief["study"]

    # Format AFE numbers
    total_afe = s["total_afe"]
    real_afe = s["realisasi_afe"]
    afe_pct = (real_afe / total_afe * 100) if total_afe > 0 else 0

    text = f"""━━━ EXECUTIVE BRIEF GEOSURVAI ━━━
📅 Data per: {datetime.now().strftime('%d %B %Y')}

📊 SURVEI SEISMIK ({int(s['total'])} kegiatan):
• Berjalan: {int(s['berjalan'])} | Selesai: {int(s['selesai'])} | Belum Mulai: {int(s['belum_mulai'])}
• Jenis: Seismik 3D ({int(s['seismik_3d'])}), 2D ({int(s['seismik_2d'])}), Lainnya ({int(s['survey_lain'])})
• Area: Onshore ({int(s['onshore'])}), Offshore ({int(s['offshore'])})
• Total AFE: ${total_afe:,.0f} | Realisasi: ${real_afe:,.0f} ({afe_pct:.1f}%)
• Potensi Resource: {s['total_mmboe']:,.1f} MMBOE (P50)
• Avg Progress: {s['avg_progress']}%

📚 STUDI GEOLOGI ({int(st['total'])} kegiatan):
• Belum Mulai: {int(st['belum_mulai'])} | Selesai: {int(st['selesai'])}
• Anggaran: ${st['total_anggaran']:,.0f}
• Tipe: {', '.join(f"{t['tipe']} ({t['jumlah']})" for t in brief['study_by_type'])}

📍 PER REGION (Survei):"""

    for r in brief["by_region"]:
        text += f"\n• {r['region']}: {r['jumlah_survei']} survei, {r['total_mmboe']} MMBOE, avg progress {r['avg_progress']}%"

    if risks:
        text += "\n\n⚠️ RISK ALERTS:"
        for r in risks:
            text += f"\n• [{r['severity']}] {r['message']}"
            text += f"\n  → Aksi: {r['action']}"

    text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return text


def refresh_cache(conn=None):
    """Refresh all pre-computed analytics and save to cache."""
    conn = conn or get_connection(read_only=True)

    brief = compute_executive_brief(conn)
    risks = compute_risk_alerts(conn)
    formatted = format_executive_brief(brief, risks)

    cache = {
        "brief": brief,
        "risks": risks,
        "formatted_brief": formatted,
        "updated_at": datetime.now().isoformat(),
    }

    cache_path = Path(CACHE_DIR) / "precomputed.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"Pre-computed cache refreshed: {cache_path}")
    return cache


def get_cached_brief() -> str:
    """Get cached executive brief (or compute if not available)."""
    cache_path = Path(CACHE_DIR) / "precomputed.json"

    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        return cache.get("formatted_brief", "")

    # Cache miss — compute fresh
    cache = refresh_cache()
    return cache.get("formatted_brief", "")


def get_cached_risks() -> list:
    """Get cached risk alerts."""
    cache_path = Path(CACHE_DIR) / "precomputed.json"

    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        return cache.get("risks", [])

    cache = refresh_cache()
    return cache.get("risks", [])
