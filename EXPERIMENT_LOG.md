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
