"""Permanent reconciliation test for the committed C2 local-study ledger.

Campaign rule: any independently-counted ledger is guilty until
reconciled. This test re-derives every headline number in
c2_local_study.json from its own rows and re-classifies every verdict
from its own CI, so the artifact can never silently disagree with the
frozen protocol it claims to implement. Fast (reads the JSON only);
the full re-decode of the local pipeline is the offline determinism
route (python c2_local_study.py — fixed seed, frozen rules).

Also carries the ledger-side date-gate audit: NO event in the committed
artifact may belong to a post-DEV_END session — the study population
ends 2024-12-31 and the artifact itself must prove it.
"""
import json
import os
import unittest
from datetime import date

from campaign2_analysis import (CONTRAST_WINSOR_R, PRIMARY_CELL,
                                PRIMARY_HORIZON_MIN, THETA_R,
                                classify_primary, screen_vs_zero)
import databento_local_data as dld

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "c2_local_study.json")


class C2LedgerIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(LEDGER):
            raise unittest.SkipTest(
                "study ledger not materialized (run c2_local_study.py on "
                "the dev machine; git-ignored purchase required)")
        with open(LEDGER, encoding="utf-8") as fh:
            cls.doc = json.load(fh)
        cls.report = cls.doc["report"]

    def test_frozen_identity(self):
        r = self.report
        self.assertEqual(r["protocol"], "C2-ONLT-v1")
        self.assertEqual(r["theta_R"], THETA_R)
        self.assertEqual(r["theta_R"], 0.2)
        self.assertEqual(r["primary_cell"], PRIMARY_CELL)
        self.assertEqual(r["primary_cell"], "T2S0.5")
        self.assertEqual(r["horizon_min"], PRIMARY_HORIZON_MIN)
        self.assertEqual(r["horizon_min"], 120)
        self.assertEqual(r["dev_range"],
                         ["2010-06-07", dld.DEV_END.isoformat()])
        self.assertEqual(r["frozen_gate_n"], 800)
        self.assertAlmostEqual(r["anchored_central_sd_R"], 1.6015,
                               places=4)

    def test_ledger_date_gate(self):
        """No committed event may touch validation/holdout dates."""
        for m, events in self.doc["events"].items():
            for e in events:
                self.assertLessEqual(date.fromisoformat(e["session_date"]),
                                     dld.DEV_END,
                                     f"{m}: event on locked session "
                                     f"{e['session_date']}")

    def test_counts_and_dispersion_rederive(self):
        for m in ("NQ", "GC"):
            f = self.report["funnel"][m]
            s = self.report["primary_stats"][m]
            events = self.doc["events"][m]
            self.assertEqual(f["events"], len(events),
                             f"{m}: funnel count != rows")
            self.assertEqual(s["n"], len(events), f"{m}: stats n != rows")
            contrasts = [e["contrast_R"] for e in events]
            mean = sum(contrasts) / len(contrasts)
            var = sum((c - mean) ** 2 for c in contrasts) \
                / (len(contrasts) - 1)
            self.assertAlmostEqual(s["event_mean_R_descriptive"], mean,
                                   delta=1e-9, msg=f"{m}: event mean drift")
            self.assertAlmostEqual(s["sd_contrast_R"], var ** 0.5,
                                   delta=1e-9, msg=f"{m}: sd drift")
            sessions = sorted({e["session_date"] for e in events})
            self.assertEqual(s["sessions"], len(sessions),
                             f"{m}: session count drift")
            self.assertLess(s["sessions"], s["n"],
                            f"{m}: clusters are not observations — "
                            "clustered bootstrap invalid")

    def test_payoffs_inside_frozen_bounds(self):
        for m, events in self.doc["events"].items():
            for e in events:
                self.assertIn(e["reversal_R"], (2.0, -0.5, 0.0),
                              f"{m}: payoff outside T2S0.5 table")
                self.assertIn(e["continuation_R"], (2.0, -0.5, 0.0))
                self.assertGreaterEqual(e["contrast_R"],
                                        CONTRAST_WINSOR_R[0] - 1e-9)
                self.assertLessEqual(e["contrast_R"],
                                     CONTRAST_WINSOR_R[1] + 1e-9)

    def test_payoffs_consistent_with_recorded_extremes(self):
        """Soundness gate promoted from the C2-RESIDUE-STOPWIDEN probe
        (2026-09-04): stored arm payoffs must be NECESSARILY consistent
        with the window extremes recorded on the same row. The rev arm's
        mfe/mae were recorded on its own signed path, so:
          rev_R == -0.5  requires mae <= -0.5   (adverse reached stop)
          rev_R == +2    requires mfe >= 2      (favorable reached target)
          rev_R == 0     requires -0.5 < mae AND mfe < 2 (neither)
        The continuation arm mirrors axes (its adverse is the rev's
        favorable extreme): cont stop needs mfe >= 0.5, cont target needs
        mae <= -2. First-touch ORDER across bars cannot be checked from
        window extremes — that is exactly the bound the archive states —
        but these necessary conditions CANNOT all hold if either formula
        is sign-inverted, and they failed loudly on every pre-fix row
        class the defect produced (e.g. rev=-0.5 with mae>=0, or cont=+2
        with mae=0). A regression of the resolve_arm/mfe/mae convention
        turns this test RED."""
        eps = 1e-9
        # stored extremes are rounded to 6 decimals; a value printed as
        # exactly -0.5 may be -0.4999995+true. Boundary (">") checks use
        # 1e-5 slack — an inverted-formula regression deviates by whole
        # barrier multiples (0.5/1.5/2R) and still fails loudly.
        reps = 1e-5
        for m, events in self.doc["events"].items():
            for e in events:
                mfe, mae = e["mfe_R"], e["mae_R"]
                if e["reversal_R"] == -0.5:
                    self.assertLessEqual(mae, -0.5 + eps,
                                         f"{m}: stop paid without adverse")
                elif e["reversal_R"] == 2.0:
                    self.assertGreaterEqual(mfe, 2 - eps,
                                            f"{m}: target paid without "
                                            "favorable extreme")
                else:
                    self.assertGreater(mae, -0.5 - reps,
                                       f"{m}: undecided despite adverse "
                                       "crossing stop")
                    self.assertLess(mfe, 2 + reps,
                                    f"{m}: undecided despite favorable "
                                    "crossing target")
                if e["continuation_R"] == -0.5:
                    self.assertGreaterEqual(mfe, 0.5 - eps,
                                            f"{m}: cont stop paid without "
                                            "rev-favorable 0.5")
                elif e["continuation_R"] == 2.0:
                    self.assertLessEqual(mae, -2 + eps,
                                         f"{m}: cont target paid without "
                                         "rev-adverse 2R")
                else:
                    self.assertLess(mfe, 0.5 + reps,
                                    f"{m}: cont undecided despite its "
                                    "stop-crossed extreme")
                    self.assertGreater(mae, -2 - reps,
                                       f"{m}: cont undecided despite its "
                                       "target-crossed extreme")

    def test_verdicts_reclassify_from_own_ci(self):
        """The stored label must be exactly classify_primary on the
        stored interval — verdict drift is impossible by test."""
        r = self.report
        for name in ("primary_a_index", "primary_b_gold"):
            v = r["verdicts"][name]
            lo, hi = v["ci_low_R"], v["ci_high_R"]
            self.assertEqual(v["confirmatory"],
                             classify_primary(v["point_R"], lo, hi,
                                              v["theta_R"]),
                             f"{name}: label != its own interval")
            self.assertEqual(v["screening"],
                             screen_vs_zero(lo, hi, v["theta_R"])["screening"],
                             f"{name}: screening != its own interval")
            self.assertIs(v["operable"], v["n"] >= 800,
                          f"{name}: operable flag != frozen gate")
        # A/B never pooled: each verdict cites exactly one market
        self.assertEqual(r["verdicts"]["primary_a_index"]["market"], "NQ")
        self.assertEqual(r["verdicts"]["primary_b_gold"]["market"], "GC")
        self.assertEqual(
            r["pooled_descriptive"]["label"],
            "descriptive_only_never_a_verdict")

    def test_stand_down_logic_matches_gate(self):
        r = self.report
        expect = []
        for m in ("NQ", "GC"):
            s = r["primary_stats"][m]
            if s["n"] < r["frozen_gate_n"]:
                expect.append(f"{m}: achieved n={s['n']} < frozen gate 800")
            if s["sd_contrast_R"] > r["anchored_central_sd_R"] * 1.5:
                expect.append(f"{m}: sd={s['sd_contrast_R']:.4f}R exceeds "
                              "anchor materially")
        self.assertEqual(r["stand_down"], expect,
                         "stand-down list != gate arithmetic")


if __name__ == "__main__":
    unittest.main(verbosity=2)
