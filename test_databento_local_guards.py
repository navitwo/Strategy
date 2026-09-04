"""Permanent tests for the three mandatory C2 local-data guards (2026-09-04).

(a) date gate: session dates past DEV_END refuse to load unless the
    committed VALIDATION_UNLOCK flag is explicitly passed True.
(b) roll handling: the embedded roll (underlying symbol change under the
    continuous series) resets ATR and invalidates the partial overnight --
    proven by a roll-day price discontinuity that must NOT corrupt an
    overnight high/low.
(c) QuantConnect reconciliation: local Databento 30m bars must match the
    bundled QC Lean minute data on a sample of dates. Skips cleanly when the
    git-ignored purchase is not on disk; runs for real on the dev machine.

Synthetic-data tests (a) and (b) always run; only (c) needs purchased files.
"""
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import databento_local_data as dld  # noqa: E402
from event_generators import OvernightLevelTouchV1  # noqa: E402

UTC = timezone.utc


def _iid(symbol):
    """Deterministic stand-in instrument_id for synthetic fixtures (real
    rows always carry one): stable small int derived from the symbol."""
    return sum((i + 1) * ord(ch) for i, ch in enumerate(symbol))


def _minute_rows_from_bars(bars_spec):
    """bars_spec: (et_naive_start, symbol, o, h, l, c) 30m bars -> minutes.
    Naive datetimes are ET WALL-CLOCK times (what the generator consumes);
    they are stamped with the ET zone so ns timestamps round-trip."""
    rows = []
    for start, sym, o, h, l, c in bars_spec:
        ts0 = int(start.replace(tzinfo=dld.ET).timestamp() * 1e9)
        for k in range(30):
            rows.append({"ts_event_ns": ts0 + k * 60 * 1_000_000_000,
                         "instrument_id": _iid(sym), "cont_symbol": "X.n.0",
                         "symbol": sym, "open": o, "high": h, "low": l,
                         "close": c, "volume": 10})
    return rows


def _flat_minutes(start_et_naive, symbol, n_minutes, price=100.0,
                  volume=5):
    rows = []
    base = int(start_et_naive.replace(tzinfo=dld.ET).timestamp() * 1e9)
    for k in range(n_minutes):
        rows.append({"ts_event_ns": base + k * 60 * 1_000_000_000,
                     "instrument_id": _iid(symbol), "cont_symbol": "X.n.0",
                     "symbol": symbol, "open": price, "high": price,
                     "low": price, "close": price, "volume": volume})
    return rows


def _overnight_spec(td, sym, base=100.0, step=1.0):
    """31 contiguous overnight bars for trade date td: minute-starts 18:00
    prev-day through 09:00 (completed-bar ENDs 18:30 through 09:30)."""
    specs = []
    t = datetime.combine(td - timedelta(days=1), datetime.min.time()
                         ).replace(hour=18)
    for i in range(31):
        o = base
        c = base + step * i
        specs.append((t, sym, o, max(o, c) + 0.5, min(o, c) - 0.5, c))
        t += timedelta(minutes=30)
    return specs


def feed_generator(gen, minute_rows):
    """Pipeline contract: embedded rolls fire on_rollover BEFORE the first
    completed bar containing new-symbol minutes; bars flow otherwise.
    Returns the bars actually delivered."""
    bars, _mixed = dld.build_bars_30m(minute_rows)
    rolls = dld.detect_rolls(minute_rows)
    pending = list(rolls)
    for bar in bars:
        first_minute_ns = int((bar["et"] - timedelta(minutes=30)
                               ).replace(tzinfo=dld.ET).timestamp() * 1e9)
        while (pending
               and bar["symbol"] == pending[0]["new_symbol"]
               and pending[0]["ts_event_ns"] >= first_minute_ns
               - 1_000_000_000):
            r = pending.pop(0)
            gen.on_rollover(bar["et"], r["old_symbol"], r["new_symbol"])
            break
        gen.on_bar({"open": bar["open"], "high": bar["high"],
                    "low": bar["low"], "close": bar["close"],
                    "et": bar["et"]})
    return bars


class DateGate(unittest.TestCase):
    def test_refuses_validation_dates(self):
        with self.assertRaises(dld.DateGateError):
            dld.check_session_dates(
                {date(2024, 12, 31), date(2025, 1, 15)})

    def test_default_call_site_stays_locked(self):
        # forgetting the argument must never unlock by accident
        with self.assertRaises(dld.DateGateError):
            dld.check_session_dates([date(2026, 6, 1)])

    def test_allows_dev_dates(self):
        dld.check_session_dates({date(2010, 6, 7), date(2024, 12, 31)})

    def test_unlock_is_committed_and_explicit(self):
        # unlock only via the committed flag, never a truthy default
        self.assertFalse(dld.VALIDATION_UNLOCK,
                         "VALIDATION_UNLOCK must stay False in a committed "
                         "state until the preregistered validation phase")
        dld.check_session_dates([date(2025, 1, 15)], unlocked=True)

    def test_loader_refuses_days_past_gate(self):
        # second mechanism of guard (a): an explicit post-DEV_END day
        # request raises even though the file physically contains it
        # (skip when the purchase is not on disk)
        if not os.path.exists(dld.OHLCV_FILE):
            self.skipTest("purchase not on disk")
        with self.assertRaises(dld.DateGateError):
            dld.load_purchased_bars(days=[date(2025, 6, 2)])

    def test_raw_primitive_refuses_post_gate_members(self):
        # the gate must live at the primitive, not only the convenience
        # loader: asking for any UTC member past DEV_END raises unless
        # explicitly unlocked
        if not os.path.exists(dld.OHLCV_FILE):
            self.skipTest("purchase not on disk")
        with self.assertRaises(dld.DateGateError):
            dld.dbn_minute_rows(dld.OHLCV_FILE, "GC",
                                {dld.DEV_END + timedelta(days=1)})
        # a member AT the gate is fine (its rows' trade dates are checked
        # downstream, and the gate day itself is dev data)
        rows = dld.dbn_minute_rows(dld.OHLCV_FILE, "GC", {dld.DEV_END})
        self.assertTrue(all(dld.trade_date_of(
            dld.ts_to_et(r["ts_event_ns"])) <= dld.DEV_END
            or dld.trade_date_of(dld.ts_to_et(r["ts_event_ns"])
                                 ) == dld.DEV_END + timedelta(days=1)
            for r in rows))


class RollHandling(unittest.TestCase):
    def test_roll_resets_atr(self):
        gen = OvernightLevelTouchV1(tick_size=0.25)
        td = date(2024, 3, 15)
        feed_generator(gen, _minute_rows_from_bars(
            _overnight_spec(td, "NQH24")))
        self.assertTrue(gen._trs)
        gen.on_rollover(datetime(2024, 3, 15, 2, 0, tzinfo=UTC),
                        "NQH24", "NQM24")
        self.assertEqual(gen._trs, [])
        self.assertIsNone(gen._prev_close)

    def test_rollover_requires_distinct_contracts(self):
        gen = OvernightLevelTouchV1(tick_size=0.25)
        with self.assertRaises(ValueError):
            gen.on_rollover(datetime(2024, 3, 15, 2, 0, tzinfo=UTC),
                            "NQH24", "NQH24")

    def test_embedded_roll_detected_from_symbol_change(self):
        td = date(2024, 6, 10)
        specs = (_overnight_spec(td, "GCZ24", base=2350.0)[:10]
                 + _overnight_spec(td, "GCM24", base=2352.0)[10:])
        rolls = dld.detect_rolls(_minute_rows_from_bars(specs))
        self.assertEqual(len(rolls), 1)
        self.assertEqual(rolls[0]["old_symbol"], "GCZ24")
        self.assertEqual(rolls[0]["new_symbol"], "GCM24")
        self.assertEqual(rolls[0]["trade_date"], td)

    def test_stream_and_definition_views_agree(self):
        """Guard (b) explicitly requires detection from the DBN stream AND
        definition data: the session-level mapping view must report the
        same roll session the stream view found, no more and no less."""
        td = date(2024, 6, 10)
        specs = (_overnight_spec(td, "GCZ24", base=2350.0)[:10]
                 + _overnight_spec(td, "GCM24", base=2352.0)[10:])
        rows = _minute_rows_from_bars(specs)
        stream = dld.detect_rolls(rows)
        definition_view = dld.mapping_roll_sessions(rows)
        self.assertEqual(len(stream), 1)
        self.assertEqual(len(definition_view), 1)
        self.assertEqual(definition_view[0]["trade_date"],
                         stream[0]["trade_date"])
        self.assertEqual(definition_view[0]["old_instrument_id"],
                         stream[0]["old_instrument_id"])
        self.assertEqual(definition_view[0]["new_instrument_id"],
                         stream[0]["new_instrument_id"])
        # roll-free stream: both views empty, mapping table well-formed
        clean = _minute_rows_from_bars(_overnight_spec(td, "GCZ24"))
        self.assertEqual(dld.detect_rolls(clean), [])
        self.assertEqual(dld.mapping_roll_sessions(clean), [])
        tables, _r = dld.build_mapping_table(clean)
        self.assertEqual(tables["X.n.0"][td], _iid("GCZ24"))

    def test_roll_day_discontinuity_cannot_corrupt_levels(self):
        """The permanent guard-(b) proof.

        A clean first trade date (contract H) establishes overnight levels.
        On the roll trade date the stream switches H->M mid-overnight, and
        the OLD contract's bars sit 1000 points ABOVE the new one: if the
        invalidation ever failed, the inflated old-contract high could
        leak into an overnight range computed against new-contract prices.
        """
        gen = OvernightLevelTouchV1(tick_size=0.25)
        td1 = date(2024, 3, 15)
        feed_generator(gen, _minute_rows_from_bars(
            _overnight_spec(td1, "NQH24", base=18000.0)))
        self.assertTrue(gen._levels)
        self.assertIsNotNone(gen._atr())

        td2 = date(2024, 3, 18)
        split = 15  # roll lands mid-overnight (between bars 14 and 15)
        specs_h = _overnight_spec(td2, "NQH24", base=18000.0)
        specs_m = _overnight_spec(td2, "NQM24", base=17000.0)
        specs = specs_h[:split] + specs_m[split:]
        feed_generator(gen, _minute_rows_from_bars(specs))
        # the mapping event invalidated the partial overnight: NO levels
        self.assertIsNone(gen._levels,
                          "roll-trade-date overnight must yield no levels")

        # next trade date, fully new contract: levels come from NEW bars only
        td3 = date(2024, 3, 19)
        feed_generator(gen, _minute_rows_from_bars(
            _overnight_spec(td3, "NQM24", base=17000.0)))
        hi, lo = gen._levels
        self.assertLess(hi, 17100.0,
                        f"corruption: old-contract high leaked (hi={hi})")
        self.assertGreater(lo, 16900.0,
                           f"corruption: old-contract low leaked (lo={lo})")

    def test_zero_volume_minutes_do_not_fabricate_bars(self):
        # Lean has no bar for a no-trade minute; the local path must agree
        rows = _flat_minutes(datetime(2024, 5, 15, 9, 30), "GCZ24", 60,
                             volume=0)
        bars, mixed = dld.build_bars_30m(rows)
        self.assertEqual(bars, [])
        self.assertEqual(mixed, [])

    def test_mid_slot_roll_produces_no_bar(self):
        # a slot whose minutes span two contracts must be excluded (mixed),
        # never emitted as a cross-contract price blend
        rows = (_flat_minutes(datetime(2024, 5, 15, 9, 30), "GCZ24", 10)
                + _flat_minutes(datetime(2024, 5, 15, 9, 40), "GCM24", 10))
        rows[10]["high"] = 999.0
        bars, mixed = dld.build_bars_30m(rows)
        self.assertEqual(len(mixed), 1, "roll slot not recorded")
        self.assertEqual(mixed[0], datetime(2024, 5, 15, 10, 0),
                         "mixed slot must carry its completed-bar END time")
        for b in bars:
            self.assertNotIn(999.0, (b["high"], b["low"], b["open"],
                                     b["close"]),
                             "mixed-contract bar leaked into the stream")


class SymbolDecoding(unittest.TestCase):
    def test_raw_symbol_to_yyyymm(self):
        # 2-digit year, direct
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCZ24", 2024, 6),
                         "202412")
        self.assertEqual(dld.raw_symbol_to_yyyymm("NQH25", 2024, 11),
                         "202503")
        # 1-digit year resolved against the record's own reference
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCZ13", 2013, 10),
                         "201312")
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCZ3", 2013, 10),
                         "201312")
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCG4", 2024, 1),
                         "202402")
        # V = October; ref 2019-10 resolves to the same month: 201910
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCV9", 2019, 10),
                         "201910")
        # a code that has already expired vs ref month walks to next decade
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCF9", 2019, 10),
                         "202901")


class QcReconciliation(unittest.TestCase):
    """Guard (c): local Databento bars vs the bundled QC Lean minutes.

    Join convention, established empirically on real Oct-2013 GC data:
    both paths are aggregated to 30m bars keyed on **trade date + ET
    wall-clock end time**. A QC trade file can omit a session's first
    evening minutes (they surface in the next day's file), so all three
    adjacent files are merged and filtered by trade date — under this
    convention 47/47 bars align with ZERO orphans on every sample day.
    Sample = four full weekdays (Tue-Fri 2013-10-08..11): Sunday 10-07 is
    excluded because the git-ignored bundle's 20131007 file starts at
    21:22 ET, missing the Globex evening-reopen minutes DBN carries from
    18:00 — a bundle boundary, not a pipeline defect; Campaign 1's
    population is weekday sessions anyway.

    MEASURED CONTRACT (4 days, 188 common bars — all numbers below are
    measured, not aspirational):
      - high/low within ONE tick on every bar (363/376 field comparisons
        exact) — these build overnight levels and drive touch triggers;
      - open/close within FOUR ticks (measured worst case: one Friday
        16:30 bar-open, Databento first-trade 1270.0 vs AlgoSeek 1270.4);
        `open` is never consumed by the frozen generator at all;
      - full OHLC exact on >=60% of bars (measured 65.4%);
      - root cause of residual drift: Databento GLBX.MDP3 consolidates
        CME Globex + CME ClearPort, Lean's bundle is the AlgoSeek feed —
        day volume ratio ~1.7:1. Bit-exact equality is impossible across
        vendors; the tick ceilings are the meaningful equivalence.
    Any violation fails with printed evidence. The hosted path remains
    the compute authority and the byte-exact generator_v1 gate the
    methodology anchor; this test BOUNDS the local path's equivalence
    instead of silently assuming it. NQ has no local QC coverage (the
    bundle holds es only); ES rides the same CME-globex code path and is
    the documented extension point.
    """

    SAMPLE_DAYS = [date(2013, 10, 8), date(2013, 10, 9),
                   date(2013, 10, 10), date(2013, 10, 11)]
    GC_TICK = 0.10
    MAX_HL_DEV_TICKS = 1
    MAX_OC_DEV_TICKS = 4
    MIN_FULL_EXACT_FRACTION = 0.60
    # front GC expiry through the whole sample window (V13 rolled ~Oct 29)
    SAMPLE_EXPIRY = "201312"

    def _qc_trade_rows(self, days_around, expiry):
        rows = []
        for f in days_around:
            p = os.path.join(dld.QC_FUTURE_DIR, "comex", "minute", "gc",
                             f"{f.strftime('%Y%m%d')}_trade.zip")
            if os.path.exists(p):
                rows += dld.qc_minute_bars("comex", "gc",
                                           f.strftime("%Y%m%d"),
                                           expiry_filter=expiry)
        rows.sort(key=lambda r: r["ts_event_ns"])
        return rows

    def test_gc_sample_days_match(self):
        if not os.path.exists(dld.OHLCV_FILE):
            self.skipTest("databento purchase not on disk (data/ is "
                          "git-ignored); run d48 first")
        if not os.path.exists(dld.DEFINITION_FILE):
            self.skipTest("definition container not on disk; run d48 first")
        instrument_map = dld.load_instrument_map()
        totals = {"bars": 0, "exact": 0}
        checked_days = 0
        for day in self.SAMPLE_DAYS:
            # DBN side: members {D-1, D}; rows whose TRADE DATE == D
            rows_w = dld.dbn_minute_rows(
                dld.OHLCV_FILE, "GC", {day - timedelta(days=1), day})
            rows = [r for r in rows_w
                    if dld.trade_date_of(dld.ts_to_et(r["ts_event_ns"])
                                         ) == day]
            self.assertTrue(rows, f"no DBN GC rows for trade date {day}")
            iids = {r["instrument_id"] for r in rows}
            self.assertEqual(len(iids), 1,
                             f"{day} unexpectedly straddles a roll: {iids}")
            iid = next(iter(iids))
            raw = dld.resolve_raw_symbol(instrument_map, iid, day)
            expiry = dld.raw_symbol_to_yyyymm(raw, day.year, day.month)
            self.assertEqual(expiry, self.SAMPLE_EXPIRY,
                             f"{day}: definition says {raw} -> {expiry}, "
                             "sample window assumed front 201312")
            dbn_bars = dld.build_bars_30m(rows)[0]
            # QC side: merge files {D-1, D, D+1}, same trade-date filter
            qc_bars = dld.build_bars_30m(self._qc_trade_rows(
                (day - timedelta(days=1), day, day + timedelta(days=1)),
                {expiry}))[0]
            qc_bars = [b for b in qc_bars
                       if dld.trade_date_of(b["et"]) == day]
            dbn_by = {b["et"]: b for b in dbn_bars}
            qc_by = {b["et"]: b for b in qc_bars}
            common = sorted(set(dbn_by).intersection(qc_by))
            self.assertGreater(len(common), 40,
                               f"{day}: only {len(common)} common bars — "
                               "alignment lost")
            self.assertEqual(
                sorted(set(dbn_by) - set(qc_by)), [],
                f"{day} dbn-only bars: {sorted(set(dbn_by)-set(qc_by))[:6]}")
            self.assertEqual(
                sorted(set(qc_by) - set(dbn_by)), [],
                f"{day} qc-only bars: {sorted(set(qc_by)-set(dbn_by))[:6]}")
            violations = []
            for et in common:
                a, b = dbn_by[et], qc_by[et]
                for k in ("open", "close"):
                    if abs(a[k] - b[k]) > self.MAX_OC_DEV_TICKS \
                            * self.GC_TICK * 1.001:
                        violations.append(
                            (et, k, a[k], b[k], self.MAX_OC_DEV_TICKS))
                for k in ("high", "low"):
                    if abs(a[k] - b[k]) > self.MAX_HL_DEV_TICKS \
                            * self.GC_TICK * 1.001:
                        violations.append(
                            (et, k, a[k], b[k], self.MAX_HL_DEV_TICKS))
                if all(round(a[k], 4) == round(b[k], 4)
                       for k in ("open", "high", "low", "close")):
                    totals["exact"] += 1
            totals["bars"] += len(common)
            self.assertEqual(
                violations, [],
                f"{day} {raw} (qc {expiry}) measured-contract violations "
                f"(et, field, dbn, qc, ceiling-ticks): {violations[:8]}")
            checked_days += 1
        self.assertEqual(checked_days, len(self.SAMPLE_DAYS),
                         "fewer QC sample days found on disk than expected")
        fraction = totals["exact"] / totals["bars"]
        self.assertGreaterEqual(
            fraction, self.MIN_FULL_EXACT_FRACTION,
            f"only {totals['exact']}/{totals['bars']} bars fully exact "
            f"(< {self.MIN_FULL_EXACT_FRACTION:.0%} measured floor)")
        print(f"QC-reconciliation guard(c): {totals['bars']} common bars "
              f"across {checked_days} days, {totals['exact']} fully exact "
              f"({fraction:.1%}), H/L within "
              f"{self.MAX_HL_DEV_TICKS} tick, O/C within "
              f"{self.MAX_OC_DEV_TICKS} ticks, zero orphan bars")


if __name__ == "__main__":
    unittest.main(verbosity=2)
