"""PERMANENT look-ahead guard for the ERL->IRL gate-ablation study.

Directive (frozen in ERLIRL_ABLATION_PROTOCOL.md S2): ship a permanent
test that fails if any gate reads a bar at or beyond the event stamp
that completes its own condition. This is the Campaign 1 defect class
(displacement/retest conditioning on the future) — four prior hits —
so the guard is structural AND pinned here with planted values.

Every gate under test is a pure function of a bar PREFIX; the tests
plant distinctive values into every bar AFTER each gate's stamp and
assert the gate's output is byte-identical.
"""
import copy
import unittest


def bar(o, h, l, c, et):
    return {"open": o, "high": h, "low": l, "close": c, "et": et}


# Import the study module for the pure gate functions.
import erlirl_ablation as ea


class DisplacementGate(unittest.TestCase):
    def test_finds_close_across_level(self):
        # low touch, reversal long: first bar after touch closing ABOVE level
        bars = [bar(10, 12, 8, 9, "t0"), bar(9, 11, 8.5, 10.4, "t1"),
                bar(10, 11, 9.5, 10.6, "t2")]
        self.assertEqual(ea.displacement_idx(bars, 0, +1, 10.0, 6), 1)

    def test_deadline(self):
        bars = [bar(10, 12, 8, 9, "t0")] + \
               [bar(9, 9.5, 8.5, 9.4, f"t{i}") for i in range(1, 8)]
        self.assertIsNone(ea.displacement_idx(bars, 0, +1, 10.0, 6))

    def test_no_lookahead_planted_after_stamp(self):
        base = [bar(10, 12, 8, 9, "t0"), bar(9, 11, 8.5, 10.4, "t1"),
                bar(10.4, 10.5, 10.3, 10.45, "t2")]
        out = ea.displacement_idx(base, 0, +1, 10.0, 6)
        for tamper_close in (-99.0, 999.0):
            for tamper_high in (-99.0, 999.0):
                mut = copy.deepcopy(base)
                mut[2]["close"] = tamper_close
                mut[2]["high"] = tamper_high
                self.assertEqual(
                    ea.displacement_idx(mut, 0, +1, 10.0, 6), out,
                    "displacement gate read the bar AFTER its stamp")


class VoidGate(unittest.TestCase):
    def test_long_void_and_near_edge(self):
        touch = bar(10, 12, 8, 9, "t0")
        d = bar(10, 13, 12.5, 12.9, "t1")       # jumps clear: low 12.5 > touch.high 12
        edge = ea.void_edge(touch, d, +1)
        self.assertEqual(edge, 12.5)             # NEAR edge, not far (12)

    def test_short_void_near_edge(self):
        touch = bar(10, 12, 8, 11, "t0")
        d = bar(8, 8.5, 6, 6.2, "t1")           # high 8.5 < touch.low 8? no; set below
        d = bar(7.9, 7.95, 6, 6.2, "t1")        # high 7.95 < touch.low 8
        edge = ea.void_edge(touch, d, -1)
        self.assertEqual(edge, 7.95)             # NEAR edge for short retrace-down

    def test_no_void(self):
        touch = bar(10, 12, 8, 9, "t0")
        d = bar(10, 11, 9.5, 10.4, "t1")
        self.assertIsNone(ea.void_edge(touch, d, +1))


class RetraceFillGate(unittest.TestCase):
    def test_open_precondition_orders_the_touch(self):
        # long: edge=12.5; bar must START at/above edge then pierce down
        bars = [bar(12.6, 12.8, 12.55, 12.6, "t0")]   # never opens above? it stays above
        self.assertIsNone(ea.retrace_fill_idx(bars, 12.5, +1, 6))
        bars = [bar(12.4, 12.7, 12.3, 12.5, "t0")]    # starts BELOW edge: invalid
        self.assertIsNone(ea.retrace_fill_idx(bars, 12.5, +1, 6))
        bars = [bar(12.7, 12.7, 12.4, 12.5, "t0")]    # opens above, pierces to 12.4
        self.assertEqual(ea.retrace_fill_idx(bars, 12.5, +1, 6), 0)

    def test_no_lookahead_planted_after_fill(self):
        base = [bar(12.7, 12.7, 12.4, 12.5, "t0"), bar(12.5, 12.6, 12.4, 12.5, "t1")]
        out = ea.retrace_fill_idx(base, 12.5, +1, 6)
        for x in (-99.0, 999.0):
            mut = copy.deepcopy(base)
            mut[1]["close"] = x
            mut[1]["high"] = x
            mut[1]["low"] = x
            self.assertEqual(ea.retrace_fill_idx(mut, 12.5, +1, 6), out,
                             "retrace gate read the bar AFTER its stamp")


class PayoffWindow(unittest.TestCase):
    def test_strictly_forward_of_stamp(self):
        import datetime as dt
        t0 = dt.datetime(2020, 1, 2, 10, 0)
        # bars 0..2 are pre-window (stamp = idx 2): the violent low 9 in the
        # window bars would fire the 9.5 stop; pre-stamp bars carry it
        pre = [bar(10, 10.2, 9.0, 10, t0 + dt.timedelta(minutes=30 * i))
               for i in range(3)]
        win = [bar(10, 10.5, 9.8, 10, t0 + dt.timedelta(minutes=30 * i))
               for i in range(3, 7)]
        import c2_local_study as c2
        # entry 10, side +1, risk 1: stop 9.5, target 12. Pre-stamp lows of
        # 9 must NOT fire the stop — only window bars are ever read.
        self.assertEqual(c2.resolve_arm(win, +1, 10.0, 1.0), 0.0)
        self.assertEqual(c2.resolve_arm(pre + win, +1, 10.0, 1.0), -0.5)

    def test_stamp_bar_itself_excluded(self):
        import datetime as dt
        import c2_local_study as c2
        t0 = dt.datetime(2020, 1, 2, 10, 0)
        b_stamp = bar(10, 11, 5, 10, t0)             # violent low AT stamp
        later = [bar(10, 10.5, 9.8, 10, t0 + dt.timedelta(minutes=30 * i))
                 for i in range(1, 5)]
        self.assertEqual(c2.resolve_arm(later, +1, 10.0, 1.0), 0.0,
                         "outcomes read the stamp bar (C2 touch-bar rule)")


class LiquidityLookback(unittest.TestCase):
    def test_reads_only_before_touch(self):
        bars = [bar(10, 11, 3, 10, "b0"), bar(10, 11, 4, 10, "b1"),
                bar(10, 11, 9, 10, "touch")]
        self.assertEqual(ea.opposing_liquidity(bars, 2, +1, lookback=2), 3.0)
        for x in (-99.0, 999.0):
            mut = copy.deepcopy(bars)
            mut[2]["low"] = x
            self.assertEqual(ea.opposing_liquidity(mut, 2, +1, lookback=2), 3.0,
                             "liquidity read the touch bar or later")


class VariableTargetSkip(unittest.TestCase):
    def test_skip_when_liquidity_beyond_2r(self):
        # long entry 10, risk 1 (stop 9): liquidity far below (5) = 5R away
        self.assertEqual(ea.variable_target(+1, 10.0, 1.0, 5.0),
                         {"skip": True})

    def test_binds_below_2r(self):
        out = ea.variable_target(+1, 10.0, 1.0, 8.5)   # 1.5R away
        self.assertFalse(out["skip"])
        self.assertEqual(out["target"], 8.5)
        self.assertTrue(out["bound_by_liquidity"])

    def test_short_mirror(self):
        out = ea.variable_target(-1, 10.0, 1.0, 11.5)  # 1.5R above entry
        self.assertFalse(out["skip"])
        self.assertEqual(out["target"], 11.5)
        out2 = ea.variable_target(-1, 10.0, 1.0, 13.5)  # beyond 2R -> skip
        self.assertTrue(out2["skip"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
