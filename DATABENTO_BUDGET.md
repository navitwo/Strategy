# Databento Budget — standing cost-control record

This file exists so the account's spend state never has to be manually
re-read for routine work. It is maintained by the same discipline as the
preregistration documents: every number has a source and a date.

## Standing rules (enforced in code, not intent)

1. **The tracked figure below is an INFERRED estimate, not a balance.**
   Databento exposes no balance/credits endpoint (probed 2026-09-04:
   `billing.balance`, `billing`, `billing.charges`, `users.get` all HTTP 404
   on hist/api hosts; official client 0.86.0 offers only
   batch/metadata/symbology/timeseries services). Any local number drifts.
   **Before ANY request estimated above $10, re-verify the balance manually
   from https://databento.com/portal/billing.** Code enforcement:
   `d48_databento_purchase.py` refuses any purchase whose live quote
   exceeds $10 unless the operator sets `DATABENTO_PORTAL_REVERIFIED=1`
   (asserting the portal check was just done), in addition to `CONFIRM=1`.
2. **If inferred and actual diverge by more than $1, STOP and reconcile
   before spending.** The ceiling check in `d48_databento_purchase.py`
   (re-quote immediately before submission, abort above MAX_USD) is the
   in-code enforcement of the same principle for purchases.
3. Credits die on a clock regardless of remaining balance (see expiry
   below) — a healthy inferred balance does NOT imply spendable balance
   after the expiry date. Re-verify after 2027-02-09 before any purchase.

## Account state

| item | value | source |
|---|---|---|
| Portal-verified balance | **$124.68** as of 2026-09-04 | user, billing page |
| New-account credit grant | $125.00 | account terms |
| Credits expire | **2027-02-09** (six months from account creation; creation evidenced by the three sample jobs dated 2026-08-09) | portal + job list |
| Payment method on file | yes — overage becomes a real charge | account terms |

### $0.32 pre-purchase consumption — reconciled

The first `batch.list_jobs` call (2026-09-04) showed exactly three jobs, all
from 2026-08-09, all `XNAS.MDP` sample data (Microsoft: `trades`, `ohlcv-1m`,
`mbo`). These are the account-creation sample pulls and account for the
$125.00 − $124.68 = **$0.32** gap. No unexplained spend remains.

## Spend ledger

| date | request | get_cost quote | actual charge | inferred remaining |
|---|---|---|---|---|
| 2026-08-09 | XNAS sample jobs ×3 (trades/ohlcv-1m/mbo MSFT) | — | $0.32 | $124.68 (portal-verified 2026-09-04) |
| 2026-09-04 | C2 purchase: GLBX.MDP3 ohlcv-1m + definition, NQ.n.0+GC.n.0 continuous, 2010-06-07→2026-09-04 (d48, ceiling $45) | **$38.04** (re-quoted immediately pre-submit) | ohlcv-1m **$38.031821** + definition **$0.008394** (job fields; sum $38.0402 = quote exactly) | **≈ $86.64** |

*Quotes vs actuals: Databento bills the confirmed job cost, which for
batch bulk jobs matches the pre-quote at the same range. If post-purchase
portal reconciliation shows |actual − $38.04| > $1, rule 2 above applies.*

### Purchased container provenance (tracked; the files themselves live under git-ignored data/databento/)

| file | bytes | sha256 |
|---|---|---|
| glbx-mdp3-ohlcv-1m.zip | 156,181,748 | c73fa087a7145d1ccce136042ad03c9cd495692a06a77b9e474dcd5f51d1287f |
| glbx-mdp3-definition.zip | 6,313,758 | 29dfb228a939d60156502f1f0e901891cc1d4df199a7aa38c0beb04334620b08 |

Jobs: ohlcv-1m GLBX-20260904-77GSFBPBNT ($38.031821); definition
GLBX-20260904-YTWSXK7WDK ($0.008394). Both containers are ZIPs of
per-UTC-day .dbn.zst members. Verify after any restore:
`certutil -hashfile data\\databento\\<file> SHA256`.

### Guard-(c) cloud-dump fixtures (git-ignored dir; zero-cost, regenerable via `python d49_nq_dump_cloud.py <tag>` — QuantConnect cloud minutes only, no Databento spend)

| tag | window | bytes | sha256 (prefix) |
|---|---|---|---|
| dump_nq-holiday.json | NQ 2024-11-15..12-05 | 60,801 | 63a5259481d92cc5 |
| dump_nq-roll.json | NQ 2024-12-16..12-30 (roll + Christmas) | 44,147 | 0fc6edd4b0c6453c |
| dump_gc-roll.json | GC 2020-01-15..01-31 (roll + MLK) | 45,279 | 5050e94550814408 |
| dump_gc-roll-b.json | GC 2020-02-01..02-14 (LEAN events) | 34,058 | 974d420286f7bddf |

## Known quotes (context, not commitments)

- Parent symbology `NQ.FUT,GC.FUT` 2010-06-07→2025-01-01: **$71.04**
  (over-pulls every listed month; superseded).
- Continuous `NQ.n.0,GC.n.0` 2010-06-07→2026-09-04: **$38.04** — half the
  cost of the parent pull for twenty months MORE data. Symbology switch
  was the cost decision; re-quotes shift daily as the end date rolls.
- ES/YM/RTY were deliberately NOT included in this purchase (design
  decision deferred, not an accident of the download).
- **Replication-venue quotes for Campaign 3 (2026-09-04, free
  `metadata.get_cost`, NOT purchased):** GLBX.MDP3, continuous,
  2010-06-07→2026-09-04 excl., ohlcv-1m + definition — SI.n.0
  $18.7710, PL.n.0 $14.8620, HG.n.0 $18.5787; all three jointly
  **$52.2116** (per-symbol sum and joint quote agree to the cent).
  Against inferred $86.6398 that leaves ≈$34.43 margin. Note the
  vendor's live-data boundary: end must precede 2026-09-04T17:41Z
  (first attempt at 2026-09-05 was rejected 422
  `dataset_unavailable_range`). Quotes drift daily as the end rolls;
  re-quote before any purchase decision, then rule 1 (portal
  re-verification + stated ceiling) governs.
- Guard (c) coverage (updated 2026-09-04, pre-study): the local QC bundle
  covers gc (comex) ordinary weekdays 2013-10 and es (cme) — reconciled:
  gc only. NQ and every ROLL window are now reconciled against LEAN
  itself via the zero-cost cloud dumps above (permanent tests
  QcCloudReconciliation). ES remains named-but-unreconciled; adding an
  es-dump window to d49's RUNS is the open extension point if ES ever
  enters scope (it is NOT part of C2-ONLT-v1's population).
