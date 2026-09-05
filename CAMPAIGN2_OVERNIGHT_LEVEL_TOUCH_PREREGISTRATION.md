# Campaign 2 — Overnight-Level Bare-Touch Event Study

**Status:** FROZEN PRE-REGISTRATION — rules immutable. **DEV pass EXECUTED
2026-09-04** (local pipeline, guard-verified, dev window only; results in
`c2_local_study.json`, integrity tests in `test_campaign2_ledger.py`).
**ARCHIVED 2026-09-04** on DEV evidence: both primaries NULL, screening
significant_not_tradable both, no promotion trigger; filed as the
hypothesis generator for Campaign 3 — see `CAMPAIGN2_ONLT_ARCHIVE.md`
(figure tests in `test_campaign2_archive.py`). Validation/holdout were
never opened and remain LOCKED. NO strategy backtest, NO optimization.
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

### 3a. Local data pipeline and its three mandatory guards (pre-data, 2026-09-04)

Purchased Databento continuous data (`NQ.n.0`/`GC.n.0`, GLBX.MDP3, unadjusted
= RAW equivalent; open-interest front mapping = Campaign 1's
`DataMappingMode.OPEN_INTEREST` analogue) feeds the frozen generator through
`databento_local_data.py` under three permanent guards, each with committed
tests (`test_databento_local_guards.py`):

- **(a) Date gate.** Validation/holdout days are physically on disk after
  this purchase and must stay unread. Two mechanisms, both required:
  default loads decode only UTC members ≤ DEV_END (2024-12-31), so
  post-gate session dates never enter memory; and any explicit day request
  past DEV_END raises unless `VALIDATION_UNLOCK` — a committed constant,
  False until the preregistered validation phase — is passed as True.
- **(b) Embedded-roll handling.** Under continuous symbology the roll is
  embedded (the underlying `instrument_id` changes while the requested
  symbol does not). Rolls are detected from the symbol mapping in the DBN
  stream plus definition data, and Campaign 1's rule is carried forward
  exactly: a mapping event resets ATR and invalidates any partial
  overnight. A slot whose minutes span two contracts is never aggregated
  into one bar (fail-closed gap; the generator's contiguity check then
  invalidates the overnight). Permanent proof: a roll-day price
  discontinuity cannot corrupt an overnight high/low.
- **(c) Two-path reconciliation.** Local 30-minute bars must reconcile with
  QuantConnect Lean minutes on a sample of dates before any result is
  computed from the local path. Join convention established empirically:
  bars keyed on TRADE DATE + ET wall-clock end time, QC files
  {D-1, D, D+1} merged (a file can omit its first evening minutes). On
  four consecutive weekdays (2013-10-08..11, front GCZ13) the paths
  produce IDENTICAL 30m bar sets — 47/47 per day, zero orphans, 188
  common bars — under which the MEASURED equivalence contract is enforced
  by the permanent test: high/low within one tick on every bar (363/376
  field comparisons exact; these build overnight levels and touch
  triggers), open/close within four ticks (worst measured case one
  bar-open on a Friday late session; `open` is never consumed by the
  frozen generator), full OHLC exact on ≥60% of bars (measured 65.4%).
  Residual drift root cause: Databento GLBX.MDP3 consolidates CME Globex
  + ClearPort while Lean's bundle is the AlgoSeek feed (volume ratio
  ~1.7:1) — bit-exactness is impossible across vendors, so tick ceilings
  are the meaningful equivalence. Zero-volume DBN minutes are dropped
  (Lean emits no bar for a no-trade minute); QC rows are restricted to
  the exact DBN-mapped expiry, resolved date-aware from the purchased
  definition file because instrument ids are reused across instruments.
  The hosted path remains the compute authority and the byte-exact
  generator_v1 gate the methodology anchor; this test BOUNDS the local
  path's equivalence instead of silently assuming it, and any violation
  beyond the measured contract fails with printed evidence.
- **(c-extension) Cloud reconciliation, NQ and roll windows (2026-09-04,
  pre-study).** The bundled-data test above covers GC ordinary weekdays
  only; NQ has NO local Lean bundle coverage, and roll weeks — where
  Databento's open-interest rule and LEAN's `DataMappingMode.OPEN_INTEREST`
  are most likely to disagree, and where a disagreement would corrupt the
  overnight high/low the study consumes — were untested. Fixed with one
  short data-dump backtest per window on the cloud (`c2_nq_dump_main.py`
  via `d49_nq_dump_main.py`; zero orders, zero signals, subscription
  already paid): NQ 2024-11-15..12-05 (ordinary + Thanksgiving/Black
  Friday early closes, zero rolls), NQ 2024-12-16..12-30 (the Z4→H5 roll
  AND the Christmas holiday inside one window; ended 12-30 so no bar
  belongs to the 2025-01-01 validation session), GC 2020-01-15..01-31 +
  02-01..02-14 (the G0→J0 roll and MLK day; the local bundle has no GC
  files near that date, so this is the only GC-roll coverage). Bar
  transport is chart series with declared-count polling — a first
  attempt proved RuntimeStatistics string values silently truncate at
  200 chars. MEASURED results (permanent tests
  `QcCloudReconciliation` in `test_databento_local_guards.py`):
  same-contract bars are BIT-EXACT across vendors — 673/676 on the NQ
  holiday week (the three residuals are the characterized first-trade
  drift), and every GC pre-roll and post-convergence bar matched exactly
  (max diff 0.00). ROLL TIMING IS A REAL VENDOR DIVERGENCE, asserted as
  measured, never papered over: NQ — Databento switched Z4→H5 at
  2024-12-18 19:00 ET, LEAN's event fired 2024-12-19 00:00 ET, the SAME
  trade session (9 divergent slots, the Z4/H5 spread, everything else
  bit-exact); GC — Databento rolled 2020-01-23 19:00 ET while LEAN's
  depth-0 series did not change until 2020-02-06/07, a ~2-week
  front-month divergence. The consequence for C2 is bounded by design:
  the study consumes the LOCAL pipeline, and guard (b) fails closed on
  every roll session the same way regardless of which clock the vendor
  used — the mixed-slot drop plus `on_rollover` invalidation means an
  overnight spanning a roll publishes NO levels (asserted end-to-end on
  the real GC roll window: zero events on session 2020-01-24, and every
  event elsewhere verified against an independently recomputed
  single-contract overnight, on a date where the two contracts traded
  ~65 ticks apart). The hosted path remains the compute authority for
  any promoted candidate; this extension removes the market-coverage and
  roll-window gaps in the local path's equivalence proof.

The pipeline is transport, not methodology: no cell, threshold, horizon,
payoff, or classifier behavior differs between local and hosted paths.

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

## 5. Primary verdicts (split pre-data, 2026-09-04)

- **Primary A — index complex:** NQ events only. **Primary B — GC alone:** GC events only. The two verdicts are computed and reported **separately and are never pooled**: a gold result cannot be diluted by an index null, and vice versa. (This supersedes the pre-split "sole primary pooled NQ+GC with equal market weighting" wording, which was itself a pre-data amendment from the original single-cell plan; the pooled NQ+GC equal-weight contrast is retained below only as a descriptive replication, never a verdict.)
- Both primaries share every other frozen element identically:
  - Contrast: paired `reversal payoff − continuation payoff`.
  - Cell: **T2S0.5**.
  - Horizon: **120 minutes**.
  - Ambiguity convention: pessimistic stop-first.
  - Per-arm payoff: horizon payoff winsorized to the cell's bounded range `[-0.5R, +2.0R]`; paired contrast is therefore bounded `[-2.5R, +2.5R]`.
  - Inference: session-date clustered bootstrap, fixed seed, two-sided 95% interval.
  - Economic threshold: **θ = 0.2R**, never widened.
- Descriptive replication: the pooled NQ+GC equal-market-weight contrast (each market averages its event-level values first, then the two market means are averaged) is reported alongside, labeled descriptive.
- **Screening statistic (pre-data amendment, 2026-09-04):** alongside each primary's confirmatory θ test, report significance **versus zero** (same clustered bootstrap, two-sided 95% interval tested against 0, plus its p-style reading from interval position). It is reported but has **no promotion power**: no effect may be elevated to POSITIVE, tradability, or any next-phase claim on the screening statistic alone. Its purpose is descriptive honesty — a real-but-below-tradability effect is reportable as "significant vs zero, inside θ ⇒ NOT tradable at threshold" instead of collapsing into an uninformative NULL.

Three outcomes per primary:

- **POSITIVE:** the complete CI is above `+0.2R` (reversal) or below `−0.2R` (continuation); direction is reported.
- **NULL:** the complete CI lies inside `[-0.2R, +0.2R]`.
- **INCONCLUSIVE:** every other interval geometry.

All other cells, horizons, levels, range/ATR bins, touch-time bins, optimistic ambiguity results, raw ratios, MFE/MAE, and control contrasts are exploratory and cannot promote a strategy. (The NQ/GC market split is no longer on this list: it *is* the A/B verdict structure; any other market partition remains exploratory.)

## 6. Mandatory pre-launch feasibility gate

Before any market data request, `campaign2_analysis.py` simulates a **grid** of
achievable sizes `n ∈ {200, 400, 800, 1600, 3200}` (nobody knows the achievable
sample yet: two potential events per session over ~3,650 sessions × 2 markets is
~7,300 slots, so physical events plausibly land anywhere from ~1,500 to ~6,000).
Each n uses `n/2` session-date clusters (two bounded observations per cluster),
200 fixed-seed replicates, contrast draws winsorized to the implied bounds
`[−2.5R,+2.5R]` (each arm `[−0.5R,+2.0R]`), and a clustered bootstrap. The
simulated unit is the **paired contrast**, whose dispersion is anchored to
committed data, never assumed (PROTOCOL input-anchoring clause, 2026-09-04;
see §6c — the original `sd = 0.45R` was 3.2× below the ledger-derived value
and made the gate unfailable). Three informative scenarios gate the result
(≥80% intended firing at that n):

1. reversal-positive (`Δ=+0.55R`),
2. continuation-positive (`Δ=−0.55R`),
3. null-equivalent (`Δ=0R`).

Two further scenarios are reported at every grid point and never gate
(amendments 2026-09-04): the knife-edge boundary case (`Δ=+0.2R`, which under
the §6a restatement must be *emissible* — INCONCLUSIVE at ≥80% for some grid
n — rather than reliable at every n), and the near-threshold MDE probe
(`Δ=+0.3R`): whether the 0.2–0.55R band is detectable at all is the declared
minimum detectable effect record, never a stand-down trigger.

The gate output is the **minimum n at which the three informative scenarios
fire ≥80%**, frozen here as the pre-registered pass/fail number. If no grid
point passes, the study stands down before any data or cloud cost. The
post-data replay re-runs the identical classifier at the achieved `n`, achieved
session count, and the empirically measured clustered dispersion and is judged
against this frozen number, not re-guessed.

### 6c. Ledger-anchored dispersion (re-freeze 2026-09-04, pre-data)

Derived from the committed 1,121-row E19B-R FT32 ledgers at the primary cell
T2S0.5, pessimistic convention (decided arms n=1,080, mean +0.0324R, per-arm
SD **1.0240R**):

- **Floor 1.4481R** = √2 × per-arm SD — arms run opposite directions on the
  same path, so `Var(A−B) = VarA + VarB − 2Cov` is at least this, larger as
  the arms anti-correlate.
- **Central 1.6015R** — trimodal contrast {+2.5R, −2.5R, 0} with per-tail
  probability P(target-first) = 0.2052 recomputed from the ledgers (the
  directive's 1.581R uses p≈0.2 and matches to rounding).
- **Sensitivity bracket 1.0R–2.0R** — declared assumption range: 1.0R sits
  below any same-path pairing (pure per-arm scale, no correlation penalty);
  2.0R covers stronger anti-correlation and heavier C2-tail clustering.

The frozen post-data gate uses the **central** minimum passing n, with the
full sensitivity table published alongside it. If NULL (or any informative
label) cannot fire ≥80% at any grid n under the central anchor, the study
stands down before any data purchase.

The test must assert `sessions < n`. This is classifier-operability evidence,
not a power claim about realized market dispersion.

### 6d. Re-run at the anchored dispersion — frozen gate (2026-09-04, pre-data)

Artifact: `c2_feasibility_grid.json` (seed `C2-feasibility-v1`, 200 reps,
four dispersion anchors per §6c; draws clipped to the contrast bounds —
the superseded run had clipped contrast draws at the per-arm bounds, a
second defect fixed in the same pass).

Exact rates from the artifact (of 200 reps):

| sd (R) | min passing n | NULL @200 | NULL @400 | NULL @800 | 0.3R probe best |
|---|---|---|---|---|---|
| floor 1.4481 | **800** | 0.155 | 0.740 | 0.985 | 0.855 @3200 |
| central 1.6015 | **800** | 0.035 | 0.535 | 0.945 | 0.740 @3200 |
| sens-low 1.0 | 400 | 0.625 | 0.955 | 1.000 | 1.000 @3200 |
| sens-high 2.0 | **800** | 0.000 | 0.365 | 0.880 | 0.250 @3200 |

- **Frozen post-data pass/fail number: achieved n ≥ 800** (central case;
  floor, central, and sensitivity-high all agree at 800; the bracket
  endpoint 1.0R would relax to 400 but is declared, not central). The
  achievable physical population (~1,500–6,000 events) comfortably exceeds
  800, so the study remains alive — this is NOT a stand-down.
- *Post-split application (2026-09-04 note, no number changed): the gate
  applies per verdict — Primary A and Primary B each need their OWN achieved
  event count ≥ 800 to be operable; it is never evaluated on the pooled
  count, since the verdicts are never pooled. The pooled-population estimate
  above is retained as the pre-split derivation record.*
- NULL is the binding scenario at every anchored dispersion (the superseded
  0.45R run had it at 100% everywhere — proof the old gate could not fail).
- **Honest MDE record:** the Δ=+0.3R probe reaches the 80% floor only at
  the two lower dispersions (1.0R: 1.000 @3200; floor 1.4481R: 0.855
  @3200) and NEVER at the central anchor or above (best 0.740 @3200;
  sens-high 0.250). Under the frozen central dispersion the 0.2–0.55R band
  is therefore declared **not reliably detectable at any achievable n**: a
  real effect must approach ~0.5R for the classifier to call it reliably,
  or the study must resolve via the NULL side (which fires from n≈800).
  This is the answer the amendment asked for regardless of sign; it changes
  no rule — the primary, θ, geometry, cell, and horizon are unchanged.
- Boundary emissibility (per the §6a restatement): INCONCLUSIVE fires ≥80%
  at some grid n under every anchored dispersion (per-dispersion maxima
  0.97/0.985/0.96/0.99). The knife-edge rate declines with n as estimator
  consistency demands — lowest cell in the whole grid is 0.725
  (sens-high @3200) — exactly the behavior §6a predicted.
- A negative-control test ships with the grid: at adversarial sd=6.0R the
  informative scenarios fail, proving the corrected gate can actually fail.

### 6a. Gate executed — boundary-criterion restatement (retained), result SUPERSEDED

> **SUPERSEDED 2026-09-04 (same day):** the run recorded below used an
> ASSUMED per-contrast dispersion of `sd = 0.45R`, which the committed
> E19B-R FT ledgers show is 3.2× too small (§6c). At the anchored
> dispersion the informative NULL label fires 4% at n=200, so the claims
> "minimum_passing_n = 200" and "0.3R detectable from n≥200" are WITHDRAWN
> and replaced by §6c. Retained verbatim because the §6a boundary-criterion
> restatement below it remains correct and in force: it was a genuine
> estimator-consistency defect, independent of the dispersion input. The
> original artifact has been overwritten by the anchored re-run under the
> same filename.

Original run (artifact of record now replaced; seed `C2-feasibility-v1`,
200 reps, assumed sd 0.45R):

- **minimum_passing_n = 200** — WITHDRAWN: at 0.45R an n of 19 already
  clears a 0.2R half-width, so no grid point could fail.
- POSITIVE and NULL fired 100% at every grid n — artifact of the same defect.
- MDE probe claim "detectable from n≥200" — WITHDRAWN; see §6c.
- Boundary scenario (Δ exactly = θ) degraded with n: 93.5 / 92.0 / 86.0 /
  86.5 / **67.5%** at n=200…3200, failing the 80% floor at n=3200 only.

**Pre-data criterion correction (documented, dated, zero market data used):**
requiring the knife-edge scenario to fire INCONCLUSIVE ≥80% at every grid n
demands that the estimator be *inconsistent*: a CI that concentrates around a
true mean sitting exactly at θ must converge to a coin flip between POSITIVE
and NULL, so the INCONCLUSIVE rate at the boundary is mathematically forced
toward 0 as n grows. A criterion that cannot pass at large n is the same
class of design defect the gate exists to catch, so the replay criterion is
restated: the post-data replay requires POSITIVE and NULL (and the MDE probe
reporting) to fire ≥80% at the achieved n/sd, and requires INCONCLUSIVE
emissibility (≥80% at some grid n — satisfied at n=200), never INCONCLUSIVE
reliability at the knife edge. θ, the interval geometry, the cell, horizon,
estimator, and clustering rule are unchanged.

## 6b. ATR floor and entry-price sensitivity (pre-data amendments)

- **Minimum ATR floor (ticks):** an event is admitted only if its ex-ante
  ATR(14) over 30-minute bars is at least **10 ticks** of its market
  (NQ: 2.50 index points; GC: 1.00 point). Below that, bracket distances are so
  small that the 0.5R stop is hit almost immediately and stop-first rates
  inflate in quiet regimes. The floor is declared pre-data; the **realized ATR
  distribution per market must be published with the event ledger** so the
  floor's event-retention rate is auditable. Retention is a fail-closed
  population filter, not a selectable parameter.
- **Touch-bar-close entry sensitivity (declared variant):** the primary keeps
  entry at the overnight level (realistic for a resting limit). Because
  excluding the touch bar from resolution hides any adverse move that occurs
  after the touch and inside that bar — a real cost a live trader eats — a
  second, fully declared variant resolves the same events entering at the
  **touch bar close**. The variant is reported alongside the primary as the
  passive-limit-versus-marketable question from Campaign 1. It cannot be used
  to pick the better-looking answer: the primary entry style — for both
  verdicts A and B — remains level-entry.

## 7. Stop rules

- No strategy orders, strategy backtest, optimization, validation, or holdout access.
- No parameter selection from the 16-cell surface or context bins.
- No random-time control until the event ledger passes exact reconciliation.
- No rescue/strategy phase unless at least one primary verdict (A or B) is robust, economically meaningful, and ambiguity-stable within its own market; a rescue phase may never be argued from the pooled descriptive replication.
- A NQ null is expected and does not invalidate a separately reported GC result; neither leg may be silently dropped.

## 8. Post-data replay record (DEV pass, executed 2026-09-04)

Artifact of record: `c2_local_study.json` (git-tracked; ledger integrity
tests `test_campaign2_ledger.py`). Frozen gate re-evaluated at ACHIEVED
numbers, not re-guessed:

| market | achieved n | sessions | realized contrast sd | frozen gate | pass |
|---|---|---|---|---|---|
| NQ (Primary A) | 3,033 | 2,570 | 1.2604R | n ≥ 800 (central 1.6015 anchor) | yes |
| GC (Primary B) | 2,468 | 2,370 | 0.9315R | n ≥ 800 | yes |

- Both realizations sit BELOW the anchored central dispersion (1.6015R):
  the study is at least as informative as planned; the stand-down
  conditions (n < 800 or sd materially exceeding the anchor) did not
  fire. At realized sd the frozen grid replays to minimum_passing_n 800
  (NQ) / 400 (GC), so the frozen 800 requirement is met with margin by
  both verdicts.
- ATR-floor retention published: NQ 38 rejects of 3,071 candidates
  (98.76%), GC 3 of 2,471 (99.88%) — the floor barely binds on this
  population.
- Primary outcomes (T2S0.5 @120m, pessimistic, clustered bootstrap):
  A = NULL (point +0.054R, CI [+0.005, +0.100]; screening
  significant_not_tradable vs zero in reversal direction);
  B = NULL (point −0.088R, CI [−0.123, −0.053]; screening
  significant_not_tradable vs zero in continuation direction).
  Declared sensitivities (optimistic ambiguity; touch-bar-close entry)
  reported in the artifact; neither crosses ±θ; no label changes.
- Consequence under §7: no promotion trigger exists (both confirmatory
  verdicts NULL), no random-time-control phase is opened by this pass,
  and validation/holdout stay locked. The screening statistics record
  that small real effects exist in opposite directions per market —
  descriptive honesty only, zero promotion power by construction.
