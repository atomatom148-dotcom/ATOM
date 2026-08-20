# ATOM V9 Thin

Quant research pipeline only.

```
COIN snapshot → Unified Quant → exact-six ledger → truthful status
```

## Laws
See FREEZE.md.

## Layout
```
FREEZE.md
PHASES.md
quant/
  __init__.py
  models.py
  snapshot.py
  unified_quant.py
  ledger.py
status/
  api.py
tests/
  test_thin_spine.py
README.md
```

## Run tests
```
python tests/test_phase_a_contracts.py
```

## Live Q1-Q3 runtime

Install `requirements.txt`, apply `migrations/001_live_q1_q2_evidence.sql`, and
set `DATABASE_URL`, `ALPACA_API_KEY`, and `ALPACA_SECRET_KEY`. Then start the single-process
standard-library HTTPS polling runtime (Render supplies `PORT`):

```
python -m quant.web --host 0.0.0.0 --port "$PORT"
```

## Not included
Charts, Research OS, Scout/Shadow, Direction Brain, broker, fat migration branch.
