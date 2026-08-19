# ATOM

Private market-intelligence and quantitative research platform.

This repository is the clean ATOM baseline. Components are admitted deliberately from the latest approved ATOM V9 architecture only; legacy V8 and superseded V9 implementations are not imported wholesale.

## Scope

- Market data and Level 2 inputs
- Fast State Bus
- Unified Quant
- Six-horizon forecast contracts
- Immutable pre-horizon forecast ledger and outcome resolver
- Certified Truth
- Scout and Shadow V2 research agents
- Research Platform

## Explicitly out of scope

- Brokerage integration
- Schwab account, balance, position, or order data
- Live order execution
- Global Lock
- Legacy execution-security architecture

## Security boundary

ATOM remains private. Provider and database credentials must be supplied through deployment secrets/environment variables and must never be committed to this repository.
