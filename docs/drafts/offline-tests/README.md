# Offline tests — decision record and pre-registrations (DRAFT, zero authority)

**Draft status:** prepared by Claude at Owner request under Amendment 1B delegated drafting (`AGENTS.md`, "Freeze-author continuity and delegated drafting"); zero controlling authority. Nothing in this folder is a freeze, amendment, phase, job card, or receipt, and nothing here changes `AGENTS.md`, `FREEZE.md`, `SIMULATION_FREEZE.md`, `PHASES.md`, the active-phase pointer, or any merged freeze.
**Change type:** documentation only. The Python files are the frozen runners for two offline studies that execute on the Owner's desktop with the Owner's data; no ATOM module imports them, `pytest` does not collect them, and Sonar does not scan `docs/`.
**Author of record:** the Owner, on merge. Claude is the draft preparer only.

## Contents

| File | Role |
| --- | --- |
| `atom-decision-record-2026-09-18.md` | The Owner's operating decision of 2026-09-18 ("Go"): direction research closed, two pre-registered offline tests decide the program, kill criteria fixed before results, cost actions, no new law. |
| `prereg-A-realized-vs-implied-vol-v1.md` | Test A — realized vs implied volatility on the Cboe EOD file; single look. |
| `prereg-B-morning-continuation-history-v1.md` | Test B — news-day morning continuation on unseen COIN history 2021-04 → 2024-08; single look. |
| `alpaca_history_pull.py` | Test B data pull (Alpaca SIP, keys from environment only, never printed). |
| `history_study.py` | Test B runner; writes `receipt-B.json` and refuses to run twice. |
| `cboe_iv_study.py` | Test A runner; writes `receipt-A.json` and refuses to run twice; `--selftest` runs a synthetic pipeline. |
| `hashes_2026-09-18.txt` | SHA-256 of the two pre-registrations and the three runners as prepared on 2026-09-18. These are the hashes that "frozen at Owner approval" refers to. Verify with `sha256sum -c hashes_2026-09-18.txt` in this folder. |

## What these studies are and are not

- Both run outside ATOM law, read nothing from ATOM's ledgers, and write nothing to any ATOM database, service, or credential.
- The protected single looks stay sealed: no E-2 `|μ|/(κσ)` statistic, no V-1B look on the ATOM ledger, no SIM return aggregates. The Sep 10 momentum pre-registration remains closed without its look; its validation and confirmation partitions (2026-03-02 → 2026-08-19) are released only to Test A's daily-close series, as `prereg-B-morning-continuation-history-v1.md` §5 states.
- Informal exploratory findings that motivated Test B are disclosed inside `prereg-B-morning-continuation-history-v1.md` §1 and are labeled in-sample; they promote nothing.
- Neither test authorizes E-2, E-3, E-4, SIM-6, a new family, a new service, role, credential, or source, broker or account action, or live trading. If either test passes, any continuation is a separate Owner decision on its own documentation-first path.

## Owner actions recorded in the decision record

1. Approve both pre-registration texts in writing; the code hashes at approval are the ones in `hashes_2026-09-18.txt`.
2. Re-order the Cboe DataShop file and place it in `research/cboe/` on the desktop; run `cboe_iv_study.py` once.
3. Put the Alpaca key in the desktop environment; run `alpaca_history_pull.py`, then `history_study.py` once.
4. Cost actions in the Render and Supabase dashboards as listed in the decision record.

Receipts (`receipt-A.json`, `receipt-B.json`) are produced on the Owner's desktop. Whether they are ever added to this repository is a later Owner decision; this folder does not pre-authorize it.
