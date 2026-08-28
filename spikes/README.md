# V2 external-memory architecture spike

Run an isolated measurement (one row count per process so `ru_maxrss` is not
contaminated by an earlier run):

```bash
python spikes/v2_external_memory_benchmark.py 65535
```

The harness is intentionally not production code. It exercises the proposed
4,096-row page-to-disk boundary, canonical byte preservation, indexed ordered
pass, accounting, and workspace cleanup. It does not claim V2 state parity;
that gate belongs to the implementation phases in
[`docs/v2-external-memory-spike.md`](../docs/v2-external-memory-spike.md).
