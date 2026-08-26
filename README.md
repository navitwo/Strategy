# SCIFVG — Sweep → CISD → IFVG Research Campaign

Quantitative research campaign for an NQ/MNQ liquidity-sweep strategy built and tested
**exclusively on QuantConnect Cloud (LEAN)**. Private research repository — no live trading.

> **Status: CAMPAIGN ADMINISTRATIVELY CLOSED (2026-08-25) — see
> [CAMPAIGN_CLOSEOUT.md](CAMPAIGN_CLOSEOUT.md)**
>
> Outcome: **INCONCLUSIVE raw primary** (floored H\*=120m −0.079R, CI
> straddling +0.2R) with a **NULL winsorized sensitivity** — not a
> pre-registered primary NULL. No rescue, no optimization. Validation and
> holdout were never touched and remain locked.
>
> Successor work (Campaign 2) proceeds as a branch of this repository and
> must begin with an offline screen against the committed 3,001-candidate
> MFE/MAE ledger before any hypothesis is selected.

## Strategy chain

```
4H bias → PDH/PDL sweep (depth-capped) → reclaim confirm → CISD trigger
        → bearish-FVG inversion → limit retest at zone edge → 2R target
```

Executed on **MNQ** (micro Nasdaq-100) with orders on the mapped front contract;
continuous canonical data via OPEN_INTEREST mapping. NQ variant exists as a
cross-instrument stress test only.

## Methodological rules (frozen in PROTOCOL v1.0)

- **Frozen protocol**: changes require a version bump; experiments are named
  `SCIFVG-v<maj>-<min>-<slug>-<hash8>` and duplicates are rejected by identity.
- **Design-R ledger only**: cloud PnL was contaminated by OCO same-bar race round-trips,
  so all verdicts come from the `r_*` RuntimeStatistics ledger (`r_trades`, `r_wins`,
  `r_avg`, `r_pf`, `r_maxconsecL`, …).
- **Anti-lookahead by construction**: completed 5m bars only, pivots confirmed with
  right-side bars, PDH/PDL from completed prior sessions, every gate timestamped knowable.
- **Costs modeled**: $0.50/side/contract commission, 1 tick slippage per fill,
  $100 fixed risk, position size floored (qty 0 ⇒ skip).
- **Sample-quality gate**: <30 dev trades ⇒ INSUFFICIENT SAMPLE verdict; concentration
  warnings precede PF/PnL in ranking.
- **Data segmentation** (dev tuned; everything else locked):
  | Segment | Range | State |
  |---|---|---|
  | Development | 2023-01-03 → 2025-04-30 | Batch 1–2 runs here |
  | Validation | 2025-05-01 → 2026-01-01 | **LOCKED** |
  | Holdout | 2026-01-01 → present | **UNTOUCHED** |

## Results summary

| Phase | Outcome |
|---|---|
| Baseline (v1.0.2 control) | −0.31R avg/trade; funnel: ~140 attempts → 2 fills |
| Batch 1 (E01–E10) | No edge. Best: E07 earlier window (−0.09R, n=10). Binding constraints: inversion scarcity + ~25% win rate at 2R |
| Batch 2 (B2-E11–14) | **B2-E12** (`stop_mode=gap`): +0.05R avg, PF(R) 1.08, maxCL 2 on n=11. Loss mechanics (sweep-extreme stop) identified as the damage center |
| E18S correctness reset (engine v2.5, atomic bracket sim) | All four variants rec_ok=1 under strict identities; ablFVG (no FVG gate) first positive expectancy (+0.099R PF 1.18) — flagged to event study, not conclusive |
| E19 / E19B event study (unfloored, `e19b-provisional`) | 15,024 rows; primary H\*=120m raw mean −0.009R, INCONCLUSIVE; 30m NULL; no rescue opened |
| E19B-R floored study (v2.8, `e19b-r-final`) | 12,004 rows, 0 floor violations; floored H\*=120m −0.079R INCONCLUSIVE; winsorized NULL at every horizon (post-hoc); bias-gate control z = −1.16 |
| Closeout | Administratively closed; one disclosed defect (iid CIs vs session-clustered — verdicts unchanged); see [CAMPAIGN_CLOSEOUT.md](CAMPAIGN_CLOSEOUT.md) |

Full details: [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) · Protocol: [PROTOCOL.md](PROTOCOL.md)

## Repository layout

| Path | Purpose |
|---|---|
| `PROTOCOL.md` | Frozen campaign protocol (v1.0 + governance rules) |
| `EXPERIMENT_LOG.md` / `experiment_log.jsonl` | Human-readable ledger + append-only raw log |
| `scifvg_main.py` | Strategy implementation (LEAN engine, v2.8 — atomic bracket simulator, tradability floor, chart-series ledger channel) |
| `test_scifvg_local.py` | Local regression suite (19 tests incl. read-list/defaults consistency, mirrored-CISD, atomic invariants) |
| `qc_api.py`, `run_exp.py` | QuantConnect REST harness (compile/poll/backtest lifecycle) |
| `d01…d16_*.py`, `b2_*.py` | Diagnostics & result-fetch probes per experiment |
| `*_out.txt`, `probe*_result.json` | Per-run output artifacts |

## Prerequisites

- QuantConnect account (cloud project `NQ CISD IFVG 2026`, id 35506697)
- Credentials go in `quantconnect_credentials.env` — **gitignored, never committed**

---

*Research artifact. Nothing here is financial advice or a production trading system.
All results are simulated, cost-modeled backtests on QuantConnect Cloud infrastructure.*
