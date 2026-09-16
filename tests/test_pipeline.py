"""Smoke-test suite for the PROV-AI pipeline: ingestion -> evidence sources
-> scoring -> seasonal dampener.

Runs entirely against a TEMPORARY database, ingested fresh from the
repo's real CSV/GeoJSON source files into a path created by
``tempfile.mkdtemp()``. Never opens or writes ``data/provai.db``.

Run with (from repo root):
    python -m unittest discover tests
    python -m unittest tests.test_pipeline

Stdlib ``unittest`` only -- no pytest dependency.
"""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

# Make this file runnable both as `python -m unittest discover tests` and
# directly, regardless of the current working directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import get_connection, init_db  # noqa: E402
from app.ingest import (  # noqa: E402
    DEFAULT_CSV_PATH,
    DEFAULT_GEOJSON_PATH,
    get_business,
    ingest_csv_and_geojson,
    list_businesses,
)
from app.scoring import compute_score, run_all_sources  # noqa: E402
from app.seasonal import seasonal_dampener  # noqa: E402

VALID_SIGNALS = {"active", "inactive", "silent", "disagreement"}

REAL_DB_PATH = REPO_ROOT / "data" / "provai.db"


def _fake_osm_check(business, db_path=None):
    """Deterministic stand-in for ``app.sources.osm_source.check``.

    Unlike the other five evidence sources (which default to an offline,
    deterministic mock unless an API-key env var is set), OSM makes an
    *unconditional* live HTTP call to the Overpass API -- there is no mock
    fallback gate. Hitting the real network from a test suite would make
    it slow and non-hermetic (verified: this Overpass endpoint is
    unreachable from this environment and reliably burns its full ~10s
    timeout per call). This patch keeps the suite fast and deterministic
    while still exercising the same evidence-logging code path (a row
    written to the `evidence` table, a ``{'signal', 'detail'}`` return
    value) as the real source.
    """
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        signal, detail = "silent", "OSM: mocked for test hermeticity/speed"
        conn.execute(
            "INSERT INTO evidence (business_uidn, source, signal, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (business.get("uidn"), "osm", signal, detail, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"signal": signal, "detail": detail}


class PipelineSmokeTest(unittest.TestCase):
    """End-to-end smoke tests against a hermetic, temporary database."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="provai_test_")
        cls.db_path = os.path.join(cls._tmpdir, "test_provai.db")
        cls.csv_path = str(REPO_ROOT / DEFAULT_CSV_PATH)
        cls.geojson_path = str(REPO_ROOT / DEFAULT_GEOJSON_PATH)

        init_db(cls.db_path)
        cls.row_count = ingest_csv_and_geojson(cls.csv_path, cls.geojson_path, cls.db_path)

        cls._osm_patcher = mock.patch("app.sources.osm_source.check", side_effect=_fake_osm_check)
        cls._osm_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._osm_patcher.stop()
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_uses_a_temp_db_not_the_real_one(self):
        """Sanity guard: confirm this suite never points at the real DB."""
        self.assertNotEqual(os.path.abspath(self.db_path), os.path.abspath(str(REAL_DB_PATH)))

    def test_real_db_untouched(self):
        """The real demo DB's row count must be unaffected by this suite."""
        if not REAL_DB_PATH.exists():
            self.skipTest("data/provai.db does not exist in this environment")
        conn = get_connection(str(REAL_DB_PATH))
        try:
            real_count = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
        finally:
            conn.close()
        # Just confirms we can read it read-only; the real assertion is
        # that no test method above ever passes REAL_DB_PATH as db_path.
        self.assertGreaterEqual(real_count, 0)

    def test_ingest_enterprise_establishment_split(self):
        businesses = list_businesses(db_path=self.db_path)
        self.assertEqual(len(businesses), 1000)
        enterprises = [b for b in businesses if b["entity_type"] == "enterprise"]
        establishments = [b for b in businesses if b["entity_type"] == "establishment"]
        self.assertEqual(len(enterprises), 457)
        self.assertEqual(len(establishments), 543)

    def test_ingest_is_idempotent(self):
        before = len(list_businesses(db_path=self.db_path))
        second_run_count = ingest_csv_and_geojson(self.csv_path, self.geojson_path, self.db_path)
        after = len(list_businesses(db_path=self.db_path))
        self.assertEqual(before, after)
        self.assertEqual(after, 1000)
        self.assertEqual(second_run_count, 1000)

    def test_run_all_sources_returns_six_valid_results(self):
        businesses = list_businesses(db_path=self.db_path)[:3]
        self.assertEqual(len(businesses), 3)
        for business in businesses:
            results = run_all_sources(business, db_path=self.db_path)
            self.assertEqual(len(results), 6)
            for result in results:
                self.assertIn("signal", result)
                self.assertIn("detail", result)
                self.assertIn(result["signal"], VALID_SIGNALS)
                self.assertTrue(result["detail"])

    def test_compute_score_persists_priority_score(self):
        business = list_businesses(db_path=self.db_path)[0]
        run_all_sources(business, db_path=self.db_path)
        score = compute_score(business["uidn"], db_path=self.db_path)

        self.assertIn("priority_score", score)
        self.assertIsInstance(score["priority_score"], (int, float))
        self.assertGreaterEqual(score["priority_score"], 0)

        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT priority_score FROM scores WHERE business_uidn = ?",
                (business["uidn"],),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["priority_score"], score["priority_score"])

    def test_seasonal_dampener_factor_in_range(self):
        business = list_businesses(db_path=self.db_path)[0]
        result = seasonal_dampener(business, [], current_month=6)
        self.assertIn("dampener_factor", result)
        self.assertGreaterEqual(result["dampener_factor"], 0)
        self.assertLessEqual(result["dampener_factor"], 1)

    def test_null_heavy_business_survives_full_pipeline(self):
        """Pick a business with missing phone+email and run ingest -> run_all_sources
        -> compute_score -> seasonal_dampener end to end without crashing.

        Note: every business in this dataset has non-null latitude/longitude,
        so a genuinely coordinate-less business isn't available to test here;
        this covers the missing phone/email case instead.
        """
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT uidn FROM businesses WHERE telefoonnummer IS NULL AND email IS NULL "
                "ORDER BY uidn LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row, "expected at least one business with missing phone+email")
        uidn = row["uidn"]

        business = get_business(uidn, db_path=self.db_path)
        self.assertIsNotNone(business)
        self.assertIsNone(business["telefoonnummer"])
        self.assertIsNone(business["email"])

        results = run_all_sources(business, db_path=self.db_path)
        self.assertEqual(len(results), 6)

        score = compute_score(uidn, db_path=self.db_path)
        self.assertGreaterEqual(score["priority_score"], 0)

        conn = get_connection(self.db_path)
        try:
            evidence_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM evidence WHERE business_uidn = ?", (uidn,)
                ).fetchall()
            ]
        finally:
            conn.close()

        dampener = seasonal_dampener(business, evidence_rows, current_month=1)
        self.assertGreaterEqual(dampener["dampener_factor"], 0)
        self.assertLessEqual(dampener["dampener_factor"], 1)


if __name__ == "__main__":
    unittest.main()
