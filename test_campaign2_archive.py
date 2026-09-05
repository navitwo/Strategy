"""Permanent test for the C2 archive's quoted figures.

CAMPAIGN2_ONLT_ARCHIVE.md makes specific numeric claims. Standing rule:
any verifier that justified a written claim gets promoted to a permanent
test, so the archive can never silently rot against its own artifact.
This test re-derives the archive analysis from the committed ledger via
c2_archive_analysis.main() and pins every figure the archive quotes.

Figures were RE-PINNED 2026-09-05 after the resolve_arm stop-condition
fix and the corrected DEV re-run (see the archive's defect-disclosure
section): the barrier-contrast cells changed materially; the fwd_R-based
horizon and touch cells were untouched (that formula was always correct)
and their pins did NOT move.
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

    def test_point1_same_sign_continuation(self):
        """Post-fix: both markets continuation — the pre-fix 'opposite
        signs cancelled' story was a defect artifact. GC NULL; NQ
        INCONCLUSIVE straddling -theta."""
        pts = self.doc["per_market_points_R"]
        self.assertLess(pts["NQ"], 0.0)
        self.assertLess(pts["GC"], 0.0)
        self.assertAlmostEqual(pts["NQ"], -0.1846, places=4)
        self.assertAlmostEqual(pts["GC"], -0.0958, places=4)
        self.assertAlmostEqual(self.doc["pooled_descriptive"]["point_R"],
                               -0.1402, places=4)
        nq = self.doc["markets"]["NQ"]["primary_committed"]
        gc = self.doc["markets"]["GC"]["primary_committed"]
        self.assertEqual(nq["confirmatory"], "INCONCLUSIVE")
        self.assertEqual(nq["screening"], "significant_beyond_theta")
        self.assertEqual(gc["confirmatory"], "NULL")
        self.assertEqual(gc["screening"], "significant_not_tradable")
        # NQ CI straddles -theta: the one geometry that is neither NULL
        # nor POSITIVE, classified exactly per the frozen rule.
        self.assertLess(nq["ci_low_R"], -0.2)
        self.assertGreater(nq["ci_high_R"], -0.2)

    def test_point2_no_sign_flip_after_fix(self):
        """Barrier contrasts all continuation across specs (event means
        and clustered CIs) — entry fragility as formerly described was
        an artifact of the inverted stop. GC holds at all three."""
        for mkt in ("NQ", "GC"):
            d = self.doc["markets"][mkt]
            em = d["sensitivities_event_mean_R"]
            pri = d["primary_committed"]["point_R"]
            for v in (pri, em["optimistic"], em["touch_close"]):
                self.assertLess(v, 0.0)
            for name in ("optimistic", "touch_close"):
                s = d["sensitivities_barrier_contrast"][name]
                self.assertEqual(s["direction"], "continuation")

    def test_point3_horizon_profiles_unchanged(self):
        """fwd_R cells are defect-immune: pins identical pre/post fix.
        GC cont-SIG at 30/60, ns at 120/240; NQ ns until 240 cont-SIG."""
        nq = self.doc["markets"]["NQ"]["horizon_profile_signed_fwdR"]
        gc = self.doc["markets"]["GC"]["horizon_profile_signed_fwdR"]
        self.assertAlmostEqual(gc["30"]["point_R"], -0.0960, places=4)
        self.assertTrue(gc["30"]["significant"])
        self.assertAlmostEqual(gc["60"]["point_R"], -0.0762, places=4)
        self.assertTrue(gc["60"]["significant"])
        self.assertFalse(gc["120"]["significant"])
        self.assertFalse(gc["240"]["significant"])
        for h in ("30", "60", "120"):
            self.assertFalse(nq[h]["significant"])
        self.assertTrue(nq["240"]["significant"])
        self.assertAlmostEqual(nq["240"]["point_R"], -0.1611, places=4)
        for m in (nq, gc):
            for cell in m.values():
                self.assertIn(cell["sig_seed_share_25"], (0.0, 1.0))

    def test_point4_touch_split(self):
        """120m fwd: effect lives in overnight-high, lows flat — pins
        unchanged by the fix (fwd_R). Barrier-contrast touch cells
        re-pinned post-fix (they moved)."""
        for mkt, oh in (("NQ", -0.1506), ("GC", -0.1248)):
            td = self.doc["markets"][mkt]["touch_direction_split"]
            high = td["overnight_high"]["fwd_R_120m"]
            low = td["overnight_low"]["fwd_R_120m"]
            self.assertAlmostEqual(high["point_R"], oh, places=4)
            self.assertLess(abs(low["point_R"]), 0.03)
            self.assertFalse(low["significant"])
        nq = self.doc["markets"]["NQ"]["touch_direction_split"]
        gc = self.doc["markets"]["GC"]["touch_direction_split"]
        self.assertAlmostEqual(
            nq["overnight_high"]["barrier_contrast"]["point_R"],
            -0.1009, places=4)
        self.assertAlmostEqual(
            gc["overnight_high"]["barrier_contrast"]["point_R"],
            -0.0610, places=4)

    def test_verdicts_not_promotable(self):
        """The archive may reframe but never promote: nothing cleared §7.
        NQ INCONCLUSIVE is by construction not POSITIVE; GC NULL inside
        theta. Both non-promotable."""
        for mkt in ("NQ", "GC"):
            p = self.doc["markets"][mkt]["primary_committed"]
            self.assertIn(p["confirmatory"], ("NULL", "INCONCLUSIVE"))
            self.assertNotEqual(p["confirmatory"], "POSITIVE")


if __name__ == "__main__":
    unittest.main()
