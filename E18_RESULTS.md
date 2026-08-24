> **STATUS: EXECUTION-ENGINE DIAGNOSTIC ONLY — NOT EDGE EVIDENCE.**
> Reclassified by directive 2026-08-23 (review round 5). The numbers below
> validate engine mechanics (reconciliation identities, fill accounting),
> NOT gate contribution, adverse selection as an edge finding, or entry
> viability. Superseded by E18R after the v2.3 correctness gates.
> Validation and holdout periods remain LOCKED; optimization PAUSED until
> the new correctness gate suite passes.

# E18 — GATE-CONTRIBUTION & ADVERSE-SELECTION STUDY (engine v2.2, rec_ok=1)

Precondition: SMOKE GATE PASS on FY-23 (bid c2cf1e05…): 6 trades, TZCHECK
09:35, bars/session 271.9 (unfragmented), rec_ok=1 under the three cash
identities (trade_builder authority: Σprofit−fees ≡ TPV delta, exact).

## Runs (NQ, max_contracts=1, 2010-01→2024-12, dev only)
| run | n | wins | WR | avg R | PF(R) | avgW | avgL |
|---|---|---|---|---|---|---|---|
| E18a signal (sweep stop) | 46 | 8 | 17.4% | −0.399 | 0.55 | +2.81* | −1.08 |
| E18b null p=.02 | 873 | 258 | 29.6% | −0.304 | 0.66 | +1.98 | −1.26 |
| E18c null p=.06 | 1401 | 414 | 29.5% | −0.337 | 0.63 | +1.92 | −1.28 |
| E18d signal (gap stop) | 51 | 19 | 37.3% | **−0.050** | 0.94 | +2.04 | −1.29 |
| E18e null gap p=.06 | 1232 | 353 | 28.7% | −0.359 | 0.61 | — | — |

All five runs rec_ok=1. *E18a avgW>2R is the flatten-row artifact now
classified is_race and excluded from headline stats in future runs; E18a's
−0.40R should be read as ≤ that with wide error (n=46).

## Gate contributions (signal avgR − matched null avgR)
| gate set | contribution |
|---|---|
| full chain, sweep stop | **−0.095 R** (worse than null) |
| full chain, gap stop | **+0.308 R** (better than null) |
| stop-mode effect on signal | +0.349 R |
| stop-mode effect on null | −0.054 R |

## Adverse-selection test (submitted-but-unfilled entries, forward TP/stop)
| run | unfilled resolved | would-win |
|---|---|---|
| E18a | 24 (19W/5L) | **79.2%** |
| E18d | 19 (17W/2L) | **89.5%** |

## Findings
1. **Adverse selection confirmed.** Setups whose resting limit never filled
   won 79–90% of the time forward — the fill itself selects against the
   hypothesis. The retest-at-proximal entry model is the primary edge leak,
   exactly as suspected: you get filled when the level fails.
2. **Gate chain selects against you under sweep-stop**: signal WR 17.4% vs
   null 29.6% on identical geometry — the chain filters TO losing fills.
3. **Gap stop flips both sign and selection**: signal 37.3% > null 28.7%,
   contribution +0.31R. The information is real but was being destroyed by
   stop placement through the swept level.
4. Null parity verified post-fix: null avgW/avgL ≈ +1.98/−1.26 (passive
   limit friction), no longer the artificial +1.54/−1.24.

## Status vs promotion criteria
- Sample: 51 dev trades (gap-stop) — below the ≥200 frozen-candidate bar.
- Bootstrap CI on +0.31R contribution pending ledger export; n_null=1232
  gives tight null CI, signal n=51 gives ±~0.28R SE → contribution is
  suggestive, not confirmed.
- Validation remains LOCKED.

## Next (requires authorization)
1. Entry-model redesign to attack adverse selection (e.g., market-on-
   inversion-close, or limit beyond proximal edge) — measure whether the
   79–90% would-win population becomes capturable.
2. Export per-trade ledgers → bootstrap CI on gate contribution.
3. Fill-realism stress (2–3 ticks/side) on the gap-stop variant.
