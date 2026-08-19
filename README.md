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
python tests/test_thin_spine.py
```

## Not included
Charts, Research OS, Scout/Shadow, Direction Brain, broker, fat migration branch.
