import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hadr import fetch, store
from hadr.pipeline import run

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _raw(run_id):
    return {
        "usgs": fetch.features(fetch.load_json_file(os.path.join(FIX, f"usgs_run{run_id}.json"))),
        "gdacs": fetch.features(fetch.load_json_file(os.path.join(FIX, f"gdacs_run{run_id}.json"))),
    }


def _by_sid(changes):
    return {c.situation_id: c for c in changes}


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = store.connect(self.tmp.name)
        store.init_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def test_run1_new_events_and_cross_source_dedup(self):
        changes = run(self.conn, _raw(1), "2026-07-07T12:00:00Z")
        by = _by_sid(changes)

        verdicts = sorted(c.verdict for c in changes)
        self.assertEqual(verdicts.count("WAKE"), 4)
        self.assertEqual(verdicts.count("QUIET"), 1)
        self.assertEqual(verdicts.count("FLAG"), 0)

        # green Alaska quake stays quiet; the orange ones wake.
        self.assertEqual(by["sit-usgs-us_A"].verdict, "QUIET")
        self.assertEqual(by["sit-usgs-us_B"].verdict, "WAKE")

        # DEDUP: the GDACS Venezuela quake folds into the USGS situation.
        sits = store.load_situations(self.conn)
        self.assertEqual(len(sits), 5)
        self.assertNotIn("sit-gdacs-100", sits)
        b = sits["sit-usgs-us_B"]
        self.assertEqual(b.pager_level, "orange")
        self.assertEqual(b.gdacs_level, "Orange")
        self.assertCountEqual(b.sources, ["usgs", "gdacs"])

    def test_run2_escalation_retraction_and_noise(self):
        run(self.conn, _raw(1), "2026-07-07T12:00:00Z")
        changes = run(self.conn, _raw(2), "2026-07-08T00:00:00Z")
        by = _by_sid(changes)

        # Alaska green -> orange, and the cyclone Orange -> Red: both escalate.
        self.assertEqual(by["sit-usgs-us_A"].verdict, "WAKE")
        self.assertEqual(by["sit-usgs-us_A"].kind, "escalation")
        self.assertEqual(by["sit-gdacs-300"].kind, "escalation")

        # Peru quake deleted -> retraction of a previously reported event.
        self.assertEqual(by["sit-usgs-us_C"].verdict, "WAKE")
        self.assertEqual(by["sit-usgs-us_C"].kind, "retraction")
        self.assertEqual(store.load_situations(self.conn)["sit-usgs-us_C"].status, "retracted")

        # Venezuela: reviewed status + identical numbers -> quiet.
        # Chile: magnitude 6.0 -> 6.1 is within noise -> quiet.
        self.assertEqual(by["sit-usgs-us_B"].verdict, "QUIET")
        self.assertEqual(by["sit-usgs-us_D"].verdict, "QUIET")
        self.assertEqual(by["sit-usgs-us_D"].kind, "noise")

    def test_rerun_identical_input_is_silent(self):
        # "Stays quiet when nothing has changed": re-running run 2's exact input
        # must produce no WAKE/FLAG -- including no repeat retraction.
        run(self.conn, _raw(1), "2026-07-07T12:00:00Z")
        run(self.conn, _raw(2), "2026-07-08T00:00:00Z")
        again = run(self.conn, _raw(2), "2026-07-08T00:05:00Z")
        self.assertTrue(all(c.verdict == "QUIET" for c in again), [c for c in again if c.verdict != "QUIET"])


if __name__ == "__main__":
    unittest.main()
