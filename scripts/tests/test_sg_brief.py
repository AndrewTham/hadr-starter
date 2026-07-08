import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sg_brief

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def run_brief(db, run_id):
    argv = [
        "--db", db,
        "--usgs", os.path.join(FIX, f"usgs_run{run_id}.json"),
        "--gdacs", os.path.join(FIX, f"gdacs_run{run_id}.json"),
        "--observed-at", "2026-07-08T00:00:00Z",
    ]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = sg_brief.main(argv)
    return code, buf.getvalue()


class TestSgBriefGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_reports_on_change_and_tiers_by_relevance(self):
        code, out = run_brief(self.tmp.name, 1)
        self.assertEqual(code, 0)                     # gate open
        self.assertIn("SINGAPORE HADR BRIEF", out)
        self.assertIn("GATE: report", out)
        # The Philippines cyclone is the one regional item; the quakes are global.
        self.assertIn("REGIONAL", out)
        self.assertIn("SGT", out)

    def test_quiet_when_nothing_changed(self):
        run_brief(self.tmp.name, 1)                   # first pass: material change
        code, out = run_brief(self.tmp.name, 1)       # identical input: silent
        self.assertEqual(code, 1)                     # gate closed
        self.assertIn("GATE: quiet", out)


if __name__ == "__main__":
    unittest.main()
