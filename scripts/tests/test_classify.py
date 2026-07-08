import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hadr.classify import FLAG, QUIET, WAKE, classify
from hadr.models import Situation


def sit(sid="s1", pager=None, gdacs=None, mag=None, lat=10.0, lon=-68.0, sources=None):
    return Situation(
        situation_id=sid, hazard_type="earthquake", pager_level=pager,
        gdacs_level=gdacs, magnitude=mag, lat=lat, lon=lon,
        sources=list(sources or []),
    )


class TestClassify(unittest.TestCase):
    def test_new_reportable_wakes(self):
        c = classify(None, sit(pager="orange"))
        self.assertEqual((c.verdict, c.kind), (WAKE, "new"))

    def test_new_subthreshold_is_quiet(self):
        c = classify(None, sit(pager="green"))
        self.assertEqual((c.verdict, c.kind), (QUIET, "new"))

    def test_escalation_wakes(self):
        before = sit(pager="green")
        after = sit(pager="orange")
        c = classify(before, after)
        self.assertEqual((c.verdict, c.kind), (WAKE, "escalation"))
        self.assertEqual((c.from_level, c.to_level), ("green", "orange"))

    def test_downgrade_wakes(self):
        c = classify(sit(pager="orange"), sit(pager="green"))
        self.assertEqual((c.verdict, c.kind), (WAKE, "downgrade"))

    def test_magnitude_jitter_is_quiet(self):
        c = classify(sit(pager="orange", mag=6.9), sit(pager="orange", mag=7.0))
        self.assertEqual((c.verdict, c.kind), (QUIET, "noise"))

    def test_material_magnitude_change_wakes(self):
        c = classify(sit(pager="orange", mag=6.5), sit(pager="orange", mag=7.0))
        self.assertEqual((c.verdict, c.kind), (WAKE, "update"))

    def test_new_source_wakes(self):
        before = sit(pager="orange", sources=["usgs"])
        after = sit(pager="orange", gdacs="Orange", sources=["usgs", "gdacs"])
        c = classify(before, after)
        self.assertEqual((c.verdict, c.kind), (WAKE, "update"))
        self.assertIn("new source", c.detail)

    def test_retraction_of_reported_wakes(self):
        before = sit(pager="orange")
        after = sit(pager="orange")
        after.status = "retracted"
        c = classify(before, after)
        self.assertEqual((c.verdict, c.kind), (WAKE, "retraction"))

    def test_retraction_of_subthreshold_is_quiet(self):
        before = sit(pager="green")
        after = sit(pager="green")
        after.status = "retracted"
        c = classify(before, after)
        self.assertEqual((c.verdict, c.kind), (QUIET, "retraction"))

    def test_flags_force_review(self):
        c = classify(sit(pager="orange"), sit(pager="orange"), flags=["ambiguous match"])
        self.assertEqual(c.verdict, FLAG)


if __name__ == "__main__":
    unittest.main()
