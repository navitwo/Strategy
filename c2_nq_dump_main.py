"""Guard (c) cloud extension: dump 30-minute bars from QuantConnect LEAN
for a parameterized (root, window) so the local Databento pipeline can be
reconciled bar-for-bar against the compute authority on markets, roll
sessions, and holiday sessions it cannot cover any other way.

A DATA-DUMP algorithm -- not a strategy, not a Campaign-2 study pass. It
subscribes one future root, places no orders, computes no signals,
touches no ledger. Output: the completed-30m bar table plus the mapping
(SymbolChangedEvent) stream.

TRANSPORT: chart series, not RuntimeStatistics values -- a first run
proved RT string values are silently truncated at 200 chars, exactly the
"terminal status is not fully collected" family of defects. The C1
engine's chart channel is the proven bulk path (it moved 1,121-row
ledgers). Five scatter series ("o", "h", "l", "c", "t" -- 5 unique
names, inside the 10-name tier) on one chart "dump-bars", x = the bar's
naive-ET end datetime as LEAN stores it (a monotone ordering key).
Prices and the bar-end epoch travel as native float64; every futures
tick size here (0.25 NQ / 0.10 GC) and every epoch second (~1.7e9 <<
2^53) round-trips exactly, and the reader asserts per-series
round-trip AND len(values) == the declared count before trusting
anything. Roll events (tiny) ride RuntimeStatistics as one
<200-char string.

Subscription wiring VERBATIM-mirrors scifvg_main.initialize on the
data-bearing axes, so any reconciliation disagreement localizes to the
vendor's data, not to a configuration difference:
    add_future(root, Resolution.MINUTE, extended_market_hours=True,
               data_mapping_mode=DataMappingMode.OPEN_INTEREST,
               data_normalization_mode=DataNormalizationMode.RAW,
               contract_depth_offset=0) + set_filter(0, 182 days)

Aggregation uses LEAN's native self.consolidate(symbol, 30m, handler)
(the same call the frozen engine uses; hand-rolled accumulators with a
trailing unconditional flush fabricate bars -- campaign lesson). Bars
are keyed on the CONSOLIDATED BAR'S OWN end_time, naive New York wall
clock (algorithm tz == exchange tz == NEW_YORK, so stamps are native;
no .astimezone() anywhere -- the documented silent-shift pitfall).
Zero-volume bars are dropped, matching databento_local_data.
build_bars_30m's drop_zero_volume default. Roll capture uses
on_symbol_changed_events -- the identical mechanism the hosted engine
uses to fire generator.on_rollover -- so this dump observes the mapping
exactly as the compute authority does. That is the direct test of
whether Databento's open-interest continuous rule and LEAN's
DataMappingMode.OPEN_INTEREST agree on WHEN the front month rolls.

Windows (frozen, launched by d49; all DEV-only, DEV_END=2024-12-31;
MEASURED holiday/roll structure from the completed fixtures):
  nq-holiday  NQ 2024-11-15..2024-12-05  holiday coverage WITHOUT a
              roll: Thanksgiving 2024-11-28 early-closed (38 bars vs
              46), Black Friday 2024-11-29 early-closed (39), zero
              mapping events. 676 bars.
  nq-roll     NQ 2024-12-16..2024-12-30  the directive's single window
              with BOTH: ROLL NQZ4->NQH5 (local stream: first new
              contract minute 2024-12-18 19:00 ET, inside trade session
              2024-12-19; an earlier assumed 11-25 roll was FALSE --
              measured, which is why nq-holiday carries no roll) AND
              the Christmas holiday (Christmas Eve session 2024-12-24
              early-closed at 13:30 with 39 bars; session 2024-12-25
              fully closed -- absent from the bar table; Dec 26-27
              back to a full 46). Ends 12-30 so no bar belongs to the
              2025-01-01 validation session. 488 bars.
  gc-roll     GC 2020-01-15..2020-01-31  ROLL GCG0->GCJ0 first new
              minute 2020-01-23 19:00 ET (session 2020-01-24), plus
              MLK Day 2020-01-20 (early close, 12 bars). The local
              Lean bundle has no GC files near this date, so the cloud
              dump is the ONLY guard-(c) coverage of a GC roll.
  gc-roll-b   GC 2020-02-01..2020-02-14  follow-on window: LEAN's own
              GC mapping events (measured 2020-02-06/07) and the
              post-convergence bit-exactness that bounds the vendor
              roll-date divergence.
"""
from AlgorithmImports import *  # noqa: F403


def _trade_date_of(et_naive):
    d = et_naive.date()
    return d + timedelta(days=1) if et_naive.hour >= 18 else d


class C2NqDumpAlgorithm(QCAlgorithm):
    def initialize(self):
        root = str(self.get_parameter("dump_root", "NQ")).upper()
        s = str(self.get_parameter("dump_start", "2024-11-15"))
        e = str(self.get_parameter("dump_end", "2024-12-05"))
        sy, sm, sd = (int(x) for x in s.split("-"))
        ey, em, ed = (int(x) for x in e.split("-"))
        self.set_start_date(sy, sm, sd)
        self.set_end_date(ey, em, ed)
        self.set_cash(50000)
        self.set_time_zone(TimeZones.NEW_YORK)

        self.root = root
        self.dump_start = s
        self.dump_end = e
        self.fut = self.add_future(
            root, Resolution.MINUTE, extended_market_hours=True,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            data_normalization_mode=DataNormalizationMode.RAW,
            contract_depth_offset=0)
        self.fut.set_filter(timedelta(0), timedelta(days=182))

        self.bars = []        # (end_et_naive, o, h, l, c)
        self.rolls = []       # (event_et, new_symbol, old_symbol)
        self._dropped_zero = 0
        self.tzcheck = None

        self.consolidate(self.fut.symbol, timedelta(minutes=30),
                         self._on_bar30)

    def _on_bar30(self, consolidated):
        if consolidated.volume <= 0:
            self._dropped_zero += 1
            return
        et = consolidated.end_time.replace(tzinfo=None, microsecond=0)
        if self.tzcheck is None:
            self.tzcheck = str(et)
        self.bars.append((et, float(consolidated.open),
                          float(consolidated.high),
                          float(consolidated.low),
                          float(consolidated.close)))

    def on_symbol_changed_events(self, changes):
        # same mechanism the frozen engine uses for on_rollover; self.time
        # is the algorithm clock (ET tz) at the event slice.
        for change in changes.values():
            self.rolls.append((self.time.replace(tzinfo=None,
                                                 microsecond=0),
                               str(change.new_symbol),
                               str(change.old_symbol)))

    def on_end_of_algorithm(self):
        # chart transport: five scatter series on ONE chart; x = naive
        # ET end datetime (LEAN may render chart x in either domain --
        # it is a monotone ordering key only; the bar-end epoch is
        # transported explicitly in the "t" series below, so the reader
        # never depends on LEAN's timezone interpretation).
        chart = Chart("dump-bars")
        series = {}
        for k in ("o", "h", "l", "c", "t"):
            srs = Series(k, SeriesType.SCATTER)
            chart.add_series(srs)
            series[k] = srs
        # add_point requires a datetime for x (C1 passed naive ET
        # datetimes the same way) -- whatever tz interpretation LEAN
        # applies, it is MONOTONE, so x orders the points; the
        # UNAMBIGUOUS bar-end epoch is transported in the "t" series as
        # an integer (naive ET wall clock treated as UTC epoch seconds;
        # ~1.7e9 << 2^53, exact in float64). The reader decodes t and
        # verifies monotone alignment.
        for et, o, h, l, c in self.bars:
            t_epoch = (et - datetime(1970, 1, 1)).total_seconds()
            series["o"].add_point(et, o)
            series["h"].add_point(et, h)
            series["l"].add_point(et, l)
            series["c"].add_point(et, c)
            series["t"].add_point(et, float(t_epoch))
        self.add_chart(chart)

        RT = self.RuntimeStatistics
        RT["dump_instrument"] = self.root
        RT["dump_start"] = self.dump_start
        RT["dump_end"] = self.dump_end
        RT["n_bars5"] = str(len(self.bars))
        RT["n_dropped_zero"] = str(self._dropped_zero)
        RT["tzcheck_first"] = str(self.tzcheck)
        RT["b5_roll_count"] = str(len(self.rolls))
        RT["b5_rolls"] = "|".join(
            f"{m.isoformat()}={n}>{o}" for m, n, o in self.rolls) or "none"
        # session dates present among published bars (short, but the
        # reader must treat chart x values as the authority)
        dates = sorted({_trade_date_of(et).isoformat()
                        for et, *_ in self.bars})
        RT["b5_days_n"] = str(len(dates))
        RT["b5_days"] = "|".join(dates)  # <=190 chars for windows here
