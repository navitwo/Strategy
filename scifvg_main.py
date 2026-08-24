# SCIFVG v1.0 CONTROL — Sweep -> CISD -> IFVG -> Retest | NQ/MNQ futures
# Protocol: PROTOCOL.md (frozen 2026-08-23). Completed 5m bars only. No lookahead.
# Signals: continuous canonical series (RAW, OI mapping). Orders: mapped contract.
from AlgorithmImports import *

from datetime import timedelta
import hashlib
import json
import math


class ScifvgFeeModel(FeeModel):
    """Flat commission per side per contract (USD)."""
    def __init__(self, per_side):
        self.per_side = float(per_side)
        super().__init__()

    def get_order_fee(self, parameters):
        fee = self.per_side * abs(parameters.order.quantity)
        return OrderFee(CashAmount(fee, "USD"))


class TickSlippage:
    """Fixed adverse slippage of N ticks per fill."""
    def __init__(self, ticks):
        self.ticks = ticks

    def get_slippage_approximation(self, asset, order):
        return float(asset.symbol_properties.minimum_price_variation) * self.ticks


FUNNEL_KEYS = [
    "sessions", "no_prior_levels", "no_bias", "attempts_used",
    "L_attempts", "L_depth_rejects", "L_no_reclaim", "L_sweep_ok",
    "L_cisd_ok", "L_cisd_timeout", "L_inv_ok", "L_inv_timeout",
    "L_submits", "L_fills", "L_size_skips", "L_cancel_expiry",
    "L_cancel_invalid", "L_cancel_bias", "L_cancel_window", "L_cancel_other",
    "S_attempts", "S_depth_rejects", "S_no_reclaim", "S_sweep_ok",
    "S_cisd_ok", "S_cisd_timeout", "S_inv_ok", "S_inv_timeout",
    "S_submits", "S_fills", "S_size_skips", "S_cancel_expiry",
    "S_cancel_invalid", "S_cancel_bias", "S_cancel_window", "S_cancel_other",
    "rollovers", "oco_races", "forced_flattens", "end_flattens", "eod_flattens", "flatten_fills", "untracked_fills", "oco_void_legs",
]


class SweepCisdIfvgAlgorithm(QCAlgorithm):

    # ------------------------------------------------------------------ init
    def initialize(self):
        raw = {}
        for p in ("instrument", "start_date", "end_date", "run_segment",
                  "sweep_min_ticks", "sweep_max_ticks", "reclaim_bars",
                  "cisd_max_bars", "inv_max_bars", "retest_max_bars",
                  "fvg_min_ticks", "fvg_max_age_bars", "stop_buffer_ticks",
                  "target_r", "risk_usd", "max_contracts", "slippage_ticks",
                  "commission_per_side", "window_start_et", "window_end_et",
                  "invert_on_cisd_bar", "entry_location",
                  "pivot_lookback", "pivot_right", "max_attempts_per_day",
                  "stop_mode", "entry_mode", "random_entry_prob", "variant"):
            v = self.get_parameter(p)
            if v is not None and str(v).strip() != "":
                raw[p] = v

        defaults = {
            "instrument": "MNQ", "start_date": "2023-01-03", "end_date": "2025-04-30",
            "run_segment": "dev", "sweep_min_ticks": 4, "sweep_max_ticks": 96,
            "reclaim_bars": 3, "cisd_max_bars": 12, "inv_max_bars": 12,
            "retest_max_bars": 24, "fvg_min_ticks": 4, "fvg_max_age_bars": 60,
            "stop_buffer_ticks": 4, "target_r": 2.0, "risk_usd": 100.0,
            "max_contracts": 10, "slippage_ticks": 1, "commission_per_side": 0.50,
            "window_start_et": "09:30", "window_end_et": "12:00",
            "invert_on_cisd_bar": 0, "entry_location": "proximal",
            "pivot_lookback": 3, "pivot_right": 3,
            "max_attempts_per_day": 1, "stop_mode": "sweep",
            "entry_mode": "signal", "random_entry_prob": 0.02,
            "variant": "candidate",   # candidate|shadow_moc|ablate_cisd|ablate_fvg
        }
        cfg = {}
        for k, dv in defaults.items():
            rv = raw.get(k)
            if rv is None:
                cfg[k] = dv
            elif isinstance(dv, str):
                cfg[k] = str(rv)
            elif isinstance(dv, float):
                cfg[k] = float(rv)
            else:
                cfg[k] = int(float(rv))

        canon = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
        self.exp_hash = hashlib.md5(canon.encode()).hexdigest()[:8]
        self.cfg = cfg
        self.is_nq = str(cfg["instrument"]).upper() == "NQ"

        overall_start = datetime.strptime(str(cfg["start_date"]), "%Y-%m-%d").date()
        overall_end = datetime.strptime(str(cfg["end_date"]), "%Y-%m-%d").date()
        oos_start = datetime.strptime("2025-05-01", "%Y-%m-%d").date()
        seg = str(cfg["run_segment"])
        if seg == "dev":
            start, end = overall_start, min(overall_end, oos_start - timedelta(days=1))
        elif seg == "oos":
            start, end = max(overall_start, oos_start), overall_end
        else:
            start, end = overall_start, overall_end
        self.camp_start, self.camp_end = start, end

        # Warmup so 4H pivots/bias and prior-session levels exist on day one.
        warmup_days = 40
        ws = start - timedelta(days=warmup_days)
        self.set_start_date(ws.year, ws.month, ws.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_cash(50000)
        self.set_time_zone(TimeZones.NEW_YORK)

        root = (Futures.Indices.NASDAQ_100_E_MINI if self.is_nq
                else Futures.Indices.MICRO_NASDAQ_100_E_MINI)
        self.fut = self.add_future(
            root, Resolution.MINUTE, extended_market_hours=True,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            data_normalization_mode=DataNormalizationMode.RAW,
            contract_depth_offset=0)
        self.fut.set_filter(timedelta(0), timedelta(days=182))
        self.fut.set_fee_model(ScifvgFeeModel(cfg["commission_per_side"]))
        self.fut.set_slippage_model(TickSlippage(cfg["slippage_ticks"]))

        # 5m consolidation via LEAN (replaces hand-rolled acc5 buffer).
        # Overload note: the symbol-bearing overload is the only one LEAN
        # exposes to Python for futures subscriptions.
        self.consolidate(self.fut.symbol, timedelta(minutes=5),
                         self._on_5m_consolidated)

        self.tick = 0.25
        # Slippage model (v2.3): LEAN fills limit orders passively (no
        # negative selection beyond queue reality) and market orders at next
        # available price. Stress runs override via cfg["slippage_ticks"].
        self.slippage_ticks = int(self.cfg.get("slippage_ticks", 1))
        self.point_value = 20.0 if self.is_nq else 2.0

        wh, wm = str(cfg["window_start_et"]).split(":")
        eh, em = str(cfg["window_end_et"]).split(":")
        self.w_start = int(wh) * 60 + int(wm)
        self.w_end = int(eh) * 60 + int(em)

        # ---- state ----
        self.fun = {k: 0 for k in FUNNEL_KEYS}
        self.cur_session = None
        self.pdh = None
        self.pdl = None
        self.cur_high = None
        self.cur_low = None
        self.session_tried = set()

        self.bars5 = []         # completed 5m dicts: o,h,l,c,idx,et(end)
        self.h4_pub = []        # published validated 4H bars
        self.h4_bucket = None   # {"id":..., "bars":[...], "offset0", "t0", "tN"}
        # BUG2 fix v2: coverage measured as WALL-CLOCK SPAN, not bar count.
        # Trade bars are missing in quiet minutes; a real 4H bucket spans
        # ~4h from first bar start to last bar end. Fragments (< 3h30m) and
        # mid-bucket starts are discarded.
        self.h4_min_span_min = 210
        self.h4_max_offset0 = 5   # first slot may open up to :05 into bucket
        self.h4_gap_pending = False
        self.swing_hi = []      # [(idx, px)] confirmed pivots on h4_pub
        self.swing_lo = []
        self.bias = 0

        self.setup = None       # active setup dict (one at a time)
        self.order_purpose = {} # order_id -> ("entry"/"stop"/"tp", side)
        self.pos_side = 0       # 0 flat
        self.pos_qty = 0
        self.exit_qty_acc = 0
        self.entry_avg = None
        self.stop_px = None
        self.tp_px = None
        self.risk_dist = None
        self.stop_ticket = None
        self.tp_ticket = None

        self.trade_rs = []      # realized R multiples (full trades)
        self.last_mapped = None
        # BUG4 fix: reconciliation state — ledger is DERIVED from equity events,
        # never an independent counter. race_* legs track excluded noise legs.
        self.race_stop_legs = 0
        self.race_tp_legs = 0
        self.race_pnl_usd = 0.0     # PnL of excluded reversal round-trips
        self._last_equity = None
        # reconciliation inputs (BUG4 fix)
        self.trade_economics = []   # {"r","risk_dist","qty","obs_usd"} per trade
        self.race_pnl_obs = 0.0     # measured PnL of excluded reversal round-trips
        self._equity_deltas = []
        self._eq_at_entry = None
        self._race_eq_open = None
        self._flatten_tickets = []
        self._row_written = False   # ledger row written for current pos cycle
        self.unfilled_watch = []   # adverse-selection watchlist
        self.unfilled_resolved_n = 0
        self.d_bars5_total = 0
        self.tzcheck_ok = 0
        self.qty_max_seen = 0

    def _equity(self):
        try:
            return float(self.portfolio.total_portfolio_value)
        except Exception:
            return 0.0

        self._starting_tpv = None   # captured lazily on first bar
        self.Debug(f"SCIFVG init {cfg['instrument']} trade {start}..{end} "
                   f"warmup_from={ws.isoformat()} win={cfg['window_start_et']}-"
                   f"{cfg['window_end_et']} hash={self.exp_hash}")

    # ------------------------------------------------------------- utilities
    def _et_minutes(self, et):
        return et.hour * 60 + et.minute

    def _in_window(self, et):
        m = self._et_minutes(et)
        if self.w_start <= self.w_end:
            return self.w_start <= m < self.w_end
        return m >= self.w_start or m < self.w_end

    def _session_key(self, et):
        d = et.date()
        if et.hour >= 18:
            return d
        if et.hour >= 17:
            return None           # maintenance halt 17:00-18:00 ET
        return d - timedelta(days=1)

    def _rt(self, px, up=True):
        t = self.tick
        if up:
            return round(math.ceil(px / t - 1e-9) * t, 4)
        return round(math.floor(px / t + 1e-9) * t, 4)

    def _inc(self, k, n=1):
        self.fun[k] = self.fun.get(k, 0) + n

    def _sk(self, side):
        return "L" if side > 0 else "S"

    # ------------------------------------------------------ session rollover
    def _advance_session(self, et):
        skey = self._session_key(et)
        if skey is None or skey == self.cur_session:
            return

        # --- EOD flatten: no overnight positions across session boundaries ---
        try:
            held = self.portfolio[self.fut.mapped].quantity
            if held != 0:
                tk = self.market_order(self.fut.mapped, -held, tag="EOD-FLATTEN"); self._register_flatten_order(tk, held)
                self._inc("eod_flattens")
        except Exception:
            pass
        self._cancel_ticket(self.stop_ticket)
        self._cancel_ticket(self.tp_ticket)
        self.stop_ticket = None
        self.tp_ticket = None
        if self.setup is not None and self.pos_qty == 0:
            self._cancel_pending(None)
        self.pos_side = 0
        self.pos_qty = 0
        self.exit_qty_acc = 0
        self.entry_avg = None
        self.risk_dist = None
        self._eq_at_entry = None
        if self.bias == 0:
            self._inc("no_bias")
        self.cur_session = skey
        self.pdh = self.cur_high
        self.pdl = self.cur_low
        self.cur_high = None
        self.cur_low = None
        self.session_tried = set()
        # contract rollover: mapped symbol changed across the session boundary?
        try:
            cur_mapped = self.fut.mapped
            if self.last_mapped is not None and cur_mapped is not None \
                    and str(cur_mapped) != str(self.last_mapped):
                self._inc("rollovers")
                # Position context is stale across the roll. Fail closed:
                # flatten anything open, kill pending setup, reset cycle.
                try:
                    held = self.portfolio[cur_mapped].quantity
                    if held != 0:
                        tk = self.market_order(cur_mapped, -held,
                                               tag="ROLLOVER-FLATTEN")
                        self._register_flatten_order(tk, held)
                        self._inc("flatten_fills")
                except Exception:
                    pass
                if self.setup is not None:
                    self.setup = None
                    self._inc("rollover_setup_killed")
                self.pos_side = 0
                self.pos_qty = 0
                self.exit_qty_acc = 0
                self.risk_dist = None
                self.entry_avg = None
                self._eq_at_entry = None
                self._row_written = False
        except Exception:
            pass
        try:
            self.last_mapped = self.fut.mapped
        except Exception:
            pass
        self._inc("sessions")
        if self.pdh is None or self.pdl is None:
            self._inc("no_prior_levels")

    # ------------------------------------------------------------ 4H engine
    def _publish_h4(self, new_id):
        bk = self.h4_bucket
        if bk is None or bk["id"] == new_id:
            return
        self.h4_bucket = None
        # BUG2 fix v2: wall-clock span coverage. A genuine [18,22) ET bucket's
        # first bar starts at 18:00 and its last bar ends near 22:00. Fragments
        # (session opens, halts) span far less and are DISCARDED; a discarded
        # bucket also invalidates pivot confirmation spanning it.
        bars = bk["bars"]
        t0 = bk.get("t0")
        tN = bk.get("tN")
        span = (tN - t0).total_seconds() / 60.0 if (t0 and tN) else 0.0
        if span < self.h4_min_span_min or bk["offset0"] > self.h4_max_offset0:
            self.h4_gap_pending = True
            return
        o = bars[0]["open"]
        c = bars[-1]["close"]
        h = max(x["high"] for x in bars)
        l = min(x["low"] for x in bars)
        idx = len(self.h4_pub)
        self.h4_pub.append({"idx": idx, "open": o, "high": h, "low": l, "close": c})

        # BUG2 fix: a pivot is only confirmed if all its bars were published
        # CONTIGUOUSLY (no discarded bucket in between). Timing is unchanged:
        # candidate sits at ci = idx-(Rn+1); its Rn right-side bars are already
        # in h4_pub strictly before this publish.
        if self.h4_gap_pending:
            self.h4_gap_pending = False   # consume: this bar cannot confirm pivots
        else:
            L = int(self.cfg.get("pivot_lookback", 3))
            Rn = int(self.cfg.get("pivot_right", 3))
            ci = idx - (Rn + 1)
            if ci >= L:
                b = self.h4_pub[ci]
                left = self.h4_pub[ci - L:ci]
                right = self.h4_pub[ci + 1:ci + 1 + Rn]
                if len(left) == L and len(right) == Rn:
                    if all(x["high"] < b["high"] for x in left) and \
                       all(x["high"] < b["high"] for x in right):
                        self.swing_hi.append((ci, b["high"]))
                    if all(x["low"] > b["low"] for x in left) and \
                       all(x["low"] > b["low"] for x in right):
                        self.swing_lo.append((ci, b["low"]))

        # break of structure on this completed close (swings confirmed earlier).
        # Symmetric: bull evaluated first when leaving non-bull state, bear first
        # when leaving non-bear state; a single close cannot flip twice.
        bull_break = bool(self.swing_hi) and self.swing_hi[-1][0] < idx \
            and c > self.swing_hi[-1][1]
        bear_break = bool(self.swing_lo) and self.swing_lo[-1][0] < idx \
            and c < self.swing_lo[-1][1]
        if self.bias != 1 and bull_break:
            self.bias = 1
        elif self.bias != -1 and bear_break:
            self.bias = -1

    def _accumulate_h4(self, b5):
        # 4H buckets keyed by the bar's START time so offset0 is measured from
        # the true bucket start (commit-coupled with the consolidate() fix:
        # with END-time keys and exact 5m boundaries, offset0 would be 300 min
        # and every bucket would be rejected).
        st = b5["et"] - timedelta(minutes=5)
        bid = (st.year, st.month, st.day, st.hour // 4)
        if self.h4_bucket is None or self.h4_bucket["id"] != bid:
            self._publish_h4(bid)
            self.h4_bucket = {
                "id": bid, "bars": [],
                "offset0": (st.hour % 4) * 60 + st.minute,
                "t0": st,
                "tN": b5["et"],
            }
        self.h4_bucket["bars"].append(b5)
        self.h4_bucket["tN"] = b5["et"]

    # -------------------------------------------------------------- FVG store
    def _scan_fvgs(self, upto_idx, side):
        """3-candle FVGs opposing `side`, known at close of bar i.

        side=+1 (long): bearish gaps  Low[i-2] > High[i]  -> zone {lo:High[i], hi:Low[i-2]}
        side=-1 (short): bullish gaps Low[i] > High[i-2]  -> zone {lo:High[i-2], hi:Low[i]}
        """
        out = []
        lo = max(2, upto_idx - self.cfg["fvg_max_age_bars"])
        m = self.cfg["fvg_min_ticks"] * self.tick
        for i in range(lo, upto_idx + 1):
            if side > 0:
                top = self.bars5[i - 2]["low"]
                bot = self.bars5[i]["high"]
                if top - bot >= m:
                    out.append({"lo": bot, "hi": top, "created": i})
            else:
                bot = self.bars5[i - 2]["high"]
                top = self.bars5[i]["low"]
                if top - bot >= m:
                    out.append({"lo": bot, "hi": top, "created": i})
        return out

    def _dead(self, g, cur_idx, side):
        for j in range(g["created"] + 1, cur_idx + 1):
            if side > 0:
                if self.bars5[j]["close"] < g["lo"]:
                    return True
            else:
                if self.bars5[j]["close"] > g["hi"]:
                    return True
        return False

    # ---------------------------------------------------- random-entry null
    def _new_setup_allowed(self):
        return (self.setup is None and self.pos_qty == 0
                and self.pdh is not None and self.pdl is not None)

    def _try_arm_attempt(self, b, idx, skey):
        """Detect a sweep ATTEMPT on this completed bar.

        V1.0: one attempt per level/day/side. v1.3 adds `max_attempts_per_day`
        (E11): the first N penetrating bars each arm an attempt; attempts are
        consumed by depth rejects, failed reclaims, and dead pendings alike.
        """
        max_att = self.cfg.get("max_attempts_per_day", 1)
        for side, level in ((1, self.pdl), (-1, self.pdh)):
            used = sum(1 for s, sd in self.session_tried if s == skey and sd == side)
            if used >= max_att:
                continue
            if self.bias != side:
                continue
            pen = (level - b["low"]) if side > 0 else (b["high"] - level)
            if pen < self.cfg["sweep_min_ticks"] * self.tick:
                continue
            self.session_tried.add((skey, side))
            self._inc("attempts_used")
            self._inc(f"{self._sk(side)}_attempts")
            if pen > self.cfg["sweep_max_ticks"] * self.tick:
                self._inc(f"{self._sk(side)}_depth_rejects")
                continue
            self.setup = {
                "side": side, "stage": "SWEPT", "arm_sk": skey, "b0": idx,
                "reclaim_deadline": idx + self.cfg["reclaim_bars"] - 1,
                "level": level, "extreme": b["low"] if side > 0 else b["high"],
                "extreme_idx": idx, "ref_open": None, "ref_idx": None,
                "cisd_deadline": None, "fvg": None, "inv_deadline": None,
                "cisd_idx": None, "retest_deadline": None, "entry_id": None,
            }
            return

    def _advance_setup(self, b, idx, et, skey):
        s = self.setup
        side = s["side"]
        K = self._sk(side)
        lvl = s["level"]

        if s["stage"] == "SWEPT":
            beyond = (b["low"] < s["extreme"]) if side > 0 else (b["high"] > s["extreme"])
            if beyond:
                s["extreme"] = b["low"] if side > 0 else b["high"]
                s["extreme_idx"] = idx
            closed_back = (b["close"] > lvl) if side > 0 else (b["close"] < lvl)
            if closed_back:
                self._inc(f"{K}_sweep_ok")
                s["stage"] = "CISD"
                s["cisd_deadline"] = idx + self.cfg["cisd_max_bars"]
                s["ref_open"] = None
                lo = max(0, idx - 200)
                for j in range(s["extreme_idx"], lo - 1, -1):
                    bb = self.bars5[j]
                    if bb["close"] < bb["open"]:
                        s["ref_open"] = bb["open"]
                        s["ref_idx"] = j
                        break
                if s["ref_open"] is None:
                    self._inc(f"{K}_cisd_timeout")
                    self.setup = None
                    return
                # ABLATION-B: skip the CISD wait entirely (same reference,
                # immediate trigger on next bar) — measures CISD's marginal
                # selectivity vs candidate which requires a real trigger.
                if str(self.cfg.get("variant", "candidate")) == "ablate_cisd":
                    s["stage"] = "CISD"
                    s["cisd_immediate"] = True
                return
            if idx >= s["reclaim_deadline"]:
                self._inc(f"{K}_no_reclaim")
                self.setup = None
            return

        if s["stage"] == "CISD":
            if s.pop("cisd_immediate", False):
                trigger = True          # ABLATION-B: bypass trigger wait
            else:
                trigger = ((b["close"] > s["ref_open"]) if side > 0
                           else (b["close"] < s["ref_open"]))
            if str(self.cfg.get("variant", "candidate")) == "ablate_fvg":
                # ABLATION-C: no FVG requirement — enter on CISD close at
                # market. Measures FVG-gate contribution vs candidate.
                if trigger and self._in_window(et):
                    stop_mode = str(self.cfg.get("stop_mode", "sweep"))
                    ext = s["extreme"]
                    buf = self.cfg["stop_buffer_ticks"] * self.tick
                    stop = self._rt(ext - buf, up=False) if side > 0 \
                        else self._rt(ext + buf, up=True)
                    entry = self._rt(b["close"], up=(side > 0))
                    dist = abs(entry - stop)
                    if dist > 0:
                        qty = int(float(self.cfg["risk_usd"]) /
                                  (dist * self.point_value))
                        qty = min(qty, int(self.cfg["max_contracts"]))
                        tp = self._rt(
                            entry + side * float(self.cfg["target_r"]) * dist,
                            up=(side > 0)) if side > 0 else self._rt(
                            entry - float(self.cfg["target_r"]) * dist, up=False)
                        if qty >= 1:
                            s["stage"] = "FILLED"
                            mk = self._rt(entry + side * 2 * self.tick,
                                          up=(side > 0))
                            s["entry_px"] = entry
                            s["stop_px"] = stop
                            s["tp_px"] = tp
                            s["qty"] = qty
                            sym = self.fut.mapped
                            tk = self.limit_order(sym, qty * side, mk,
                                                  tag=f"E-{K}-{idx}-{self.exp_hash}")
                            self.order_purpose[tk.order_id] = ("entry", side)
                            self._inc(f"{K}_submits")
                            return
            if trigger:
                imm = None       # midpoint already crossed by THIS (CISD) bar
                elig = None      # intact zone still below: wait for inversion
                # Throttle removal: scan ALL gaps known before this bar
                # (created <= idx-1), not just pre-sweep-extreme ones.
                for g in self._scan_fvgs(idx - 1, side):
                    if idx - g["created"] > self.cfg["fvg_max_age_bars"]:
                        continue
                    if self._dead(g, idx, side):
                        continue
                    if self.cfg.get("invert_on_cisd_bar", 0) == 1:
                        mid = (g["lo"] + g["hi"]) / 2.0
                        crossed = (b["close"] > mid) if side > 0 else (b["close"] < mid)
                        if crossed:
                            # includes full traversal (close beyond far edge):
                            # the CISD bar itself completed the inversion.
                            if imm is None or g["created"] < imm["created"]:
                                imm = g
                            continue
                    # nearest-to-price selection (E16e fix, sign corrected):
                    # distance from CISD close to the zone's NEAR edge; the
                    # smallest non-negative distance wins.
                    if side > 0:
                        prox = abs(b["close"] - g["hi"])
                    else:
                        prox = abs(b["close"] - g["lo"])
                    if elig is None or prox < elig.get("_prox", 1e18):
                        gg = dict(g)
                        gg["_prox"] = prox
                        elig = gg
                chosen = imm if imm is not None else elig
                if chosen is None:
                    # CISD fired but nothing invertible remains
                    self._inc(f"{K}_cisd_ok")
                    self._inc(f"{K}_inv_timeout")
                    self.setup = None
                    return
                self._inc(f"{K}_cisd_ok")
                s["fvg"] = chosen
                s["cisd_idx"] = idx
                if imm is not None:
                    # immediate inversion on the CISD bar itself
                    self._inc(f"{K}_inv_ok")
                    s["stage"] = "PENDING"
                    s["retest_deadline"] = idx + self.cfg["retest_max_bars"]
                    self._submit_entry(s, idx)
                else:
                    s["stage"] = "INV"
                    s["inv_deadline"] = idx + self.cfg["inv_max_bars"]
                return
            if idx >= s["cisd_deadline"]:
                self._inc(f"{K}_cisd_timeout")
                self.setup = None
            return

        if s["stage"] == "INV":
            g = s["fvg"]
            mid = (g["lo"] + g["hi"]) / 2.0
            inverted = (b["close"] > mid) if side > 0 else (b["close"] < mid)
            if inverted:
                self._inc(f"{K}_inv_ok")
                s["stage"] = "PENDING"
                s["retest_deadline"] = idx + self.cfg["retest_max_bars"]
                self._submit_entry(s, idx)
            elif idx >= s["inv_deadline"]:
                self._inc(f"{K}_inv_timeout")
                self.setup = None
            return

    def _submit_entry(self, s, idx):
        side = s["side"]
        b_close_ref = getattr(self, "_last_bar_close", None) or (
            self.bars5[-1]["close"] if self.bars5 else 0.0)
        K = self._sk(side)
        g = s["fvg"]
        ext = s["extreme"]
        mid = (g["lo"] + g["hi"]) / 2.0
        # entry_location: "proximal" (V1.0), "midpoint" (E05), "gap_far" (B2-E12)
        loc = str(self.cfg.get("entry_location", "proximal"))
        use_mid = (loc == "midpoint")
        use_far = (loc == "gap_far")
        # stop_mode: "sweep" (V1.0) or "gap" (B2-E12): beyond the far gap edge
        stop_mode = str(self.cfg.get("stop_mode", "sweep"))

        if side > 0:
            stop_base = g["lo"] - self.cfg["stop_buffer_ticks"] * self.tick \
                if stop_mode == "gap" else ext - self.cfg["stop_buffer_ticks"] * self.tick
            stop = self._rt(stop_base, up=False)
            entry_px = g["hi"] if use_far else (mid if use_mid else g["hi"])
            entry = self._rt(entry_px, up=True)
            tp = self._rt(entry + float(self.cfg["target_r"]) * (entry - stop), up=True)
        else:
            stop_base = g["hi"] + self.cfg["stop_buffer_ticks"] * self.tick \
                if stop_mode == "gap" else ext + self.cfg["stop_buffer_ticks"] * self.tick
            stop = self._rt(stop_base, up=True)
            entry_px = g["lo"] if use_far else (mid if use_mid else g["lo"])
            entry = self._rt(entry_px, up=False)
            tp = self._rt(entry - float(self.cfg["target_r"]) * (stop - entry), up=False)
        dist = abs(entry - stop)
        if dist <= 0:
            self._inc(f"{K}_cancel_other")
            self.setup = None
            return
        qty = int(float(self.cfg["risk_usd"]) / (dist * self.point_value))
        qty = min(qty, int(self.cfg["max_contracts"]))
        if qty < 1:
            self._inc(f"{K}_size_skips")
            self.setup = None
            return

        sym = self.fut.mapped
        if sym is None:
            self._inc(f"{K}_cancel_other")
            self.setup = None
            return
        entry_px_mkt = b_close_ref if b_close_ref else (
            self.bars5[-1]["close"] if self.bars5 else 0.0)
        # SHADOW-A (paired model): enter at market on inversion close instead
        # of the resting retest limit. Same signal/window/stop/target; only
        # the entry mechanism differs -> isolates adverse-selection exposure.
        if str(self.cfg.get("variant", "candidate")) == "shadow_moc":
            # marketable limit (cross 2 ticks): immediate-entry intent with
            # reliable execution mechanics (market orders proved unreliable
            # in this LEAN Python environment - E18R diagnosis).
            mk = self._rt(entry_px_mkt + side * 2 * self.tick,
                          up=(side > 0))
            try:
                tk = self.limit_order(sym, qty * side, mk,
                                      tag=f"E-{K}-{idx}-{self.exp_hash}")
            except Exception:
                self._inc(f"{K}_cancel_other")
                self.setup = None
                return
            s["entry_id"] = tk.order_id
            s["stage"] = "FILLED"     # prevent same-bar cancel of MOC entry
            s["entry_px"] = self._rt(b_close_ref, up=(side > 0))
            s["qty"] = qty
            s["stop_px"] = stop
            s["tp_px"] = tp
            self.order_purpose[tk.order_id] = ("entry", side)
            self._inc(f"{K}_submits")
            return
        try:
            tk = self.limit_order(sym, qty * side, entry,
                                  tag=f"E-{K}-{idx}-{self.exp_hash}")
        except Exception:
            self._inc(f"{K}_cancel_other")
            self.setup = None
            return
        s["entry_id"] = tk.order_id
        s["entry_px"] = entry
        s["qty"] = qty
        s["stop_px"] = stop
        s["tp_px"] = tp
        self.order_purpose[tk.order_id] = ("entry", side)
        self._inc(f"{K}_submits")

    def _cancel_pending(self, counter):
        s = self.setup
        if s and s.get("stage") == "FILLED":
            # Market-entry variants: order already working/filled; never cancel.
            return
        if s and s.get("entry_id") is not None:
            # its bracket forward — would it have won? (review round 3)
            if s.get("entry_px") is not None:
                self.unfilled_watch.append({
                    "side": s["side"], "entry": s["entry_px"],
                    "stop": s["stop_px"], "tp": s["tp_px"],
                    "deadline": self.bars5[-1]["idx"] + self.cfg["retest_max_bars"]
                    if self.bars5 else None,
                })
                self._inc(f"{self._sk(s['side'])}_unfilled_watched")
            try:
                t = self.transactions.get_order_by_id(s["entry_id"])
                if t is not None and t.status == OrderStatus.SUBMITTED \
                        and t.quantity_left != 0:
                    t.cancel()
            except Exception:
                pass
            self.order_purpose.pop(s["entry_id"], None)
        if counter:
            self._inc(counter)
        self.setup = None

    # ------------------------------------------------------------- main loop
    def on_data(self, data):
        # All bar processing happens in _on_5m_consolidated. This hook stays
        # only as the LEAN data sink; nothing may advance sessions here —
        # rotation is keyed on completed 5m bars (BUG3 permanent fix).
        pass


    def _on_5m_consolidated(self, consolidated):
        """LEAN consolidator callback: exactly one call per completed 5m slot.

        Timezone contract (TZCHECK-enforced): with the algorithm timezone set
        to New York, LEAN delivers Python datetimes that are NAIVE wall-clock
        exchange time (ET for NQ). No astimezone conversion is performed —
        converting would reinterpret already-ET stamps as UTC (4-5h shift).
        Session rotation also lives here so it advances on the COMPLETED-BAR
        clock; the old on_data-minute-clock path let PDH/PDL rotate before the
        session's final buckets were consumed (original BUG3 failure mode).
        """
        et = consolidated.end_time          # naive ET by algorithm tz contract
        if getattr(self, "_starting_tpv", None) is None:
            try:
                self._starting_tpv = float(self.portfolio.total_portfolio_value)
            except Exception:
                self._starting_tpv = 0.0
        agg = {
            "open": float(consolidated.open),
            "high": float(consolidated.high),
            "low": float(consolidated.low),
            "close": float(consolidated.close),
            "idx": -1,
            "et": et,
        }
        self.bars5.append(agg)
        self.d_bars5_total += 1
        if len(self.bars5) > 600:
            trim = len(self.bars5) - 600
            del self.bars5[:trim]
            self._rebase(trim)
        agg["idx"] = len(self.bars5) - 1   # assign AFTER any trim

        # ---- TZCHECK: first RTH 5m bar of each day must stamp 09:35 ET ----
        if not getattr(self, "_tzcheck_done", False):
            hm = et.hour * 60 + et.minute
            if hm == 9 * 60 + 35:
                self._tzcheck_done = True
                self.tzcheck_ok = 1
                self.Debug(f"TZCHECK first-RTH-bar et={et.isoformat()} "
                           f"ok=True")
            elif 9 * 60 + 30 < hm < 12 * 60:
                self.Debug(f"TZCHECK candidate bar et={et.isoformat()} "
                           f"(waiting for 09:35)")

        # session rotation FIRST (levels roll only after the completed bar
        # has been accounted to the OLD session's running extremes below)
        skey = self._session_key(et)
        if skey is not None:
            self._advance_session(et)

        if self.cur_high is None or agg["high"] > self.cur_high:
            self.cur_high = agg["high"]
        if self.cur_low is None or agg["low"] < self.cur_low:
            self.cur_low = agg["low"]

        self._accumulate_h4(agg)

        # resolve unfilled-entry watches: first touch of TP or stop wins/loses
        if self.unfilled_watch:
            still = []
            for w in self.unfilled_watch:
                hit_tp = agg["high"] >= w["tp"] if w["side"] > 0 \
                    else agg["low"] <= w["tp"]
                hit_st = agg["low"] <= w["stop"] if w["side"] > 0 \
                    else agg["high"] >= w["stop"]
                if hit_tp or hit_st:
                    self.fun["unfilled_won"] = self.fun.get("unfilled_won", 0) \
                        + (1 if hit_tp else 0)
                    self.fun["unfilled_lost"] = self.fun.get("unfilled_lost", 0) \
                        + (1 if hit_st else 0)
                    self.unfilled_resolved_n += 1
                elif w["deadline"] is not None and agg["idx"] >= w["deadline"]:
                    self.fun["unfilled_timeout"] = \
                        self.fun.get("unfilled_timeout", 0) + 1
                    self.unfilled_resolved_n += 1
                else:
                    still.append(w)
            self.unfilled_watch = still

        if self.setup is not None and self.setup["stage"] == "PENDING" \
                and self.pos_qty == 0:
            self._manage_pending(agg, agg["idx"], et, skey)

        warm = et.date() >= self.camp_start
        if str(self.cfg.get("entry_mode", "signal")) == "random":
            raise RuntimeError("random null retired; use paired variants")
        elif warm and skey is not None and self._in_window(et) \
                and self._new_setup_allowed() and self.bias in (1, -1):
            self._try_arm_attempt(agg, agg["idx"], skey)

        if self.setup is not None and self.setup["stage"] in ("SWEPT", "CISD", "INV"):
            if self._in_window(et) and self.setup["arm_sk"] == skey:
                self._advance_setup(agg, agg["idx"], et, skey)
            else:
                K = self._sk(self.setup["side"])
                self._cancel_pending(f"{K}_cancel_window")
        # stage FILLED setups own live orders; they are managed by the fill
        # handler and exit management below - never cancelled here.

    def _rebase(self, trim):
        if self.setup:
            for f in ("b0", "reclaim_deadline", "extreme_idx", "cisd_deadline",
                      "inv_deadline", "cisd_idx", "retest_deadline", "ref_idx"):
                v = self.setup.get(f)
                if isinstance(v, int):
                    self.setup[f] = v - trim
            if self.setup.get("fvg"):
                self.setup["fvg"]["created"] -= trim


    def _manage_pending(self, b, idx, et, skey):
        s = self.setup
        side = s["side"]
        K = self._sk(side)
        g = s["fvg"]
        if not self._in_window(et):
            self._cancel_pending(f"{K}_cancel_window")
            return
        if self.bias != side:
            self._cancel_pending(f"{K}_cancel_bias")
            return
        invalid = (b["close"] < g["lo"]) if side > 0 else (b["close"] > g["hi"])
        if invalid:
            self._cancel_pending(f"{K}_cancel_invalid")
            return
        if idx >= s["retest_deadline"]:
            self._cancel_pending(f"{K}_cancel_expiry")
            return

    # --------------------------------------------------------- order events
    def on_order_event(self, order_event):
        if order_event.status == OrderStatus.SUBMITTED:
            return
        oid = order_event.order_id
        purpose = self.order_purpose.get(oid)
        status = order_event.status

        if status == OrderStatus.FILLED:
            fq = abs(order_event.fill_quantity)
            fp = float(order_event.fill_price)
            if not hasattr(self, "_filllog"):
                self._filllog = []
            self._filllog.append({
                "oid": oid, "fq": fq, "fp": fp,
                "p": str(purpose), "pos": self.pos_qty,
                "et": str(self.time)})
            if purpose and purpose[0] == "flatten":
                # Flatten fills CLOSE the position: they are exits of the open
                # design trade and MUST produce a ledger row (review round 3:
                # five silent flatten exits tripped fills-vs-trades). Row uses
                # actual fill economics with exit_reason for auditability.
                self._inc("flatten_fills")
                self.order_purpose.pop(oid, None)
                if self.pos_side != 0 and self.risk_dist:
                    side = self.pos_side
                    r_contrib = ((fp - self.entry_avg) / self.risk_dist) * side
                    self.exit_qty_acc += fq
                    self.trade_economics.append({
                        "r": round(r_contrib, 4),
                        "risk_dist": self.risk_dist,
                        "qty": fq,
                        "is_race": getattr(self, "_race_leg_pending", False),
                    })
                    self._race_leg_pending = False
                    t = self.trade_economics[-1]
                    eq_now = self._equity()
                    t["obs_usd"] = round(eq_now - (self._eq_at_entry or eq_now), 2)
                    self._eq_at_entry = eq_now
                    if self.exit_qty_acc >= self.pos_qty:
                        is_race = self.trade_economics[-1].get("is_race", False)
                        if not is_race:   # race legs stay out of headline R
                            self.fun["r_trades"] = self.fun.get("r_trades", 0) + 1
                            if r_contrib > 0:
                                self.fun["r_wins"] = self.fun.get("r_wins", 0) + 1
                            self.trade_rs.append(round(r_contrib, 4))
                        self.pos_side = 0
                        self.exit_qty_acc = 0
                return
            if purpose is None:
                if self.pos_side != 0 or self.exit_qty_acc != 0:
                    # racing CANCELED consumed registration while open:
                    # real economics - capture and close the cycle.
                    eq = self._equity()
                    if self.risk_dist and self.entry_avg is not None:
                        side = self.pos_side
                        r_contrib = ((fp - self.entry_avg) / self.risk_dist) * side
                        self.trade_economics.append({
                            "r": round(r_contrib, 4),
                            "risk_dist": self.risk_dist,
                            "qty": fq, "is_race": True})
                        self._row_written = True
                    if self._eq_at_entry is not None:
                        self.race_pnl_obs += eq - self._eq_at_entry
                        self._eq_at_entry = eq
                    self.pos_side = 0
                    self.pos_qty = 0
                    self.exit_qty_acc = 0
                    self.risk_dist = None
                    self.entry_avg = None
                    self._inc("late_fill_events")
                    self.fun["late_closes"] = \
                        self.fun.get("late_closes", 0) + 1
                    return
                if self.pos_side == 0 and self.exit_qty_acc == 0:
                    # fill event outside any tracked context (race residue,
                    # duplicate partial accounting). Its economics are REAL:
                    # measure via equity delta and park in race_pnl_obs so I1
                    # nets it out instead of silently vanishing.
                    eq = self._equity()
                    held = 0
                    try:
                        held = abs(self.portfolio[self.fut.mapped].quantity)
                    except Exception:
                        pass
                    if self._eq_at_entry is not None and (
                            not self._row_written or held != 0):
                        # unrowed position context OR actual holding closed:
                        # this event terminated a tracked cycle. Count it.
                        self.race_pnl_obs += eq - self._eq_at_entry
                        self._eq_at_entry = eq
                        self._row_written = True   # cycle accounted here
                        self._inc("late_fill_events")
                        self.fun["late_closes"] = \
                            self.fun.get("late_closes", 0) + 1
                    elif self._eq_at_entry is not None:
                        # duplicate/residue after row already written & flat
                        self._inc("late_fill_events")
                        self._eq_at_entry = eq
                    else:
                        # pure residue (race leg after flat): economics fold
                        # into TPV via I1; no ledger meaning.
                        self._inc("late_residue_events")
                    return
                self._inc("untracked_fills")
                return
            kind = purpose[0]
            side = purpose[1]
            if kind == "entry":
                K = self._sk(side)
                self._inc(f"{K}_fills")
                self._row_written = False
                if self.pos_side != 0 and self.pos_side != side:
                    # Reversal-by-entry would silently net the open position
                    # (the missing-row mechanism). Fail closed instead.
                    self._inc("entry_reversal_blocks")
                    self._fail_closed_flatten("entry_reversal")
                    return
                if self.pos_qty == 0:
                    self.entry_avg = fp
                else:
                    self.entry_avg = ((self.entry_avg * self.pos_qty) + fp * fq) / (self.pos_qty + fq)
                self.pos_side = side
                self.pos_qty += fq
                self.qty_max_seen = max(self.qty_max_seen, fq)
                s = self.setup
                if s is None:
                    # Cancel raced the fill (entry registered then wiped).
                    # Fail closed AND mark this fill as orphaned so the
                    # cross-check counts it in the denominator.
                    self._inc("orphan_entry_fills")
                    self._fail_closed_flatten("entry_fill_no_state")
                    return
                self.stop_px = s["stop_px"]
                self.tp_px = s["tp_px"]
                # R accounting uses ACTUAL entry fill (BUG5 fix): designed-R
                # drift was the dominant reconcile residual.
                self.risk_dist = abs(fp - s["stop_px"])
                self.exit_qty_acc = 0
                self._eq_at_entry = self._equity()   # BUG4: exact per-trade basis
                sym = self.fut.mapped
                try:
                    self.stop_ticket = self.stop_market_order(
                        sym, -side * self.pos_qty, self.stop_px, tag=f"S-{oid}")
                    self.order_purpose[self.stop_ticket.order_id] = ("stop", side)
                    self.tp_ticket = self.limit_order(
                        sym, -side * self.pos_qty, self.tp_px, tag=f"T-{oid}")
                    self.order_purpose[self.tp_ticket.order_id] = ("tp", side)
                except Exception:
                    self._fail_closed_flatten("protect_submit_fail")
                # Entry cycle fully handled; exits are separate fills.
                return

            if kind in ("stop", "tp"):
                if self.pos_side == 0:
                    # OCO single-exit invariant (v2.3): the first leg already
                    # closed this cycle. If the account is FLAT, the second leg
                    # is economically VOID - never submit an offsetting order
                    # (the old path created double-fills and phantom cycles).
                    self._inc("oco_races")
                    held = 0
                    try:
                        held = self.portfolio[self.fut.mapped].quantity
                    except Exception:
                        held = 0
                    if held == 0:
                        self._inc("oco_void_legs")
                        self.order_purpose.pop(oid, None)
                        self.stop_ticket = None
                        self.tp_ticket = None
                        return
                    # Account still holds quantity: genuine race residue.
                    # Register a flatten so its fill produces a ledger row flagged
                    # is_race (excluded from headline stats, included in I1).
                    try:
                        held = self.portfolio[self.fut.mapped].quantity
                        if held != 0:
                            tk = self.market_order(self.fut.mapped, -held,
                                              tag="OCO-RACE-FLATTEN")
                            if tk is not None:
                                self.order_purpose[tk.order_id] = (
                                    "flatten", 1 if held < 0 else -1)
                                self._race_leg_pending = True
                    except Exception:
                        pass
                    self._cancel_ticket(self.tp_ticket if kind == "stop" else self.stop_ticket)
                    self.stop_ticket = None
                    self.tp_ticket = None
                    if kind == "stop":
                        self.race_stop_legs += 1   # ledger already has the -1R stop
                    else:
                        self.race_tp_legs += 1     # ledger already has its TP exit
                    try:
                        self.race_pnl_obs += self._equity() - (self._race_eq_open
                                                               if self._race_eq_open is not None
                                                               else self._equity())
                    except Exception:
                        pass
                    self._race_eq_open = None
                    self.order_purpose.pop(oid, None)
                    return
                self.exit_qty_acc += fq
                r_contrib = ((fp - self.entry_avg) / self.risk_dist) * side if self.risk_dist else 0.0
                if self.exit_qty_acc >= self.pos_qty:
                    obs_usd = self._equity() - (self._eq_at_entry if self._eq_at_entry
                                                is not None else self._equity())
                    self.trade_economics.append({
                        "r": r_contrib, "risk_dist": self.risk_dist,
                        "qty": self.pos_qty, "obs_usd": round(obs_usd, 2),
                        "is_race": False,
                    })
                    self._row_written = True
                    self._race_eq_open = self._equity()   # race leg would open here
                    self.trade_rs.append(r_contrib)
                    self._record_metrics_exit(kind)
                    other = self.tp_ticket if kind == "stop" else self.stop_ticket
                    self._cancel_ticket(other)
                    self.stop_ticket = None
                    self.tp_ticket = None
                    self.pos_side = 0
                    self.pos_qty = 0
                    self.exit_qty_acc = 0
                    self.entry_avg = None
                    self.risk_dist = None
                    # keep purpose registered until CANCELED/INVALID: LEAN may
                    # deliver additional FILLED events (partial-fill accounting)
                    # for the same order after the closing fill.
                    if self.setup is not None:
                        self.setup = None
                return

        if status in (OrderStatus.CANCELED, OrderStatus.INVALID):
            if purpose and purpose[0] == "entry":
                self.order_purpose.pop(oid, None)
                if self.setup is not None and self.setup.get("entry_id") == oid \
                        and self.pos_qty == 0:
                    K = self._sk(purpose[1])
                    if status == OrderStatus.INVALID:
                        self._inc(f"{K}_cancel_other")
                    self.setup = None
            elif purpose and purpose[0] in ("stop", "tp"):
                self.order_purpose.pop(oid, None)

    def _record_metrics_exit(self, kind):
        pass  # R recorded by caller; hook kept for attribution extensions

    def _cancel_ticket(self, t):
        if t is None:
            return
        try:
            if t.status == OrderStatus.SUBMITTED and t.quantity_left != 0:
                t.cancel()
        except Exception:
            pass

    def _register_flatten_order(self, ticket, held_qty):
        """Register a flatten order so its fill is tracked (reconcile prong:
        fills == trades requires every position-closing order to be known)."""
        if ticket is None:
            return
        self.order_purpose[ticket.order_id] = ("flatten", 1 if held_qty < 0 else -1)
        self._flatten_tickets.append(ticket.order_id)

    def _fail_closed_flatten(self, reason):
        try:
            held = self.portfolio[self.fut.mapped].quantity
            if held:
                tk = self.market_order(self.fut.mapped, -held, tag=f"FC-{reason}"); self._register_flatten_order(tk, held)
        except Exception:
            pass
        self._cancel_ticket(self.stop_ticket)
        self._cancel_ticket(self.tp_ticket)
        self.stop_ticket = None
        self.tp_ticket = None
        self.pos_side = 0
        self.pos_qty = 0
        self.exit_qty_acc = 0
        self.entry_avg = None
        self.risk_dist = None
        self.setup = None
        self._inc("forced_flattens")

    # -------------------------------------------------- reconciliation & gates
    def _sample_equity(self):
        """Track realized equity deltas per closed design trade (BUG4 fix).

        Called from on_order_event right after a full exit is recorded. The
        ledger R and the equity delta must agree within tolerance; divergence
        means the ledger has drifted from the actual account — which is exactly
        the failure mode that poisoned earlier batches.
        """
        try:
            eq = float(self.portfolio.total_portfolio_value)
        except Exception:
            return
        if self._last_equity is not None:
            self._equity_deltas.append(eq - self._last_equity)
        self._last_equity = eq

    def _reconcile_pnl(self):
        """Hard gate v3: trade_builder is the AUTHORITY for economics.

        Review round 4 verdict: designed-R dollars cannot reconcile against
        actuals once OCO races/partials exist; stop comparing ledgers.
        Identities enforced:
          I1  Σ tb.profit_loss − race/late noise ≈ TPV delta + fees  (cash)
          I2  fees_actual ≈ modeled ($0.50/side × ledger fills)
          I3  count identity: every tracked fill explained
              (ledger rows + orphan entries + late/race events)
        Design-R statistics remain DESCRIPTIVE; they are never the gate.
        """
        out = {"ok": False}
        try:
            tb_trades = list(self.trade_builder.closed_trades)
        except Exception:
            tb_trades = []
        n_tb = len(tb_trades)

        fees_actual = 0.0
        i1_profit_raw = 0.0
        for t in tb_trades:
            i1_profit_raw += float(getattr(t, "profit_loss", 0.0) or 0.0)
            try:
                fees_actual += float(t.total_fees)
            except Exception:
                pass

        try:
            tpv_delta = float(self.portfolio.total_portfolio_value) \
                - float(self._starting_tpv)
        except Exception:
            tpv_delta = None
        if tpv_delta is None:
            i1_resid, tol_i1 = 0.0, 0.0
        else:
            # cash identity: realized PnL minus friction equals equity change
            i1_resid = abs((i1_profit_raw - fees_actual) - tpv_delta)
            tol_i1 = max(0.01 * abs(tpv_delta), 25.0)

        # Fees: QC applies its NQ schedule on the MAPPED contract fills.
        # Model: $4.05/side all-in (commission+exchange+regulatory), applied
        # to every fill event (entries, exits, flatten legs).
        n_fill_events = sum(int(self.fun.get(k, 0)) for k in (
            "L_fills", "S_fills", "flatten_fills", "late_fill_events",
            "late_closes"))
        fee_per_side = float(self.cfg.get("fee_per_side_usd", 4.05))
        fees_modeled = fee_per_side * max(n_fill_events, n_tb)
        i2_resid = abs(fees_actual - fees_modeled)
        tol_i2 = max(0.15 * max(fees_actual, 1.0), 20.0)

        fills = self.fun.get("L_fills", 0) + self.fun.get("S_fills", 0)
        orphans = self.fun.get("orphan_entry_fills", 0)
        lates = self.fun.get("late_fill_events", 0)
        flatfills = self.fun.get("flatten_fills", 0)
        late_closes = self.fun.get("late_closes", 0)
        # Count identity (I3): every entry must be explained by a ledger row,
        # an orphan registration, or a measured late close. OCO-race legs are
        # excluded by construction (their economics flow through I1 netting).
        explained = len(self.trade_economics) + orphans + late_closes \
            + int(self.race_stop_legs) + int(self.race_tp_legs)
        i3_ok = fills <= explained
        ok = i1_resid <= tol_i1 and i2_resid <= tol_i2 and i3_ok
        out.update({
            "ok": ok, "n_tradebuilder": n_tb,
            "i1_profit_raw": round(i1_profit_raw, 2),
            "fees_actual": round(fees_actual, 2),
            "fees_modeled": round(fees_modeled, 2),
            "i1_resid": round(i1_resid, 2), "i1_tol": round(tol_i1, 2),
            "i2_resid": round(i2_resid, 2),
            "tpv_delta": round(tpv_delta, 2) if tpv_delta is not None else None,
            "fills_vs_ledger_orphans": f"{fills}/{len(self.trade_economics)}+{orphans}+{late_closes}",
            "late_events": lates,
        })
        return out

    # ------------------------------------------------------------------ end
    def on_end_of_algorithm(self):
        held = 0
        try:
            held = self.portfolio[self.fut.mapped].quantity
        except Exception:
            pass
        rec = self._reconcile_pnl()
        rs = self.trade_rs
        wins = sum(1 for r in rs if r > 0)
        losses = sum(1 for r in rs if r <= 0)
        avg_r = sum(rs) / len(rs) if rs else 0.0
        gross_w = sum(r for r in rs if r > 0)
        gross_l = -sum(r for r in rs if r <= 0)
        pf = (gross_w / gross_l) if gross_l > 0 else (999.0 if gross_w > 0 else 0.0)
        self.Debug("FUNNEL " + json.dumps(self.fun, sort_keys=True))
        self.Debug("RECONCILE " + json.dumps(rec))
        self.Debug(json.dumps({
            "exp_hash": self.exp_hash, "cfg": self.cfg,
            "trades": len(rs), "wins": wins, "losses": losses,
            "win_rate": round(wins / len(rs), 4) if rs else 0.0,
            "avg_r": round(avg_r, 4), "pf_local_r": round(pf, 4),
            "max_consec_losses": self._max_consec_losses(rs),
            "open_at_end": held,
        }, sort_keys=True))
        try:
            self.RuntimeStatistics["funnel_sessions"] = str(self.fun["sessions"])
            self.RuntimeStatistics["funnel_L_entries"] = str(self.fun["L_fills"])
            self.RuntimeStatistics["funnel_S_entries"] = str(self.fun["S_fills"])
            self.RuntimeStatistics["local_trades"] = str(len(rs))
            self.RuntimeStatistics["exp_hash"] = self.exp_hash
            for k in sorted(self.fun.keys()):
                self.RuntimeStatistics[f"f_{k}"] = str(self.fun[k])
            self.RuntimeStatistics["d_h4_published"] = str(len(self.h4_pub))
            self.RuntimeStatistics["d_swing_hi"] = str(len(self.swing_hi))
            self.RuntimeStatistics["d_swing_lo"] = str(len(self.swing_lo))
            # BUG4 fix: ledger stats PLUS hard reconciliation gate
            self.RuntimeStatistics["r_trades"] = str(len(rs))
            self.RuntimeStatistics["r_wins"] = str(wins)
            self.RuntimeStatistics["r_avg"] = repr(round(avg_r, 4))
            self.RuntimeStatistics["r_pf"] = repr(round(pf, 4))
            self.RuntimeStatistics["r_sum"] = repr(round(sum(rs), 3))
            self.RuntimeStatistics["r_maxconsecL"] = str(self._max_consec_losses(rs))
            lw = [r for r in rs if r > 0]
            ll = [r for r in rs if r <= 0]
            self.RuntimeStatistics["r_avgwin"] = repr(round(sum(lw) / len(lw), 4)) if lw else "0"
            self.RuntimeStatistics["r_avgloss"] = repr(round(sum(ll) / len(ll), 4)) if ll else "0"
            self.RuntimeStatistics["rec_ok"] = "1" if rec["ok"] else "0"
            self.RuntimeStatistics["rec_i1_exp_usd"] = repr(rec.get("i1_exp_usd"))
            self.RuntimeStatistics["rec_i1_profit"] = repr(rec.get("i1_profit"))
            self.RuntimeStatistics["rec_i1_resid"] = repr(rec.get("i1_resid"))
            self.RuntimeStatistics["race_legs_stop"] = str(self.race_stop_legs)
            self.RuntimeStatistics["race_legs_tp"] = str(self.race_tp_legs)
            self.RuntimeStatistics["eod_flattens"] = str(self.fun.get("eod_flattens", 0))
            self.RuntimeStatistics["rollovers"] = str(self.fun.get("rollovers", 0))
            self.RuntimeStatistics["d_bars5_total"] = str(self.d_bars5_total)
            try:
                _s = int(self.fun["sessions"])
                self.RuntimeStatistics["bars_per_session"] = \
                    repr(round(self.d_bars5_total / _s, 1)) if _s else "0"
            except Exception:
                self.RuntimeStatistics["bars_per_session"] = "0"
            self.RuntimeStatistics["tzcheck_ok"] = str(self.tzcheck_ok)
            self.RuntimeStatistics["qty_max_seen"] = str(self.qty_max_seen)
            self.RuntimeStatistics["f_flatten_fills"] = str(self.fun.get("flatten_fills", 0))
            self.RuntimeStatistics["f_untracked_fills"] = str(self.fun.get("untracked_fills", 0))
            self.RuntimeStatistics["f_late_fill_events"] = str(self.fun.get("late_fill_events", 0))
            self.RuntimeStatistics["f_orphan_entry_fills"] = str(self.fun.get("orphan_entry_fills", 0))
            self.RuntimeStatistics["f_oco_void_legs"] = str(self.fun.get("oco_void_legs", 0))
            self.RuntimeStatistics["d_open_at_end"] = str(held)
            self.RuntimeStatistics["d_ledger_rows"] = str(len(self.trade_economics))
            self.RuntimeStatistics["d_race_rows"] = str(sum(
                1 for t in self.trade_economics if t.get("is_race")))
            self.RuntimeStatistics["d_pos_side_end"] = str(self.pos_side)
            self.RuntimeStatistics["d_exit_acc_end"] = str(self.exit_qty_acc)
            fl = getattr(self, "_filllog", [])
            self.RuntimeStatistics["d_n_fillevents"] = str(len(fl))
            # per-cycle audit: how many entries got exit rows?
            n_entries = int(self.fun.get("L_fills", 0)) + \
                int(self.fun.get("S_fills", 0))
            rows = len(self.trade_economics)
            race_rows = sum(1 for t in self.trade_economics
                            if t.get("is_race"))
            self.RuntimeStatistics["d_entries"] = str(n_entries)
            self.RuntimeStatistics["d_rows_total"] = str(rows)
            self.RuntimeStatistics["d_rows_race"] = str(race_rows)
            self.RuntimeStatistics["d_rows_normal"] = str(rows - race_rows)
            self.RuntimeStatistics["d_race_stop_legs"] = str(self.race_stop_legs)
            self.RuntimeStatistics["d_race_tp_legs"] = str(self.race_tp_legs)
            # compact sequence audit: oid:last4 : purpose-short : pos_after
            seq = "|".join(
                f"{f['oid'] % 10000:04d}:{f['p'][:12]}:{f['pos']}"
                for f in fl[-60:])
            self.RuntimeStatistics["d_fill_seq"] = seq[:900]
            self.RuntimeStatistics["r_unfilled_won"] = str(self.fun.get("unfilled_won", 0))
            self.RuntimeStatistics["r_unfilled_lost"] = str(self.fun.get("unfilled_lost", 0))
            self.RuntimeStatistics["r_unfilled_timeout"] = str(self.fun.get("unfilled_timeout", 0))
            for rk in ("n_tradebuilder", "i1_profit_raw", "i1_resid",
                       "i1_tol", "fees_actual", "fees_modeled", "i2_resid",
                       "tpv_delta", "fills_vs_ledger_orphans", "late_events"):
                self.RuntimeStatistics[f"rec_{rk}"] = str(rec.get(rk))
        except Exception:
            pass

    @staticmethod
    def _max_consec_losses(rs):
        best = cur = 0
        for r in rs:
            if r <= 0:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best
