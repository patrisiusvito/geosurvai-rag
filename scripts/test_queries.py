"""
GeoSurvAI Test Suite
Tests 20 strategic questions against the RAG system.

Usage:
    python scripts/test_queries.py              # Test all
    python scripts/test_queries.py --quick      # Test first 5 only
    python scripts/test_queries.py --sql-only   # Only test SQL generation (no LLM compose)
"""
import sys
import json
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from app.core.sql_engine import run_query, generate_sql, validate_sql, execute_sql
from app.core.query_router import classify
from app.core.precomputed import get_cached_brief, compute_risk_alerts

# 20 strategic test questions with expected behavior
TEST_QUESTIONS = [
    # === Executive Level (1-10) ===
    {
        "id": 1,
        "question": "Berapa total kegiatan survei tahun ini?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Simple count",
    },
    {
        "id": 2,
        "question": "Berapa total investasi AFE seluruh survei?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Sum aggregation",
    },
    {
        "id": 3,
        "question": "Survei mana saja yang terlambat?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Filter on computed column",
    },
    {
        "id": 4,
        "question": "Top 5 survei dengan potensi resource terbesar",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Ranking with LIMIT",
    },
    {
        "id": 5,
        "question": "Berikan executive brief kondisi terkini",
        "expected_route": "precomputed",
        "expected_has_data": True,
        "description": "Pre-computed brief",
    },
    {
        "id": 6,
        "question": "Bandingkan kinerja per holding company",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "GROUP BY with aggregations",
    },
    {
        "id": 7,
        "question": "Total potensi resource per region",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "GROUP BY region",
    },
    {
        "id": 8,
        "question": "Berapa studi yang masih belum mulai?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Count with filter on study table",
    },
    {
        "id": 9,
        "question": "Studi tipe apa yang paling banyak?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "GROUP BY with ORDER BY",
    },
    {
        "id": 10,
        "question": "Berapa total anggaran studi tahun ini?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Sum on study table",
    },
    # === Manager/Engineer Level (11-20) ===
    {
        "id": 11,
        "question": "Daftar semua survei seismik 3D",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Filter by jenis kegiatan",
    },
    {
        "id": 12,
        "question": "Survei mana yang punya potensi besar tapi progress rendah?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Multi-condition filter",
    },
    {
        "id": 13,
        "question": "Daftar survei offshore yang sedang berjalan",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Multi-filter with LIKE",
    },
    {
        "id": 14,
        "question": "Survei apa saja yang play-nya karbonat?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Text search with LIKE",
    },
    {
        "id": 15,
        "question": "Bandingkan onshore dan offshore",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "GROUP BY comparison",
    },
    {
        "id": 16,
        "question": "Daftar survei dengan kendala operasional",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "NOT NULL filter",
    },
    {
        "id": 17,
        "question": "Status pelaksanaan survei breakdown",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "GROUP BY status",
    },
    {
        "id": 18,
        "question": "Berapa total prospect dan lead di seluruh survei?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Multiple SUM",
    },
    {
        "id": 19,
        "question": "Validator yang menangani paling banyak studi",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "GROUP BY with filter and ORDER",
    },
    {
        "id": 20,
        "question": "Berapa total kegiatan survei dan studi keseluruhan?",
        "expected_route": "quantitative",
        "expected_has_data": True,
        "description": "Cross-table subquery",
    },
]


def test_router():
    """Test query router accuracy."""
    logger.info("=" * 60)
    logger.info("TEST: Query Router")
    logger.info("=" * 60)

    correct = 0
    for t in TEST_QUESTIONS:
        result = classify(t["question"])
        route = result["route"]
        expected = t["expected_route"]
        match = "✅" if route == expected else "❌"
        if route == expected:
            correct += 1
        logger.info(f"  {match} Q{t['id']}: route={route} (expected={expected}) [{result.get('method')}]")

    accuracy = correct / len(TEST_QUESTIONS) * 100
    logger.info(f"\nRouter accuracy: {correct}/{len(TEST_QUESTIONS)} ({accuracy:.0f}%)")
    return accuracy


def test_sql_generation(quick: bool = False):
    """Test SQL generation and execution."""
    logger.info("=" * 60)
    logger.info("TEST: SQL Generation & Execution")
    logger.info("=" * 60)

    questions = TEST_QUESTIONS[:5] if quick else TEST_QUESTIONS
    # Skip precomputed questions for SQL test
    questions = [q for q in questions if q["expected_route"] != "precomputed"]

    results = []
    for t in questions:
        start = time.time()

        try:
            sql = generate_sql(t["question"])
            is_valid, val_err = validate_sql(sql)

            if not is_valid:
                results.append({
                    "id": t["id"], "success": False,
                    "error": f"Validation: {val_err}", "time": time.time() - start
                })
                logger.info(f"  ❌ Q{t['id']}: Validation failed — {val_err}")
                logger.info(f"     SQL: {sql[:100]}")
                continue

            exec_result = execute_sql(sql)
            elapsed = time.time() - start

            if exec_result["success"]:
                has_data = exec_result["row_count"] > 0
                match = has_data == t["expected_has_data"]
                icon = "✅" if match else "⚠️"
                results.append({
                    "id": t["id"], "success": True, "rows": exec_result["row_count"],
                    "time": elapsed, "data_match": match
                })
                logger.info(f"  {icon} Q{t['id']}: {exec_result['row_count']} rows, {elapsed:.1f}s — {t['description']}")
                logger.info(f"     SQL: {sql[:120]}")
            else:
                results.append({
                    "id": t["id"], "success": False,
                    "error": exec_result["error"], "time": elapsed
                })
                logger.info(f"  ❌ Q{t['id']}: Execution error — {exec_result['error'][:80]}")
                logger.info(f"     SQL: {sql[:120]}")

        except Exception as e:
            elapsed = time.time() - start
            results.append({"id": t["id"], "success": False, "error": str(e), "time": elapsed})
            logger.info(f"  ❌ Q{t['id']}: Exception — {str(e)[:80]}")

    # Summary
    success = sum(1 for r in results if r["success"])
    total = len(results)
    avg_time = sum(r["time"] for r in results) / total if total > 0 else 0
    accuracy = success / total * 100 if total > 0 else 0

    logger.info(f"\nSQL accuracy: {success}/{total} ({accuracy:.0f}%)")
    logger.info(f"Average time: {avg_time:.1f}s")

    return results


def test_precomputed():
    """Test pre-computed analytics."""
    logger.info("=" * 60)
    logger.info("TEST: Pre-computed Analytics")
    logger.info("=" * 60)

    brief = get_cached_brief()
    if brief:
        logger.info("  ✅ Executive brief available")
        logger.info(f"     Length: {len(brief)} chars")
        # Print first 3 lines
        for line in brief.split("\n")[:5]:
            logger.info(f"     {line}")
    else:
        logger.info("  ❌ No cached brief found")

    risks = compute_risk_alerts()
    logger.info(f"  Risk alerts: {len(risks)}")
    for r in risks:
        logger.info(f"    [{r['severity']}] {r['message']}")


def main():
    parser = argparse.ArgumentParser(description="GeoSurvAI Test Suite")
    parser.add_argument("--quick", action="store_true", help="Run quick test (5 questions)")
    parser.add_argument("--sql-only", action="store_true", help="Test SQL generation only")
    parser.add_argument("--router-only", action="store_true", help="Test router only")
    args = parser.parse_args()

    logger.info("🧪 GeoSurvAI RAG Test Suite")
    logger.info(f"   Database: {sys.path}")

    if args.router_only:
        test_router()
    elif args.sql_only:
        test_sql_generation(quick=args.quick)
    else:
        test_router()
        print()
        test_precomputed()
        print()
        test_sql_generation(quick=args.quick)


if __name__ == "__main__":
    main()
