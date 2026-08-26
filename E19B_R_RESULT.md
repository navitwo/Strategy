# E19B-R — FLOORED EVENT STUDY RESULT (2026-08-25)

Pre-registered population-conformance correction (tradability floor on
`risk_dist`: ≥ min ticks AND ≥ 0.10×ATR14(5m) at arm time) applied; θ=0.2R
and the three-outcome rule unamended. Frozen unfloored primary from
`e19b-provisional` remains published alongside.

## Offline gate (pre-cloud)
Directive's own bootstrap reproduced on committed ledgers: 1,381 aligned
events / 1,031 session-dates; raw CI [−0.240,+0.233] INCONCLUSIVE;
winsorized ±5R CI [−0.217,+0.098] NULL. Top-9 events +206.3R vs whole-
sample −12.58R; +71R extreme ⇒ stop ~1/71 of the 120-minute move.

## Critical defect found and fixed pre-analysis (commit e207dcc)
First cloud rerun showed 2,516/14,528 rows below the tick floor: the floor
parameters were declared in `defaults` but **missing from the raw parameter
read list**, so cloud runs silently used 0.0 and the floor never bound.
Regression test added (`test_floor_params_in_read_list`). All four markets
rerun on compile 3605cbb7. Post-fix: **0 violations in 12,004 rows**.

## Result (12,004 rows; NQ 4,084 / ES 2,036 / YM 4,176 / RTY 1,708)
| h | n | sessions | mean R | 95% CI | SE | verdict |
|---|---|---|---|---|---|---|
| 30m | 1121 | 1121 | +0.006 | [−0.135,+0.154] | 0.074 | **NULL** |
| 60m | 1121 | 1121 | −0.001 | [−0.202,+0.210] | 0.106 | INCONCLUSIVE |
| 120m | 1121 | 1121 | −0.079 | [−0.352,+0.219] | 0.143 | INCONCLUSIVE |
| 240m | 1121 | 1121 | −0.116 | [−0.479,+0.259] | 0.188 | INCONCLUSIVE |

Winsorized ±5R at H\*: mean −0.1145, CI [−0.278,+0.051] → **NULL**.

## Primary verdicts
- **Floored primary (H\*=120m): INCONCLUSIVE** — CI straddles 0.2R.
- Winsorized H\*: NULL.
- Frozen unfloored primary: INCONCLUSIVE (unchanged).

## Bias-gate control (H\*, floored)
aligned −0.0787 (n=1121) vs bias-rejected +0.1207 (n=1880), z = −1.16.
Directionally consistent with every prior ablation: the HTF-bias filter
selects the worse half, but not significant.

## MFE/MAE study (exploratory; cannot rescue a null under §5)
Median MFE +1.79R, median MAE −1.91R (means +2.74/−2.86). Excursions are
symmetric and large relative to |mean drift| — consistent with a coin-flip
process whose barriers, not its direction, dominate realized outcomes.

## Invariants
- Ledger md5 (core fields): de187ca2c8e6731b92c7d0ea2a6f82fd
- floor_violations: 0 · rows_total: 12004
- one row per event per horizon: verified

## Consequence (rule applied without amendment)
INCONCLUSIVE permits neither rescue nor optimization. The campaign remains
archived with no declared path to rescue from this design family; any
future attempt requires a NEW hypothesis family with its own preregistration,
not another amendment of this one.
