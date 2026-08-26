# E19B-R ANALYSIS (floored primary; prereg rule unamended)

Floor: max(min_stop_ticks, 0.10*ATR14(5m)) at arm time.
Population: bias_aligned==True pooled across markets.

| h | n | sessions | mean R | CI lo | CI hi | SE | verdict |
|---|---|---|---|---|---|---|---|
| 30m | 1121 | 1121 | +0.0055 | -0.1350 | +0.1538 | 0.0741 | **NULL** |
| 60m | 1121 | 1121 | -0.0006 | -0.2017 | +0.2097 | 0.1058 | **INCONCLUSIVE** |
| 120m | 1121 | 1121 | -0.0787 | -0.3519 | +0.2187 | 0.1432 | **INCONCLUSIVE** |
| 240m | 1121 | 1121 | -0.1161 | -0.4791 | +0.2591 | 0.1883 | **INCONCLUSIVE** |

PRIMARY H*=120m: n=1121 sessions=1121 mean=-0.0787R CI=[-0.3519,+0.2187] -> **INCONCLUSIVE**
Frozen unfloored primary (e19b-provisional): -0.0091R CI [-0.2414,+0.2263] INCONCLUSIVE — both published.
Winsorized +-5R H*: mean=-0.1145 CI=[-0.2776,+0.0510] -> NULL

Bias-gate control at H*: aligned -0.0787 (n=1121) vs rejected +0.1207 (n=1880), z=-1.16

MFE/MAE study (H*, aligned): median MFE=+1.786R, median MAE=-1.905R, mean MFE=+2.737R, mean MAE=-2.857R

## Invariants
ledger md5 (core fields): `de187ca2c8e6731b92c7d0ea2a6f82fd`
- floor_violations: 0
- rows_total: 12004
- one_row_per_event_horizon: True
