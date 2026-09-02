# Campaign 2 — Overnight-Level Bare-Touch Event Study

**Status:** FROZEN PRE-REGISTRATION — NO MARKET DATA PULLED, NO BACKTEST, NO OPTIMIZATION  
**Protocol:** `C2-ONLT-v1`  
**Frozen:** 2026-09-01  
**Validation/holdout:** LOCKED

## 1. Question and prior

Does the first regular-session bare touch of the completed full-session overnight high or low contain an economically meaningful directional effect, and is the effect reversal or continuation?

The prior is deliberately unfavorable for NQ: it tests a liquidity-reference level closely related to the sweep/reclaim family already shown by FT32E to be a coin flip across its ambiguity interval. GC is the genuinely untested replication leg. Removing the reclaim requirement creates a new bare-touch population; it does not rehabilitate Campaign 1.

## 2. Frozen population

- Markets: **NQ** and **GC** only; never MNQ/MGC.
- Common development interval: **2010-06-07 through 2024-12-31**.
- Validation: **2025-01-01 through 2025-12-31**, locked and unread.
- Holdout: **2026-01-01 onward**, locked and unread.
- Source bars: one-minute trades consolidated natively to completed **30-minute ET bars**.
- Continuous futures: current mapped contract, `OPEN_INTEREST` mapping, `RAW` normalization. GC delivery months are Feb/Apr/Jun/Aug/Oct/Dec. A mapping event resets ATR and invalidates the partial overnight; no event can be published until a later complete overnight is observed.
- Session: 18:00 ET previous calendar day through 17:00 ET trade date, with 17:00–18:00 maintenance.

A complete overnight is exactly 31 contiguous completed 30-minute endpoints from 18:30 ET through 09:30 ET. A gap, partial lifecycle, mid-session start, or rollover fails closed.

## 3. Frozen event generator

`EventGenerator` emits exactly:

`(timestamp, side, reference_level, risk_dist, context)`

`overnight_level_touch_v1`:

1. Compute the high and low over the complete overnight, 18:00 previous day → 09:30 trade date.
2. Inspect completed RTH 30-minute bars ending 10:00, 10:30, 11:00, 11:30, 12:00, and 12:30 ET.
3. Emit the first bare touch of each level, at most one high event and one low event per session. No reclaim, bias, CISD, FVG, IFVG, depth, or other gate is permitted.
4. High touch is signed short toward the reference; low touch is signed long toward it.
5. Resolve both the signed **reversal** arm and the exact opposite **continuation** arm for every physical event. They share one `event_id`; arm and horizon are subkeys.
6. `risk_dist` is ex-ante ATR(14) of completed 30-minute bars, excluding the touch bar. Entry/reference price is the overnight level. The touch bar is excluded from post-event MFE/MAE and first-touch resolution to prevent pre-touch leakage.

The frozen `generator_v1` compatibility gate must reconcile the committed E19B-R ledgers exactly: NQ 388, ES 186, YM 376, RTY 171; same `chart_x`, 16 codes, and `packed_uint32` for all 1,121 rows. Failure blocks Campaign 2.

## 4. Outcomes and transport

Reuse the no-order downstream event-study layer:

- signed forward R at 30/60/120/240 minutes;
- MFE/MAE;
- 16 target/stop cells T{0.5,1,1.5,2} × S{0.5,1,1.5,2};
- pessimistic stop-first primary and optimistic target-first sensitivity for same-bar ambiguity;
- float64-exact packed FT payload, decoded ledgers, exact row reconciliation, offline screen, martingale calibration;
- same-session-date random-time control, matched on market, date, side, time-window support, and risk distance; genuine session-date clustering with a permanent `sessions < n` assertion.

New packed context per physical event:

- overnight range width in points;
- overnight range width / ex-ante ATR;
- touch time-of-day in ET.

Context is conditioning-only. No context threshold is selectable in this phase.

## 5. Sole primary

- Physical population: NQ and GC pooled with equal market weighting; each market first averages its event-level values, then the two market means are averaged. Market-specific results are mandatory descriptive replications.
- Contrast: paired `reversal payoff − continuation payoff`.
- Cell: **T2S0.5**.
- Horizon: **120 minutes**.
- Ambiguity convention: pessimistic stop-first.
- Per-arm payoff: horizon payoff winsorized to the cell's bounded range `[-0.5R, +2.0R]`; paired contrast is therefore bounded `[-2.5R, +2.5R]`.
- Inference: session-date clustered bootstrap, fixed seed, two-sided 95% interval.
- Economic threshold: **θ = 0.2R**, never widened.

Three outcomes:

- **POSITIVE:** the complete CI is above `+0.2R` (reversal) or below `−0.2R` (continuation); direction is reported.
- **NULL:** the complete CI lies inside `[-0.2R, +0.2R]`.
- **INCONCLUSIVE:** every other interval geometry.

All other cells, horizons, market splits, levels, range/ATR bins, touch-time bins, optimistic ambiguity results, raw ratios, MFE/MAE, and control contrasts are exploratory and cannot promote a strategy.

## 6. Mandatory pre-launch feasibility gate

Before any market data request, `campaign2_analysis.py` must simulate at conservative achievable size `n=800`, `400` session-date clusters, 200 fixed-seed replicates per scenario. It must demonstrate nonzero and at least 80% intended firing for:

1. reversal-positive (`Δ=+0.55R`),
2. continuation-positive (`Δ=−0.55R`),
3. null-equivalent (`Δ=0R`),
4. boundary/inconclusive (`Δ=+0.2R`).

The test must assert `sessions < n`. Failure of any scenario stands the study down before cloud/data cost. This is classifier-operability evidence, not a power claim about realized market dispersion.

After development rows exist, a second simulation must replay the achieved `n`, session count, and clustered dispersion. If any informative label fires below 80%, stop before inference or control launch and amend only by a new protocol — never by widening θ.

## 7. Stop rules

- No strategy orders, strategy backtest, optimization, validation, or holdout access.
- No parameter selection from the 16-cell surface or context bins.
- No random-time control until the event ledger passes exact reconciliation.
- No rescue/strategy phase unless the sole primary is robust, economically meaningful, ambiguity-stable, and directionally supported across both markets.
- A NQ null is expected and does not invalidate a separately reported GC result; neither leg may be silently dropped.
