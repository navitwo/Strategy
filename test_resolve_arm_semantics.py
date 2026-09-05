"""Permanent regression for C2 arm payoff resolution (resolve_arm).

Root cause found 2026-09-04 by the C2-RESIDUE-STOPWIDEN soundness gate:
the probe's baseline self-check required the stored bar-path contrast to
lie inside the extreme-based bracket; it failed, and tracing showed the
stored contrast itself was priced under an inverted stop condition.

The defect: resolve_arm computed adverse as (entry - low) for a LONG (and
(high - entry) for SHORT) — positive when the market moves AGAINST the
arm — and then tested ``adv <= -s_R``. That condition fires only when the
bar is entirely s_R deep on the PROFITABLE side (low >= entry + sR for
long), and never when the true adverse extreme crosses the stop. A long
trade 0.5R below entry (the frozen stop) resolved UNDECIDED (0.0); a
trade whose bar opened +0.5R above entry resolved as STOPPED (-s_R). The
preregistration froze "pessimistic stop-first" on a -0.5R adverse touch;
the implementation did the opposite. Campaign 1's hosted resolver
(scifvg_main.py:480-492 / random_time_control.py:1325-1338) records
adverse NEGATIVE (low - entry for long) and tests mae <= -stop — the
correct convention; the C2 local port inverted the recording formula
while keeping the comparison sign. That is the bug class this test pins.

Tests are synthetic and convention-free: a long whose price drops 0.5R
must pay -0.5 (stop), a short whose price rises 0.5R must pay -0.5, a
gapped-through-stop bar pays -s_R (not +t_R), real profit runs must NOT
pay a stop, and the pessimistic/optimistic ambiguity must pick the side
the frozen text names.
"""
import unittest

from c2_local_study import resolve_arm


def bar(lo, hi, o=None, c=None):
    return {"open": o if o is not None else lo, "high": hi,
            "low": lo, "close": c if c is not None else hi, "et": None}


class ResolveArmSemantics(unittest.TestCase):
    # ---- the inverted-stop defect class, four witnesses ----
    def test_long_real_adverse_touch_pays_stop(self):
        """Price drops to -0.5R (long entry 100, rd 1, stop 0.5R)."""
        path = [bar(99.5, 100.1)]
        self.assertEqual(resolve_arm(path, +1, 100.0, 1.0), -0.5)

    def test_short_real_adverse_touch_pays_stop(self):
        """Short at 100, price rises to +0.5R above entry."""
        path = [bar(99.9, 100.5)]
        self.assertEqual(resolve_arm(path, -1, 100.0, 1.0), -0.5)

    def test_profit_run_does_not_pay_stop(self):
        """A bar entirely 0.6-1.9R in the PROFIT direction must not
        register a stop hit (this was the old bug's false positive)."""
        self.assertEqual(resolve_arm([bar(100.6, 101.9)], +1,
                                     100.0, 1.0), 0.0)
        self.assertEqual(resolve_arm([bar(98.1, 99.4)], -1,
                                     100.0, 1.0), 0.0)

    def test_target_correct_both_sides(self):
        self.assertEqual(resolve_arm([bar(99.9, 102.0)], +1,
                                     100.0, 1.0), 2.0)
        self.assertEqual(resolve_arm([bar(98.0, 100.1)], -1,
                                     100.0, 1.0), 2.0)

    def test_same_bar_ambiguity_conventions(self):
        """Bar spans both barriers: pessimistic pays the stop, the
        optimistic sensitivity pays the target (frozen prereg text)."""
        path = [bar(99.5, 102.0)]
        self.assertEqual(resolve_arm(path, +1, 100.0, 1.0,
                                     pessimistic=True), -0.5)
        self.assertEqual(resolve_arm(path, +1, 100.0, 1.0,
                                     pessimistic=False), 2.0)

    def test_first_touch_order_stop_then_target(self):
        """Bar 1 stops (-0.5R low, closes back), bar 2 hits target.
        Stop came first — payoff is the stop, target is irrelevant."""
        path = [bar(99.5, 100.0, c=100.0), bar(99.9, 102.5)]
        self.assertEqual(resolve_arm(path, +1, 100.0, 1.0), -0.5)

    def test_gap_through_stop_pays_stop_not_target(self):
        """Open 0.6R below entry (through the stop): adverse before
        any chance of the target."""
        self.assertEqual(resolve_arm([bar(99.0, 99.4)], +1,
                                     100.0, 1.0), -0.5)

    def test_c1_hosted_parity(self):
        """Parity with Campaign 1's hosted first-touch logic: extreme
        recorded signed-adverse-negative, mae <= -stop. Emulate C1's
        bookkeeping on the same path and require identical payoff."""
        def c1_resolve(path, side, px, rd, t=2.0, s=0.5):
            mfe = mae = 0.0
            for b in path:
                fav = ((b["high"] - px) if side > 0
                       else (px - b["low"])) / rd
                adv = ((b["low"] - px) if side > 0
                       else (px - b["high"])) / rd   # NEGATIVE when adverse
                mfe = max(mfe, fav)
                mae = min(mae, adv)
                hit_t, hit_s = mfe >= t, mae <= -s
                if hit_t or hit_s:
                    return -s if hit_s else t   # pessimistic stop-first
            return 0.0
        for path in ([bar(99.5, 100.1)], [bar(99.9, 102.0)],
                     [bar(99.0, 99.4)], [bar(98.1, 99.4)],
                     [bar(100.6, 101.9)], [bar(98.0, 100.1)],
                     [bar(99.5, 100.0, c=100.0), bar(99.9, 102.5)]):
            for side in (+1, -1):
                self.assertEqual(resolve_arm(path, side, 100.0, 1.0),
                                 c1_resolve(path, side, 100.0, 1.0),
                                 msg=f"path={path} side={side}")


if __name__ == "__main__":
    unittest.main()
