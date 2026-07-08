import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hadr.correlate import CorrelationIndex
from hadr.models import Evidence, new_situation_from


def usgs_eq(eid, lat, lon, onset, ids=None):
    return Evidence(
        evidence_id=f"ev-{eid}", source="usgs", source_event_id=eid,
        hazard_type="earthquake", observed_at="2026-07-08T00:00:00Z",
        onset_time=onset, lat=lat, lon=lon, magnitude=7.0,
        external_ids=ids or [eid], pager_level="orange",
    )


def gdacs_eq(eid, lat, lon, onset, external=None, glide=None):
    return Evidence(
        evidence_id=f"ev-{eid}", source="gdacs", source_event_id=eid,
        hazard_type="earthquake", observed_at="2026-07-08T00:00:00Z",
        onset_time=onset, lat=lat, lon=lon, origin_agency="NEIC",
        external_ids=external or [], glide=glide, gdacs_level="Orange",
    )


class TestCorrelate(unittest.TestCase):
    def _index_with(self, ev):
        idx = CorrelationIndex()
        sit = new_situation_from(ev, f"sit-{ev.source}-{ev.source_event_id}", ev.observed_at)
        idx.add(ev, sit)
        return idx, sit

    def test_rung1_same_source_same_id_is_exact(self):
        base = usgs_eq("us_1", 10.5, -68.2, "2026-07-07T09:12:00Z")
        idx, sit = self._index_with(base)
        again = usgs_eq("us_1", 10.5, -68.2, "2026-07-07T09:12:00Z")
        m = idx.match(again)
        self.assertEqual(m.confidence, "exact")
        self.assertTrue(m.auto_merge)
        self.assertEqual(m.situation_id, sit.situation_id)

    def test_rung3a_explicit_upstream_id(self):
        base = usgs_eq("us_1", 10.5, -68.2, "2026-07-07T09:12:00Z", ids=["us_1"])
        idx, sit = self._index_with(base)
        # GDACS record far away in space/time, but names the USGS id explicitly.
        g = gdacs_eq("500", 0.0, 0.0, "2026-01-01T00:00:00Z", external=["us_1"])
        m = idx.match(g)
        self.assertEqual(m.confidence, "cross_source")
        self.assertEqual(m.rung, "3a")
        self.assertEqual(m.situation_id, sit.situation_id)

    def test_rung3b_cross_source_eq_coincidence(self):
        base = usgs_eq("us_1", 10.5, -68.2, "2026-07-07T09:12:00Z")
        idx, sit = self._index_with(base)
        g = gdacs_eq("500", 10.52, -68.25, "2026-07-07T09:12:30")  # 30s, ~5km
        m = idx.match(g)
        self.assertEqual(m.confidence, "cross_source")
        self.assertEqual(m.rung, "3b")
        self.assertEqual(m.situation_id, sit.situation_id)

    def test_same_source_coincidence_does_not_merge(self):
        # Two USGS quakes close in space/time (e.g. an aftershock) must NOT be
        # coincidence-merged — that path is cross-source only.
        base = usgs_eq("us_1", 10.5, -68.2, "2026-07-07T09:12:00Z")
        idx, _ = self._index_with(base)
        after = usgs_eq("us_2", 10.51, -68.21, "2026-07-07T09:13:00Z")
        m = idx.match(after)
        self.assertIsNone(m.confidence)

    def test_rung4_loose_match_is_fuzzy_not_merged(self):
        base = usgs_eq("us_1", 10.5, -68.2, "2026-07-07T09:12:00Z")
        idx, _ = self._index_with(base)
        # cross-source EQ ~200s and ~120km away: outside identity, inside fuzzy.
        g = gdacs_eq("500", 11.5, -68.7, "2026-07-07T09:15:20")
        m = idx.match(g)
        self.assertEqual(m.confidence, "fuzzy")
        self.assertFalse(m.auto_merge)

    def test_merged_situation_does_not_absorb_new_same_source_quake(self):
        # A USGS+GDACS merged situation must not absorb a *distinct* USGS quake
        # nearby — that would be the USGS<->USGS fusion the guard prevents.
        u = usgs_eq("us_1", 10.5, -68.2, "2026-07-07T09:12:00Z")
        g = gdacs_eq("gd_1", 10.52, -68.25, "2026-07-07T09:12:30")
        idx = CorrelationIndex()
        sit = new_situation_from(u, "sit-merged", u.observed_at)
        sit.apply_evidence(g)
        idx.add(u, sit)
        idx.add(g, sit)  # situation now reported by both feeds
        newq = usgs_eq("us_2", 10.9, -68.5, "2026-07-07T09:13:00Z")
        self.assertIsNone(idx.match(newq).confidence)

    def test_cross_source_large_magnitude_gap_not_merged(self):
        # Coincident in space/time but 2 magnitudes apart -> distinct events;
        # the magnitude gate keeps rung 3b from fusing them.
        base = usgs_eq("us_1", 10.5, -68.2, "2026-07-07T09:12:00Z")  # M7.0
        idx, _ = self._index_with(base)
        g = gdacs_eq("gd_1", 10.52, -68.25, "2026-07-07T09:12:30")
        g.magnitude = 5.0
        m = idx.match(g)
        self.assertEqual(m.confidence, "fuzzy")  # flagged for review, not merged


if __name__ == "__main__":
    unittest.main()
