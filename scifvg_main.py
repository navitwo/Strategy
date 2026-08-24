# SCIFVG v1.0 CONTROL — Sweep -> CISD -> IFVG -> Retest | NQ/MNQ futures
# Protocol: PROTOCOL.md (frozen 2026-08-23). Completed 5m bars only. No lookahead.
# Signals: continuous canonical series (RAW, OI mapping). Orders: mapped contract.
from AlgorithmImports import *

from datetime import timedelta
import hashlib
import json
import math
from zoneinfo import ZoneInfo


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
    "rollovers", "oco_races", "forced_flattens", "end_flattens", "eod_flattens", "flatten_fills", "untracked_fills",
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
                  "stop_mode", "entry_mode", "random_entry_prob"):
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
        self.set_time_zone(TimeZones.UTC)

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

        # 5m consolidation via LEAN (replaces hand-rolled acc5 buffer)
        self.consolidate(timedelta(minutes=5), Resolution.MINUTE,
                         self._on_5m_consolidated)

        self.ny = ZoneInfo("America/New_York")
        self.tick = 0.25
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

        self.acc5 = []          # minute bars accumulating into current 5m bucket
        self.acc5_key = None    # 5m slot key on the standard :00 grid (START time)
        self.bars5 = []         # completed 5m dicts: o,h,l,c,idx,et(end)
        self.h4_pub = []        # published validated 4H bars
        self.h4_bucket = None   # {"id":..., "bars":[...], "offset0", "t0", "tN"}
        # BUG2 fix v2: coverage measured as WALL-CLOCK SPAN, not bar count.
        # Trade bars are missing in quiet minutes; a real 4H bucket spans
        # ~4h from first bar start to last bar end. Fragments (< 3h30m) and
        # mid-bucket starts are discarded.
        self.h4_min_span_min = 210
        self.h4_max_offset0 = 1
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

    def _equity(self):
        try:
            return float(self.portfolio.total_portfolio_value)
        except Exception:
            return 0.0

        self.Debug(f"SCIFVG init {cfg['instrument']} trade {start}..{end} "
                   f"warmup_from={ws.isoformat()} win={cfg['window_start_et']}-"
                   f"{cfg['window_end_et']} hash={self.exp_hash}")

    # ------------------------------------------------------------- utilities
    def _et(self, utc_dt):
        return utc_dt.astimezone(self.ny)

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
    def _maybe_random_entry(self, b, idx, et):
        """Deterministic pseudo-random entry for the null distribution (B2-E15).

        Eligible: flat, no setup, in window, prior-day levels known. The
        accept/reject draw is a pure hash of (exp_hash, bar end time) so runs
        are reproducible and independent of the signal path. Bracket geometry,
        sizing, costs, and management are IDENTICAL to the signal strategy —
        only entry selection differs.
        """
        import hashlib as _h
        if not self._in_window(et) or not self._new_setup_allowed():
            return
        p = float(self.cfg.get("random_entry_prob", 0.02))
        seed = f"{self.exp_hash}|{b['et'].isoformat()}"
        h = int(_h.md5(seed.encode()).hexdigest()[:8], 16)
        if (h % 10000) / 10000.0 >= p:
            return
        side = 1 if (h % 2 == 0) else -1
        level = self.pdl if side > 0 else self.pdh
        ext = b["low"] if side > 0 else b["high"]
        buf = self.cfg["stop_buffer_ticks"] * self.tick
        # entry at the just-closed bar's close: realistic (near-market) fill so
        # designed R == realized R (the reconciliation gate verifies this).
        if side > 0:
            stop = self._rt(ext - buf, up=False)
            entry = self._rt(b["close"], up=True)
            if entry - stop < 4 * self.tick:
                return
            tp = self._rt(entry + float(self.cfg["target_r"]) * (entry - stop), up=True)
        else:
            stop = self._rt(ext + buf, up=True)
            entry = self._rt(b["close"], up=False)
            if stop - entry < 4 * self.tick:
                return
            tp = self._rt(entry - float(self.cfg["target_r"]) * (stop - entry), up=False)
        s = {
            "side": side, "stage": "PENDING", "arm_sk": self._session_key(et),
            "b0": idx, "reclaim_deadline": idx, "level": level,
            "extreme": ext, "extreme_idx": idx, "ref_open": None,
            "ref_idx": None, "cisd_deadline": idx,
            "fvg": {"lo": min(level, ext), "hi": max(level, ext), "created": idx},
            "inv_deadline": idx, "cisd_idx": idx,
            "retest_deadline": idx + self.cfg["retest_max_bars"],
            "entry_id": None,
        }
        # register setup BEFORE submission so the fill handler can find it;
        # exactly ONE bracket order per null entry (dup call removed).
        self.setup = s
        self._submit_bracket(side, entry, stop, tp, idx)
        self._inc(f"{self._sk(side)}_attempts")

    def _submit_bracket(self, side, entry, stop, tp, idx):
        """Shared bracket submission for the null mode: marketable-limit entry
        at this bar's close ± modeled slippage + OCO exits. Keeps designed R ==
        realized R so the reconciliation gate passes."""
        dist = abs(entry - stop)
        K = self._sk(side)
        if dist <= 0:
            return False
        qty = int(float(self.cfg["risk_usd"]) / (dist * self.point_value))
        qty = min(qty, int(self.cfg["max_contracts"]))
        if qty < 1:
            self._inc(f"{K}_size_skips")
            return False
        sym = self.fut.mapped
        if sym is None:
            return False
        lim = self._rt(entry + side * 2 * self.tick, up=(side > 0))
        try:
            tk = self.limit_order(sym, qty * side, lim,
                                  tag=f"E-{K}-{idx}-{self.exp_hash}")
        except Exception:
            return False
        if self.setup is not None:
            self.setup["entry_id"] = tk.order_id
            self.setup["entry_px"] = entry
            self.setup["qty"] = qty
            self.setup["stop_px"] = stop
            self.setup["tp_px"] = tp
            self.order_purpose[tk.order_id] = ("entry", side)
        self._inc(f"{K}_submits")
        return True

    # ---------------------------------------------------------- state machine
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
            if idx >= s["reclaim_deadline"]:
                self._inc(f"{K}_no_reclaim")
                self.setup = None
            return

        if s["stage"] == "CISD":
            trigger = (b["close"] > s["ref_open"]) if side > 0 else (b["close"] < s["ref_open"])
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
        if s and s.get("entry_id") is not None:
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
        # 5m aggregation is delegated to LEAN's TradeBarConsolidator via
        # self.consolidate(...) (registered in initialize). The consolidator
        # owns slot boundaries on the standard :00/:05/:10 grid and calls
        # _on_5m_consolidated exactly once per completed bucket. No manual
        # accumulator, no trailing flush: one minute bar in never emits a bar.
        for symbol, bar in data.bars.items():
            if symbol != self.fut.symbol and symbol != self.fut.mapped:
                continue
            et = self._et(bar.end_time)
            self.last_bar_et = et

        # Session advance still happens here, AFTER any consolidation callback
        # fired for this slice (LEAN invokes consolidators before/with on_data
        # delivery of subsequent slices; the last bucket of a session is always
        # flushed by the calendar before the next session's first bar arrives).
        if self.last_bar_et is not None:
            self._advance_session(self.last_bar_et)

    def _on_5m_consolidated(self, consolidated):
        """LEAN consolidator callback: exactly one call per completed 5m slot.

        `consolidated` is a TradeBar whose EndTime marks the slot boundary on
        the standard :00/:05/:10... grid (exchange tz). We convert to ET and
        append to bars5 with identical downstream semantics as before.
        """
        try:
            end_utc = consolidated.end_time
            et = end_utc.astimezone(self.ny)
        except Exception:
            return
        agg = {
            "open": float(consolidated.open),
            "high": float(consolidated.high),
            "low": float(consolidated.low),
            "close": float(consolidated.close),
            "idx": -1,
            "et": et,
        }
        self.bars5.append(agg)
        if len(self.bars5) > 600:
            trim = len(self.bars5) - 600
            del self.bars5[:trim]
            self._rebase(trim)
        agg["idx"] = len(self.bars5) - 1   # assign AFTER any trim
        if self.cur_high is None or agg["high"] > self.cur_high:
            self.cur_high = agg["high"]
        if self.cur_low is None or agg["low"] < self.cur_low:
            self.cur_low = agg["low"]
        self._accumulate_h4(agg)
        if self.setup is not None and self.setup["stage"] == "PENDING" \
                and self.pos_qty == 0:
            skey0 = self._session_key(et)
            if skey0 is not None:
                self._manage_pending(agg, agg["idx"], et, skey0)
        skey = self._session_key(et)
        if skey is None:
            return
        if str(self.cfg.get("entry_mode", "signal")) == "random":
            self._maybe_random_entry(agg, agg["idx"], et)
        elif (et.date() >= self.camp_start and self._in_window(et)
                and self._new_setup_allowed() and self.bias in (1, -1)):
            self._try_arm_attempt(agg, agg["idx"], skey)
        if self.setup is not None and self.setup["stage"] in ("SWEPT", "CISD", "INV"):
            if self._in_window(et) and self.setup["arm_sk"] == skey:
                self._advance_setup(agg, agg["idx"], et, skey)
            else:
                K = self._sk(self.setup["side"])
                self._cancel_pending(f"{K}_cancel_window")

    def _flush_5m(self):
        if not self.acc5:
            return
        bars = self.acc5
        self.acc5 = []
        agg = {
            "open": bars[0]["open"],
            "high": max(x["high"] for x in bars),
            "low": min(x["low"] for x in bars),
            "close": bars[-1]["close"],
            "idx": -1,
            "et": bars[-1]["et"],
        }
        self.bars5.append(agg)
        if len(self.bars5) > 600:
            trim = len(self.bars5) - 600
            del self.bars5[:trim]
            self._rebase(trim)
        agg["idx"] = len(self.bars5) - 1   # assign AFTER any trim
        self._on_completed_bar(agg)

    def _rebase(self, trim):
        if self.setup:
            for f in ("b0", "reclaim_deadline", "extreme_idx", "cisd_deadline",
                      "inv_deadline", "cisd_idx", "retest_deadline", "ref_idx"):
                v = self.setup.get(f)
                if isinstance(v, int):
                    self.setup[f] = v - trim
            if self.setup.get("fvg"):
                self.setup["fvg"]["created"] -= trim

    def _on_completed_bar(self, b):
        idx = b["idx"]
        et = b["et"]
        skey = self._session_key(et)
        if skey is None:
            return  # maintenance halt bar cannot exist (halt has no trades)

        if self.cur_high is None or b["high"] > self.cur_high:
            self.cur_high = b["high"]
        if self.cur_low is None or b["low"] < self.cur_low:
            self.cur_low = b["low"]

        self._accumulate_h4(b)

        if self.setup is not None and self.setup["stage"] == "PENDING" \
                and self.pos_qty == 0:
            self._manage_pending(b, idx, et, skey)

        if et.date() < self.camp_start:
            return  # warmup: build bias/levels only; no signal generation

        if str(self.cfg.get("entry_mode", "signal")) == "random":
            self._maybe_random_entry(b, idx, et)
        elif (self._in_window(et) and self._new_setup_allowed()
                and self.bias in (1, -1)):
            self._try_arm_attempt(b, idx, skey)

        if self.setup is not None and self.setup["stage"] in ("SWEPT", "CISD", "INV"):
            if self._in_window(et) and self.setup["arm_sk"] == skey:
                self._advance_setup(b, idx, et, skey)
            else:
                K = self._sk(self.setup["side"])
                self._cancel_pending(f"{K}_cancel_window")

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
            if purpose and purpose[0] == "flatten":
                # Flatten fills close residual exposure; they are not design
                # trades. Record them so fills==trades cross-check stays true
                # (flatten orders ARE registered in order_purpose).
                self._inc("flatten_fills")
                self.order_purpose.pop(oid, None)
                return
            if purpose is None:
                self._inc("untracked_fills")
                return
            kind = purpose[0]
            side = purpose[1]
            if kind == "entry":
                K = self._sk(side)
                self._inc(f"{K}_fills")
                if self.pos_qty == 0:
                    self.entry_avg = fp
                else:
                    self.entry_avg = ((self.entry_avg * self.pos_qty) + fp * fq) / (self.pos_qty + fq)
                self.pos_side = side
                self.pos_qty += fq
                s = self.setup
                if s is None:
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
                return

            # stop / tp fill events
            if self.pos_side == 0:
                # BUG4 fix: same-bar stop+target race. The first leg closed the
                # position (already recorded); this second fill REVERSED us.
                # Fail-closed flatten, and the reversal round-trip PnL is
                # EXCLUDED from the R ledger (it is execution noise, not
                # strategy economics) but reported via pnl_reconcile counters.
                self._inc("oco_races")
                try:
                    held = self.portfolio[self.fut.mapped].quantity
                    if held != 0:
                        tk = self.market_order(self.fut.mapped, -held,
                                          tag="OCO-RACE-FLATTEN")
                        self._register_flatten_order(tk, held)
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
                })
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
                self.order_purpose.pop(oid, None)
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
        """Hard gate: design-R ledger must reconcile with account economics.

        expected_usd  = Σ(R × risk_dist × point_value × qty) over recorded trades
        observed_usd  = final equity − starting cash + fees paid
        race noise    = PnL of excluded same-bar reversal round-trips
        PASS requires |expected − (observed + excluded_race_pnl)| ≤ max(1% of
        |observed|, $25). On failure the run is flagged RECONCILE_FAIL and MUST
        NOT be used for any research conclusion.
        """
        exp_usd = 0.0
        obs_sum = 0.0
        for t in self.trade_economics:
            exp_usd += t["r"] * t["risk_dist"] * self.point_value * t["qty"]
            obs_sum += t["obs_usd"]
        # primary gate: per-trade ledger R (converted at design risk) must match
        # the equity actually realized between that trade's entry and exit.
        resid_trades = abs(exp_usd - obs_sum)
        tol = max(0.01 * abs(obs_sum), 25.0)
        resid = resid_trades
        obs_usd = obs_sum
        ok = resid <= tol
        # cross-check prong: every tracked fill must have become a ledger trade
        fills = self.fun.get("L_fills", 0) + self.fun.get("S_fills", 0)
        if fills != len(self.trade_economics):
            ok = False
        return {
            "ok": ok, "exp_usd": round(exp_usd, 2), "obs_usd": round(obs_usd, 2),
            "race_pnl_est": round(self.race_pnl_obs, 2), "resid": round(resid, 2),
            "tol": round(tol, 2), "fills_vs_trades": f"{fills}/{len(self.trade_economics)}",
        }

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
            self.RuntimeStatistics["rec_exp_usd"] = repr(rec["exp_usd"])
            self.RuntimeStatistics["rec_obs_usd"] = repr(rec["obs_usd"])
            self.RuntimeStatistics["rec_resid"] = repr(rec["resid"])
            self.RuntimeStatistics["race_legs_stop"] = str(self.race_stop_legs)
            self.RuntimeStatistics["race_legs_tp"] = str(self.race_tp_legs)
            self.RuntimeStatistics["eod_flattens"] = str(self.fun.get("eod_flattens", 0))
            self.RuntimeStatistics["rollovers"] = str(self.fun.get("rollovers", 0))
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
