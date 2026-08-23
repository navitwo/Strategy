# BATCH 3 — CORRECTNESS RESET & NULL STUDY (2026-08-23)

Triggered by external review: 4 correctness bugs invalidated all prior results.
All 20 Batch 1–2 results are hereby marked INVALID and superseded.

## Bugs fixed (engine v2.0, each with regression tests where local-testable)
1. **5m grid misalignment** — buckets keyed by algorithm slice time (off-by-one);
   fixed to standard :00 grid keyed by bar START time; flush on bar's own end time.
2. **4H partial publishing** — 8-bar guard let 40-minute fragments publish;
   fixed to wall-clock-span coverage (≥210 min, start offset ≤1 min) + contiguous-
   publication requirement for pivot confirmation (h4_gap_pending invalidation).
3. **PDH/PDL session leak** — `_advance_session` ran before `_flush_5m`, so the
   final bars of a session leaked into the NEXT session's levels; order swapped.
4. **R-ledger drift** — ledger was an independent counter that diverged from the
   equity curve; replaced with equity-snapshot accounting per trade + hard
   reconciliation gate (|designed − observed| ≤ max(1%, $25)) + cross-check
   (cloud fills == ledger trades). Race-reversal PnL excluded and reported.
Also added: EOD flatten at every session boundary; rollover detection counter.

## Additional defects found & fixed during the reset
5. R computed from DESIGNED entry instead of ACTUAL fill (dominant residual).
6. Null-mode entries submitted before setup registration → untracked fills;
   caught by the new fills==trades gate prong.
7. `self.utc_time` used as bar time (breaks under multi-slice data).

## Structural changes (per review)
- Instrument switched to **NQ with 1-contract sizing** (risk_usd=10000) so
  history back to 2010 is usable; R math is sizing-independent.
- Artificial inversion throttles removed: `through` filter deleted;
  `created <= extreme_idx` restriction removed (scan all gaps ≤ idx−1);
  nearest-to-price gap selection installed.
- Per-trade ledgers exported via Debug `TRADES {...}` for offline pandas.
- Random-entry null engine (`entry_mode=random`, deterministic hash draws,
  identical bracket geometry/costs) for gate-contribution measurement.

## E16 study results (NQ, 2010-01 → 2024-12, dev only)
| run | trades | wins | avg R | sum R | rec_ok |
|---|---|---|---|---|---|
| signal (all gates) | 3 | 1 | −0.21 | −0.64 | 0 |
| null p=0.0002 | 21 | 6 | −0.55 | −11.6 | 0 |
| signal + gap stop | 2 | 0 | −1.00 | −2.00 | 0 |
| null + gap stop | 9 | 3 | −0.55 | −4.97 | 0 |
| null p=0.02 | 38 | 11 | −0.44 | −16.7 | 0 |
| null p=0.04 | 61 | 16 | −0.56 | −34.4 | 0 |
| null p=0.10 | 36 | 9 | −0.62 | −22.3 | 0 |
| null p=0.10 gap | 82 | 28 | −0.27 | −21.8 | 0 |

## Findings
1. **Signal trade count is structurally tiny (3 fills / 15 years)** — the
   retest-at-proximal-edge entry model is the binding constraint (13 inversions
   → 13 submits → 3 fills; expiry+window cancels dominate). n in the hundreds
   is unreachable for THIS entry model without changing it.
2. **Null expectancy is negative at every calibration** (−0.27R to −0.62R),
   consistent with 1-tick slippage + $1/round-turn commissions on 2R brackets:
   random entries lose roughly the friction. Signal avg R (−0.21, n=3) is
   statistically indistinguishable from the null (−0.55, n=21) at this sample.
3. **Gate contribution cannot yet be measured**: signal n=3 vs null n=21 —
   the comparison is underpowered by 2 orders of magnitude.
4. **Reconciliation gate still fails (rec_ok=0)** on all runs — residuals
   remain after the fill-price fix, indicating remaining unmodeled economics
   (likely EOD-flatten marks and race-leg accounting). MUST be driven to zero
   before any result is usable. This gate is now the blocking item.

## Verdict
- The strategy AS SPECIFIED cannot reach n≥200 on dev without an entry-model
  change (retest model) — that is a strategy redesign decision, not a fix.
- No frozen candidate exists; **validation remains LOCKED**.
- Bootstrap CI computation deferred until (a) rec_ok passes and (b) either the
  entry model is redesigned for sample or the null comparison is reframed.

## Next steps (require authorization)
1. Drive reconciliation residual to zero (audit EOD marks, race legs, fees).
2. Decide entry-model redesign (e.g., market-on-inversion instead of
   retest-limit) to unlock sample, then re-run the null study at n≥200.
3. Only then: frozen candidate → bootstrap CI → fill-realism stress → validation.
