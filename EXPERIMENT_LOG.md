# EXPERIMENT LOG — SCIFVG Batch 1 (frozen 2026-08-23)

Project: NQ CISD IFVG 2026 (QC project_id 35506697). Protocol: PROTOCOL.md.
Dev range: 2023-01-03 → 2025-04-30 (631 sessions). Validation/holdout LOCKED in Batch 1.
Execution: $0.50/side commission, 1 tick slippage/fill, mapped-contract orders, $100 fixed risk.

## Implementation revision history
- v1.0.0 — first cloud baseline. DEFECTS FOUND: (1) bias could never flip back to bullish
  (`bias>=0` guard); (2) OCO same-bar race leaked a reversal position instead of flattening;
  warmup gate missing; ring-buffer idx assigned pre-trim (cloud runtime error).
- v1.0.1 — fixes for (1)(2) + regression tests `test_bias_symmetry`. CONTROL rerun.
- v1.2 — DEFECT FOUND: `_scan_fvgs` only built bearish gaps → short setups used wrong-side
  zones since baseline. Fixed to orientation-symmetric; regression test `test_fvg_orientation_symmetry`.
- Instrumentation note: cloud PnL includes OCO-race reversal round-trips (accidental offsetting
  exposure). All Batch-1 verdicts use the design-R ledger emitted via RuntimeStatistics
  (r_trades, r_wins, r_avg, r_pf, r_sum, r_maxconsecL, r_avgwin, r_avgloss).

## Diagnostics (not experiments)
- DIAG probe v1 (8d): runtime error (idx desync) — fixed.
- DIAG probe v2/v3 (8d): clean; funnel verified end-to-end (1 attempt→CISD→inv_timeout).
- SCIFVG-v1.0-BASELINE-ctrl-e2b0c1aa — superseded by v1.0.1/v1.0.2 control reruns (defects above).
- E01/E01b — E01 no-op (midpoint test shadowed by traversal guard); E01b revealed defect #3.

## Controls
| version | trades | wins | avg R | PF(R) | sum R | notes |
|---|---|---|---|---|---|---|
| v1.0.1 CONTROL | 2 | 1 | n/a | 1.83* | ~0 | long side still broken (bearish-only FVGs) |
| **v1.0.2 CONTROL** | 2 | 1 | n/a | 1.66* | ~0 | symmetric FVGs; L:73→18 CISD→1 inv→1 fill; S:68→17→1→1 |

*cloud-PF contaminated by race round-trips; sample = 2 trades ⇒ uninformative either way.

## Experiments (all on v1.2 engine, invert_on_cisd_bar=1 unless noted)
| # | id (backtest) | change | trades | wins | avg R | PF(R) | sum R | verdict |
|---|---|---|---|---|---|---|---|---|
| E01c | 30f57465… | invert-on-CISD-bar + FVG symmetry fix | 6 | 3 | −0.52R* | 15.24* | n/a | *cloud-contaminated ledger; superseded by E01d |
| E01d | b25973b5… | E01c re-run with R-ledger instrumentation | 8 | 2 | **−0.31** | 0.61 | −2.51 | NEGATIVE edge; unlocks sample though |
| E02 | b5866e15… | sweep_max_ticks 96→192 | 9 | 2 | −0.41 | 0.52 | −3.65 | rejected (worse, +depth not helpful) |
| E03 | 3cc71d0f… | reclaim_bars 3→6 | 8 | 2 | −0.31 | 0.61 | −2.51 | non-binding (no new entries) |
| E04 | 1b79a302… | fvg_min_ticks 4→2 | 8 | 2 | −0.31 | 0.61 | −2.51 | non-binding (identical behavior) |
| E05 | midpoint entry | entry_location=midpoint | 6 | 1 | **−0.60** | 0.36 | −3.60 | rejected (adverse selection at deeper fills) |
| E06 | target_r=1.5 | 2R→1.5R | 8 | 2 | −0.44 | 0.46 | −3.50 | rejected (losers aren't near-misses) |
| E07 | window 8:30–11:30 | window_start −60m, end −30m | **10** | 3 | **−0.09** | 0.87 | −0.90 | best config; still ≤ breakeven |
| E08 | window 9:30–13:00 | window_end +60m | 8 | 2 | −0.31 | 0.61 | −2.51 | identical ledger (post-noon dead) |
| E09 | sweep_min_ticks 4→8 | deeper sweeps only | 8 | 2 | −0.31 | 0.61 | −2.51 | identical trade set (non-binding) |
| E10 | instrument=NQ | cross-instrument replication | 0 (7 size_skips) | – | – | – | – | signals match MNQ upstream; sizing skip correct |

Funnel reference (v1.0.2 control): attempts L73/S68 → sweep_ok L28/S25 → CISD L18/S17 →
inv_ok L1/S1 → fills 2. With invert-on-CISD-bar (E01d): inv_ok L5/S4 → submits 8 → fills 8.

## Raw artifacts
- experiment_log.jsonl (append-only), *_out.txt per run, probe_result.json / probe3_result.json.
- Remote backtests retained under project 35506697 with immutable names/IDs above.

---

# BATCH 2 (authorized continuation, 2026-08-23)

Addendum frozen before runs: engine v1.3 adds `pivot_lookback` / `pivot_right` /
`max_attempts_per_day` / `stop_mode` ("sweep"|"gap") parameters, all defaulting to V1.0
behavior. No new implementation defects discovered in Batch 2. Same dev range, costs,
and R-ledger discipline. Limit: 4 completed experiments → then STOP.

## Experiments
| # | id | change | trades | wins | avg R | PF(R) | sum R | maxCL | verdict |
|---|---|---|---|---|---|---|---|---|---|
| B2-E11 | d383c6c6… | max_attempts_per_day 1→3 | 20 | 6 | −0.19 | 0.76 | −3.79 | 5 | rejected standalone (dilution; DD 42.6%) |
| **B2-E12** | 32a3834c… | stop_mode=sweep→gap (far edge + buffer) | **11** | **4** | **+0.05** | **1.08** | **+0.59** | **2** | FIRST non-negative lead; insufficient sample |
| B2-E13 | dff67e1c… | pivot_right 3→2 | 9 | 2 | −0.39 | 0.53 | −3.51 | 4 | rejected |
| B2-E14 | e43cacef… | pivot_lookback 2 + right 2 | 9 | 2 | −0.39 | 0.53 | −3.51 | 4 | rejected |

## Batch 2 findings
1. Loss mechanics confirmed as the damage center: moving the stop from the sweep extreme
   to the far gap edge flipped expectancy from −0.31R to +0.05R and cut consecutive-loss
   streaks 4→2 (B2-E12). The sweep-extreme stop sits beyond noise for this setup.
2. Multi-attempt scaling works mechanically (10x funnel) but admits lower-quality chains;
   useful only as a sample amplifier once a positive core exists.
3. Bias pivot geometry is NOT the binding constraint: L/R ∈ {2,3} variations shift
   results only marginally and consistently negatively vs baseline.
4. No Champion promoted: B2-E12 is ~breakeven on n=11 — a hypothesis, not a result.

## Recommended Batch 3 (NOT started)
1. Combine stop_mode=gap + E07 window (8:30–11:30 ET) + attempts=3 to push sample toward
   40+; judge only the combined ledger.
2. Parameter robustness around the gap stop: buffer ±1–2 ticks, proximal vs far entry
   under gap-stop geometry.
3. Slippage stress 2–3 ticks each way on any configuration that survives step 1–2.
4. Only after a frozen candidate exists: validation segment 2025-05→2026-01, holdout untouched.


## 2026-08-23 — Review round 5 directive (user)
- E18 reclassified: execution-engine diagnostic ONLY. Not evidence of gate
  contribution, adverse selection, or entry viability.
- Optimization PAUSED until new correctness gates pass: OCO single-exit
  cycle invariant, exact ledger↔portfolio reconciliation, fees/slippage on
  mapped contracts, partial fills, rollovers, protocol-conformance
  versioning, paired shadow entry models + candidate-matched ablations,
  deterministic replay, execution invariants.
- Validation + holdout LOCKED. Next dev rerun designated E18R; artifacts
  packaged for independent audit before validation unlocks.


## E19 — EVENT STUDY VERDICT (2026-08-23, v2.5.6)
- 952 bias-aligned sweep/reclaim events resolved at 30/60/120/240m.
- All horizons: |mean| < 1bp, WR 50.7-51.6%, z < 1. NO directional information.
- Pre-registered rule: rescue precondition NOT met -> strategy family ARCHIVED.
- Validation/holdout never touched. No rescue experiments conducted.

---

# REVIEW ROUND 6 (E19B directive, 2026-08-23) - engine v2.6

Directive adopted in prescribed order. No optimization started; validation/holdout LOCKED.

## Record corrections (before any new run)
- E18S_RESULTS.md RETRACTED: "rec_ok=1 strict identities" and "first positive-expectancy
  configuration" were false - same file shows r_sum +20.261 vs rec_i1_profit_raw -985.0 /
  rec_tpv_delta -1879.4. Root causes: frictionless atomic booking (exit_px = stop_px/tp_px,
  zero slip/fees), I1 never compared the ledger expectation, I2 compared per-trade modeled fee
  to total actual inside an always-true band, I3 unfailable on EOD exits (_eod_resolve
  incremented atomic_exits). ablFVG-mkt +0.099R VOID as edge evidence.
- E19_EVENT_STUDY.md RELABELED raw bias-aligned level-penetration diagnostic: events_only
  returned after min-penetration check, BEFORE depth reject and reclaim (funnel proof:
  f_attempts_used=952, f_L_sweep_ok=0, f_depth_rejects=0, f_no_reclaim=0). No sigma/t/CI/
  block-bootstrap/MFE-MAE; stated 10-20 bps event vol contradicts NQ ~50-70 bps @120min.
  True reclaimed population 449 (952 -> 159 depth rejects -> 449). Archive verdict WITHDRAWN:
  at best INCONCLUSIVE; family archive suspended pending E19B.

## Engine v2.6 fixes (each gated by a negative test)
- Barrier exits carry slippage + round-turn fees; rows publish r_gross / r(net) / friction_r.
- Identity 1 GATE: ledger expectation sum(r_net*risk_dist*pv*qty) vs trade_builder P&L, $25 tol.
- Identity 2 FIXED: modeled TOTAL vs actual TOTAL fees ($25 tol).
- Identity 3 SPLIT: exits_barrier_stop / exits_barrier_tp / exits_eod + barrier purity
  (|r_gross| == 1 or target_r by construction); publishes median_risk_dist, friction_R_total.
- tz regression fixed: exit_time stamped from algo clock (ET), astimezone(UTC) path removed.
- Starvable _resolve_cycle_minute fixed: minute bars queue and drain fully each step.
- Local suite 18/18 green. AST-verified comment compression 71,918 -> 62,005 chars (cloud <64k).
- LEAN CLI installed locally (1.0.228) - seventh request honored; ledger export unblocked.

## E19B pre-registration (PREREGISTRATION_E19B.md, frozen BEFORE data)
- Population: post-reclaim confirmed candidates only (expect ~449 NQ dev), permanent IDs,
  CISD/FVG/IFVG as labels on ONE immutable population; paired counter-bias arm.
- Measurement: R-unit forward returns (event's own risk_dist), H*=120min primary horizon,
  full EVENT-ledger export, MFE/MAE exploratory-only.
- Reporting: n, sigma, SE, 95% CI, MDE(80%) BEFORE any p-values; inference offline via
  session-block bootstrap (B=10k, arms resampled jointly).
- Three outcomes: POSITIVE (CI excludes 0 AND mean > 0.2R) / NULL (CI excludes MDE) /
  INCONCLUSIVE (CI contains MDE boundary). Only NULL earns "archived"; only POSITIVE opens
  the capped 6-8-run rescue study (rescue simulator MUST carry slippage+fees).
- Multiplicity in writing: single primary hypothesis is the sole rescue trigger; everything
  else EXPLORATORY; Holm-Bonferroni over fully enumerated family upon any promotion;
  stable-positive = Holm-significant AND >=12/15 LOYO sign-stable AND >=3/4 markets AND >0.2R.
- Replication plan: ES/YM/RTY dev-window data only (~1,800 pooled events). No locked data touched.
- E19B NOT YET RUN: requires corrected-engine cloud compile + smoke gate, then directive
  authorization sequence.


---

## E19B — UNFLOORED EVENT STUDY (closed 2026-08-25, tag e19b-provisional @ 7de3be0)

- Preflight (one commit): two-sided arming (bias_aligned tag isolates HTF gate),
  shared event_id per reclaim, real ES/YM/RTY spec table, bps threshold
  normalization, excursion-cumulative depth kill, wall-clock horizons,
  chart-series ledger channel (ObjectStore export license-blocked), shadow
  CISD/FVG/IFVG labels, fill-based economics, rollover pricing fix.
- One-year NQ smoke: artifact completeness (288/288 rows via charts) +
  deterministic replay equality.
- Full run: 15,024 event-horizon rows; primary H*=120m raw mean −0.0091R,
  iid CI [−0.2414,+0.2263] → INCONCLUSIVE. No rescue study opened.

## E19B-R — FLOORED EVENT STUDY (closed 2026-08-25, tag e19b-r-final)

- Preregistered population-conformance correction BEFORE rerun:
  tradability floor risk_dist ≥ max(min ticks per instrument,
  0.10×ATR14(5m)); θ and three-outcome rule unamended; frozen unfloored
  primary retained alongside.
- Offline replication gate passed pre-cloud (directive's own bootstrap
  reproduced: raw INCONCLUSIVE / winsorized NULL on committed ledgers).
- CRITICAL DEFECT FOUND MID-COURSE (commit e207dcc): floor params present in
  defaults but MISSING from the raw parameter read list → cloud silently
  used 0.0 and the floor never bound (2,516 violations detected). Fixed;
  regression test `test_floor_params_in_read_list` added; all four markets
  rerun on compile 3605cbb7 → 12,004 rows, 0 violations.
- Result: floored H*=120m −0.0787R iid CI [−0.352,+0.219] INCONCLUSIVE;
  winsorized ±5R −0.1145 [−0.278,+0.051] NULL; bias-gate control aligned
  −0.079 vs rejected +0.121 (z=−1.16); MFE/MAE: 68.9% reach MAE ≤ −1R vs
  45.8% reaching MFE ≥ +2R.

## CAMPAIGN CLOSEOUT (documentation-only commit)

- Outcome label: administratively closed campaign — INCONCLUSIVE raw
  primary + NULL winsorized sensitivity; NOT a pre-registered primary NULL.
- Four separated layers recorded in CAMPAIGN_CLOSEOUT.md: frozen primary /
  floored primary / post-hoc robustness (winsorized+trimmed NULL at every
  horizon; every market CI contains zero except ES-240m marginal) /
  mechanism (exploratory).
- Exactly one defect disclosed: published CIs were iid not session-clustered
  (sessions=n=1121 printed while ledger holds 895 distinct session-dates;
  SEs match σ/√1121 exactly). Correctly clustered CIs are reproducible from
  committed ledgers and change no verdict (raw ≈[−0.374,+0.230]
  INCONCLUSIVE; winsorized ≈[−0.298,+0.070] NULL). Reclaim timestamps are
  recoverable (reclaim_ts = ts − h_min×60); only true gaps: missing
  permanent event_id + this statistical error.
- Five findings preserved: estimator-design lesson (raw mean of unbounded
  ratio structurally unable to return NULL); MFE/MAE mechanism; bias-gate
  selects worse half; 60m omitted from closeout-facing prose (present in
  result tables; raw INC / wins NULL); floor composition shift (ES −45%/
  RTY −18%/NQ −10%/YM 0%) making primaries non-identical populations, and
  the ATR clause never bound (below tick floor everywhere).
- Campaign 2: branch of THIS repo (durable asset = engine v2.8 + identity
  gates + null infra + ledger channel + smoke gate + regression suite);
  must screen bracket geometries offline against the 3,001-candidate H*
  MFE/MAE ledger before hypothesis selection; fresh prereg with bounded
  primary estimator, ex-ante normalizer, sessions<n assertion; optimization
  prohibited absent a demonstrated robust edge.

---

## 2026-08-26 — E19B-R first-touch screen WITHDRAWN

`e19br_ft_screen.json` from commit `6f738fb` is withdrawn and deleted from
the current tree. It is not evidence, must not be cited, and cannot support
Campaign 2 hypothesis selection. E19B-R and the administrative closeout are
unchanged.

The withdrawal is compelled by three reproducible defects:

1. The four committed `e19br_ft_ledger/*_ft.jsonl` files are empty,
   `e19br_ft_results.jsonl` contains no `ft*` RuntimeStatistic, and
   `d44_e19b_ft.py` did not retrieve either chart series. The claimed
   per-event first-touch provenance therefore cannot be reconstructed from
   the repository.
2. For several fixed targets, both `p_target_given_decided` and `n` are
   identical across multiple stop widths. A wider stop must weakly reduce
   stop-first outcomes, so the equality proves that stop width did not
   participate in those resolutions.
3. Every reported cell is exactly reproduced by
   `p*T - (1-p)*S` using a target-specific `p` insensitive to `S`. This
   mechanically rewards tighter stops, repeating the bias of the unordered
   MFE/MAE screen. The reported `mean_R` also used `risk_dist` units rather
   than units per amount risked; comparable bracket returns require division
   by stop width.

Repair is restricted to the development-only `events_only` export: one
32-bit value per event (two bits for each of 16 cells), one chart series,
an `n_ft_rows` RuntimeStatistic reconciled exactly to retrieved ledger rows,
per-unit-risked reporting, and permanent monotonicity/non-empty-ledger tests.
No strategy backtests or optimization are authorized. Validation and holdout
remain locked, and Campaign 2 hypothesis selection remains blocked pending a
valid replacement screen.
