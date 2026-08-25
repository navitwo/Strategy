# E18S — ATOMIC ENGINE PARALLEL VARIANT RERUN (v2.5)

All four variants on identical immutable population, NQ 1-contract,
2010-01→2024-12 dev. **Every run rec_ok=1 under strict identities:
cycles == atomic_exits == ledger rows, anomalies=0, untracked=0,
late≤1, I1 cash residual 0.0.**

| variant | n | WR% | avg R | PF(R) |
|---|---|---|---|---|
| candidate (sweep stop) | 54 | 27.8 | −0.237 | 0.66 |
| ablCISD (trigger bypassed) | 60 | 26.7 | −0.273 | 0.61 |
| shadowMOC (marketable entry) | 70 | 37.1 | −0.562 | 0.31 |
| ablFVG-mkt (no FVG gate) | **205** | **42.4** | **+0.099** | **1.18** |

## Findings
1. **Execution engine fully reconciled**: one clean exit per cycle across
   389 total cycles; zero races/anomalies by construction (atomic simulator).
2. **ablFVG-mkt is the first positive-expectancy configuration ever recorded**
   (+0.099R, PF 1.18, n=205). CAVEAT: it changes two factors vs candidate
   (removes FVG gate AND enters at marketable limit). Attribution between
   "FVG gate harmful" and "marketable entry beneficial" requires ablFVG with
   resting entry — not yet run.
3. shadowMOC (marketable entry WITH FVG gate) is worse than candidate
   (−0.562): entering immediately when the FVG gate passes selects badly.
   Combined with ablFVG-mkt positive: value lives in *entering earlier on
   non-FVG-confirmed signals*, i.e., the FVG gate itself is the liability.

## Next per directive
Block-bootstrap forward-return/MFE/MAE event study on the HTF-bias +
sweep/reclaim universe to test whether directional information exists at
all before any rescue experiments are considered.
