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
    "rollovers", "oco_races", "forced_flattens", "end_flattens",
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
                  "stop_mode"):
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

        self.acc5 = []          # minute closes accumulating into current 5m bucket
        self.acc5_key = None    # (et.date(), et.hour, et.minute // 5) of END times
        self.bars5 = []         # completed 5m dicts: o,h,l,c,idx,et(end)
        self.h4_pub = []        # published validated 4H bars
        self.h4_bucket = None   # {"id": (y,m,d,hour//4), "bars": [...], "offset0"}
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
        if self.bias == 0:
            self._inc("no_bias")
        self.cur_session = skey
        self.pdh = self.cur_high
        self.pdl = self.cur_low
        self.cur_high = None
        self.cur_low = None
        self.session_tried = set()
        # yesterday's levels cannot arm/hold setups into today
        if self.setup is not None and self.pos_qty == 0:
            self._cancel_pending(None)
        self._inc("sessions")
        if self.pdh is None or self.pdl is None:
            self._inc("no_prior_levels")

    # ------------------------------------------------------------ 4H engine
    def _publish_h4(self, new_id):
        bk = self.h4_bucket
        if bk is None or bk["id"] == new_id:
            return
        self.h4_bucket = None
        bars = bk["bars"]
        if len(bars) < 8 or bk["offset0"] > 60:
            return                      # partial/unverifiable bucket discarded
        o = bars[0]["open"]
        c = bars[-1]["close"]
        h = max(x["high"] for x in bars)
        l = min(x["low"] for x in bars)
        idx = len(self.h4_pub)
        self.h4_pub.append({"idx": idx, "open": o, "high": h, "low": l, "close": c})

        # confirm pivot centered 3 bars back; its right-side bars (ci+1..ci+3)
        # were all published strictly before now -> knowable at THIS publish.
        ci = idx - 4
        L = int(self.cfg.get("pivot_lookback", 3))
        Rn = int(self.cfg.get("pivot_right", 3))
        ci = idx - (Rn + 1)          # pivot candidate sits Rn+1 bars back
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
        et = b5["et"]
        bid = (et.year, et.month, et.day, et.hour // 4)
        if self.h4_bucket is None or self.h4_bucket["id"] != bid:
            self._publish_h4(bid)
            self.h4_bucket = {
                "id": bid, "bars": [],
                "offset0": (et.hour % 4) * 60 + et.minute,
            }
        self.h4_bucket["bars"].append(b5)

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
                for g in self._scan_fvgs(s["extreme_idx"], side):
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
                    through = (b["close"] > g["hi"]) if side > 0 else (b["close"] < g["lo"])
                    if through:
                        continue          # fully traded through pre-CISD: skip
                    if elig is None or g["created"] < elig["created"]:
                        elig = g
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
        for symbol, bar in data.bars.items():
            if symbol != self.fut.symbol and symbol != self.fut.mapped:
                continue
            et = self._et(self.utc_time)

            self._advance_session(et)

            # --- 5m bucket aggregation from completed minute bars ---
            bkey = (et.year, et.month, et.day, et.hour, et.minute // 5)
            if bkey != self.acc5_key:
                self._flush_5m()
                self.acc5_key = bkey
            self.acc5.append({"open": float(bar.open), "high": float(bar.high),
                              "low": float(bar.low), "close": float(bar.close),
                              "et": et})
        # flush lazily on key change; final flush handled by trim-on-read below

    def _flush_5m(self):
        if not self.acc5:
            return
        bars = self.acc5
        self.acc5 = []
        if len(bars) < 3:
            return  # hole/gap fragment: discard rather than mix distant minutes
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

        if (self._in_window(et) and self._new_setup_allowed()
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
            if purpose is None:
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
                self.risk_dist = abs(s["entry_px"] - s["stop_px"])
                self.exit_qty_acc = 0
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
                # Second leg of a same-bar stop+target race: the fill REVERSED
                # our position. Fail closed: flatten immediately.
                self._inc("oco_races")
                try:
                    held = self.portfolio[self.fut.mapped].quantity
                    if held != 0:
                        self.market_order(self.fut.mapped, -held,
                                          tag="OCO-RACE-FLATTEN")
                except Exception:
                    pass
                self._cancel_ticket(self.tp_ticket if kind == "stop" else self.stop_ticket)
                self.stop_ticket = None
                self.tp_ticket = None
                if kind == "stop":
                    self.trade_rs.append(-1.0)   # conservative: count full -1R
                    self.risk_dist = None
                self.order_purpose.pop(oid, None)
                return
            self.exit_qty_acc += fq
            r_contrib = ((fp - self.entry_avg) / self.risk_dist) * side if self.risk_dist else 0.0
            if self.exit_qty_acc >= self.pos_qty:
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

    def _fail_closed_flatten(self, reason):
        try:
            held = self.portfolio[self.fut.mapped].quantity
            if held:
                self.market_order(self.fut.mapped, -held, tag=f"FC-{reason}")
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

    # ------------------------------------------------------------------ end
    def on_end_of_algorithm(self):
        try:
            held = self.portfolio[self.fut.mapped].quantity
            if held:
                self._inc("end_flattens")
        except Exception:
            pass
        rs = self.trade_rs
        wins = sum(1 for r in rs if r > 0)
        losses = sum(1 for r in rs if r <= 0)
        avg_r = sum(rs) / len(rs) if rs else 0.0
        gross_w = sum(r for r in rs if r > 0)
        gross_l = -sum(r for r in rs if r <= 0)
        pf = (gross_w / gross_l) if gross_l > 0 else (999.0 if gross_w > 0 else 0.0)
        self.Debug("FUNNEL " + json.dumps(self.fun, sort_keys=True))
        self.Debug(json.dumps({
            "exp_hash": self.exp_hash, "cfg": self.cfg,
            "trades": len(rs), "wins": wins, "losses": losses,
            "win_rate": round(wins / len(rs), 4) if rs else 0.0,
            "avg_r": round(avg_r, 4), "pf_local_r": round(pf, 4),
            "max_consec_losses": self._max_consec_losses(rs),
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
            # design-R ledger (excludes race-reversal noise present in cloud PnL)
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
