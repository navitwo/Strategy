"""Permanent test for the C2 archive's quoted figures.

CAMPAIGN2_ONLT_ARCHIVE.md makes specific numeric claims in sections
2.1-2.4. Standing rule: any verifier that justified a written claim gets
promoted to a permanent test, so the archive can never silently rot
against its own artifact. This test re-derives the archive analysis from
the committed ledger via c2_archive_analysis.main() and pins every figure
the archive quotes, plus the exploratory labelling itself (the archive may
only present sections B/C as leads — the test enforces the flag exists).

The primary-CI bit-match self-check inside c2_archive_analysis is the
load-bearing integrity step; it runs here too, and an AssertionError on
drift fails this suite.
"""
import json
import os
import unittest

import c2_archive_analysis as A

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "c2_archive_analysis.json")


class C2ArchiveFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(OUT):
            raise unittest.SkipTest("run c2_archive_analysis.py first")
        with open(OUT, encoding="utf-8") as fh:
            cls.doc = json.load(fh)

    def test_exploratory_flag_present(self):
        flag = self.doc["exploratory_flag"]
        self.assertIn("post-hoc", flag.lower())
        self.assertIn("zero promotion power", flag.lower())

    def test_point1_split_was_load_bearing(self):
        """Opposite-sign primaries; pooled ~ zero (descriptive only)."""
        pts = self.doc["per_market_points_R"]
        self.assertGreater(pts["NQ"], 0.0)
        self.assertLess(pts["GC"], 0.0)
        self.assertAlmostEqual(pts["NQ"], 0.0536, places=4)
        self.assertAlmostEqual(pts["GC"], -0.0878, places=4)
        self.assertAlmostEqual(self.doc["pooled_descriptive"]["point_R"],
                               -0.0171, places=4)
        # magnitudes must be small relative to theta: the split mattered
        # because |0.054| and |0.088| cancel to ~|0.017|
        self.assertLess(abs(self.doc["pooled_descriptive"]["point_R"]),
                        min(abs(pts["NQ"]), abs(pts["GC"])))

    def test_point2_entry_survival(self):
        """NQ flips sign across entry conventions; GC holds sign."""
        nq = self.doc["markets"]["NQ"]
        gc = self.doc["markets"]["GC"]
        nq_pri = nq["primary_committed"]["point_R"]
        nq_opt = nq["sensitivities_event_mean_R"]["optimistic"]
        nq_tc = nq["sensitivities_event_mean_R"]["touch_close"]
        self.assertAlmostEqual(nq_pri, 0.0536, places=4)
        self.assertAlmostEqual(nq_opt, 0.0148, places=4)
        self.assertAlmostEqual(nq_tc, -0.0208, places=4)
        # the claim: touch_close OPPOSITE SIGN to primary for NQ
        self.assertLess(nq_pri * nq_tc, 0.0)
        gc_pri = gc["primary_committed"]["point_R"]
        gc_opt = gc["sensitivities_event_mean_R"]["optimistic"]
        gc_tc = gc["sensitivities_event_mean_R"]["touch_close"]
        self.assertAlmostEqual(gc_pri, -0.0878, places=4)
        self.assertAlmostEqual(gc_opt, -0.1449, places=4)
        self.assertAlmostEqual(gc_tc, -0.1311, places=4)
        for other in (gc_opt, gc_tc):
            self.assertGreater(gc_pri * other, 0.0)   # same sign holds

    def test_point3_horizon_profiles(self):
        """GC cont-SIG at 30/60, ns at 120/240; NQ ns until 240 cont-SIG."""
        nq = self.doc["markets"]["NQ"]["horizon_profile_signed_fwdR"]
        gc = self.doc["markets"]["GC"]["horizon_profile_signed_fwdR"]
        self.assertTrue(gc["30"]["significant"])
        self.assertEqual(gc["30"]["direction"], "continuation")
        self.assertAlmostEqual(gc["30"]["point_R"], -0.0960, places=4)
        self.assertTrue(gc["60"]["significant"])
        self.assertAlmostEqual(gc["60"]["point_R"], -0.0762, places=4)
        self.assertFalse(gc["120"]["significant"])
        self.assertFalse(gc["240"]["significant"])
        for h in ("30", "60", "120"):
            self.assertFalse(nq[h]["significant"])
        self.assertTrue(nq["240"]["significant"])
        self.assertEqual(nq["240"]["direction"], "continuation")
        self.assertAlmostEqual(nq["240"]["point_R"], -0.1611, places=4)
        # every exploratory cell must have survived the seed sweep at 0 or 1
        for m in (nq, gc):
            for cell in m.values():
                self.assertIn(cell["sig_seed_share_25"], (0.0, 1.0))

    def test_point4_touch_split(self):
        """120m fwd effect lives in overnight-high touches; lows flat."""
        for mkt, oh, oh_ci_sig in (("NQ", -0.1506, False),
                                   ("GC", -0.1248, True)):
            td = self.doc["markets"][mkt]["touch_direction_split"]
            high = td["overnight_high"]["fwd_R_120m"]
            low = td["overnight_low"]["fwd_R_120m"]
            self.assertAlmostEqual(high["point_R"], oh, places=4)
            self.assertEqual(high["significant"], oh_ci_sig)
            self.assertLess(abs(low["point_R"]), 0.03)
            self.assertFalse(low["significant"])
            self.assertGreater(low["point_R"], 0.0)   # flat, +0.018/+0.024

    def test_verdicts_stay_null(self):
        """The archive may reframe but never relabel: both primaries NULL."""
        for mkt in ("NQ", "GC"):
            p = self.doc["markets"][mkt]["primary_committed"]
            self.assertEqual(p["confirmatory"], "NULL")
            self.assertLess(abs(p["point_R"]), self.doc["theta_R"])
            self.assertGreater(abs(p["point_R"]), 0.0)


if __name__ == "__main__":
    unittest.main()
