# PROTOCOL CONFORMANCE — v2.3 (2026-08-23)

Written protocol: `PROTOCOL.md` (frozen 2026-08-23, v1.0 baseline).
This document formally versions every divergence between the protocol text
and the shipped implementation. Each deviation carries an ID, a rationale,
and is asserted by `test_protocol_conformance()` so silent drift is
impossible.

## Conformant core (asserted, not assumed)
- C1 Instrument: NQ/MNQ futures; signals on continuous RAW; orders ONLY on
  `fut.mapped` (all 6 submission sites verified mapped).
- C2 HTF bias: 4H buckets from completed 5m bars, wall-clock span ≥210 min,
  first-bar offset ≤5 min into bucket; pivots L/R confirmed with contiguous
  publication (no partial-bucket pivots).
- C3 Liquidity: PDH/PDL strictly from COMPLETED prior session; rotation on
  completed-bar clock inside the consolidator callback.
- C4 Session: entries only inside 09:30–12:00 ET window, DST via
  America/New_York algorithm timezone.
- C5 Long sequence order: bias → PDL sweep → reclaim → CISD → IFVG inversion
  → retest fill. Shorts mirrored symmetrically (see D1).
- C6 Stop: sweep extreme ± buffer ticks; Target: 2R fixed; risk $ fixed;
  size-skip when 1 contract exceeds risk; max one position; no pyramiding.
- C7 No lookahead: every gate consumes only completed bars; pivot right-side
  confirmation enforced; TZCHECK asserts first-RTH stamp 09:35 ET.
- C8 EOD flatten at session boundary; no overnight positions.

## Versioned deviations from the written protocol
| ID | Protocol text | Shipped v2.3 | Rationale |
|----|---------------|--------------|-----------|
| D1 | "Implement the exact inverse" for shorts | Mirrored short CISD uses same reference-open rule as long (symmetric function, single code path) | Symmetry-by-construction beats duplicated logic; tested by mirror test |
| D2 | FVG eligibility "formed before or during the decline" | Scan all gaps with created ≤ idx−1, age ≤ fvg_max_age_bars(60), nearest-to-price selection | Original `created ≤ extreme_idx` was over-restrictive (E16 diagnosis); nearest-gap fixes unreachable-zone bug |
| D3 | Inversion requires close through midpoint | Close beyond midpoint within inv_max_bars; `through` filter removed | Through-filter made inversion ~impossible; midpoint rule retained per spec |
| D4 | Pivot timing "confirmed when right bars close" | Confirmation additionally requires contiguous publication (gap invalidates pending pivots) | Data holes must not confirm structure |
| D5 | EOD exit implied by intraday-only session | Explicit EOD flatten market order + rollover fail-closed flatten | Execution realism; stale position context across rolls |
| D6 | entry_location unspecified (retest) | cfg knob: proximal (V1.0 default) / midpoint (E05) / gap_far (B2-E12) | Parameter family testing per §21 Phase 4 |
| D7 | Attempt counting unspecified | One armed attempt per level per session; counters per stage | Funnel attribution (§31) |
| D8 | Slippage 1 tick each way | LEAN native fills; slippage_ticks cfg knob (default 1) applied in stress mode | Deterministic base; stress overrides |

## Paired shadow models (replacing unfilled-watcher & random null)
Per review round 5: candidate-matched ablations share signal, validity
window, stop, target, and market conditions with the candidate; only the
studied factor differs. Implemented as paired runs:
- SHADOW-A: identical everything, entry at inversion-close (market) instead
  of resting retest limit → isolates adverse-selection exposure.
- ABLATION-B: candidate minus CISD gate → measures CISD's marginal selectivity.
- ABLATION-C: candidate minus FVG-inversion gate → measures FVG contribution.
The random null and unfilled-order watcher are RETIRED from evidence use;
watcher code remains but its output is diagnostic-only.

## Gate suite required before E18R
G1 local chronology suite green · G2 OCO single-exit invariant ·
G3 deterministic replay (same seed ⇒ identical ledgers) ·
G4 execution invariants (one-exit-per-cycle, no unregistered fills,
mapped-only orders) · G5 protocol conformance assertions ·
G6 smoke gate (rec_ok=1 cash identity on multi-trade window).


---

## v2.6 additions (review round 6, E19B directive - 2026-08-23)

- D9: barrier exits carry slippage + round-turn fees; ledger rows publish
  r_gross / net r / friction_r. Frictionless atomic booking is PROHIBITED
  (it produced E18S's false positive).
- D10: Identity 1 gate = ledger expectation sum(r_net*risk_dist*pv*qty) vs
  trade_builder profit_loss ($25 tolerance); Identity 2 = modeled TOTAL vs
  actual TOTAL fees; Identity 3 splits barrier/EOD exit counters with
  barrier-R purity assertions. Every gate ships with a negative test
  proving it can go red (test_identity_gates_can_go_red).
- D11: cycle resolution drains queued minute bars every step (stop cannot
  starve); exit timestamps use algo clock (ET) - bar.end_time UTC
  conversion is banned from ledger paths.
- D12: events_only candidates publish ONLY after reclaim confirmation,
  permanent cand_ids, R-unit forward returns + MFE/MAE, optional paired
  counter-bias arm. Raw-attempt capture RETIRED (E19 reclassified as a
  raw level-penetration diagnostic).
- G7: PREREGISTRATION_E19B.md predates any E19B data pull; cloud runs
  publish n/sigma/SE/CI/MDE only - inference happens offline via
  session-block bootstrap under that document's rules.
