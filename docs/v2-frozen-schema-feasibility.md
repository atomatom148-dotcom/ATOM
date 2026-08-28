# ATOM V9 External-Memory Phase 1A — frozen-schema feasibility gate

**Verdict: `FEASIBLE_WITH_EXTERNAL_BUILD`.** This is an offline laboratory
finding, not approval to publish, migrate, deploy, or implement external
V2A–V2D adapters. Production V2 and every frozen formula, codec, hash,
operation order, eligibility rule, and live consumer remain unchanged.

## Critical result

The final serialized `V2EvidenceState` contains **no evidence-row identity,
observation, target, or support-identity tuple**. Its payload is 8,171–8,172
bytes from 1,000 through 200,000 admitted synthetic rows. A restored live state
is likewise bounded. Legacy construction is intrinsically O(n), reaching
1,756,434,432 bytes peak RSS at 200,000 rows in this run. Therefore the frozen
schema does not block external construction, but the current constructor cannot
be called an end-to-end bounded-memory build.

A one-byte size transition at 10,000 is caused by decimal aggregate counts; it
is O(log n), not retained evidence. Strictly, unbounded integer text is not
mathematical O(1), but under the frozen database/cardinality domain these scalar
counts are classified as O(1) as requested.

## Complete object graph and field classification

### V2A dataset

`V2ADataset` is the sole frozen result that retains row-shaped history.

* **O(evidence rows):** `skeleton` (`TargetOrigin`, including identity, record
  id, times, and target), every `FamilySubset.observations`
  (`FamilyObservation`, including target identity, record id, lineage, value,
  and times), each `PairSupport.target_identities`, and
  `complete_case_target_identities`.
* **O(families × horizons):** `family_lineage`, `directional_subsets`,
  `q3_subset`, `pair_support` container (the contained identity tuples are
  O(rows)), and `exclusions` (bounded reason vocabulary).
* **O(1):** schema/method/symbol/cutoff/training/target lineage/horizon scalar
  fields, `raw_resolved_count`, and `dataset_hash`.

The builder also temporarily materializes selected-target dictionaries,
observation dictionaries/lists, identity sets, and sorted row collections. The
production PostgreSQL builder first accumulates all keyset pages into tuples,
then creates per-horizon target/observation lists and six V2A datasets. Paging
therefore removes the query ceiling but does not bound legacy construction RAM.

### V2B calibration

The serialized `V2BCalibration` output is **O(families × horizons)**:
`input_manifest`, `directional`, and `q3_magnitude`; `gamma`, version, and state
are O(1). Every calibration record consists only of lineage, scalar counts,
scalar estimates/diagnostics, a fixed 2×2 matrix, status, and bounded reasons.
It contains no observations or identities.

Construction is O(evidence rows): `_Series.x`, `_Series.y`, scores, centered
values/autocorrelations, residuals, targets lookup, and intermediate vectors.
The frozen `effective_n` implementation can also take O(n²) time on a
non-degenerate series because it evaluates every lag. The measurement fixture
uses a degenerate constant residual to exercise its frozen early return and
keep this resource gate practical; it does not claim representative wall time.

### V2C covariance

The `V2CCovariance` result is **O(families² × horizons)** (reported in the
requested O(families × horizons) bounded category because the family universe
is frozen): fixed-size quant/formula/lineage tuples; pairwise, empirical,
projected, and stabilized matrices; duplicate groups; scalar diagnostics; and
bounded reasons. It retains no support identities.

Construction is O(evidence rows): target and residual dictionaries,
pair-support joins, complete-case rows, and centered rows. These temporaries are
not forwarded into V2D.

### V2D, canonical codec, store, and live consumers

`V2EvidenceState` contains O(1) metadata and status/reasons plus
O(families × horizons) `component_hash_tuple`, six `HorizonEvidenceState`
records, calibration summaries, lineage, and covariance matrices. V2D forwards
only the **boolean** pair-support matrix, not `PairSupport.target_identities`.
`exclusion_count_tuple` is bounded by the frozen reason vocabulary.

The canonical serializer recursively expands only this bounded final object.
The strict deserializer reconstructs and validates the same graph. The state
store serializes, decodes, reserializes, checks relational columns, and returns
one state. `ImmutableV2StateProvider.restore` holds that one returned state;
`capture` returns the same immutable object. V1/V3/V4 consumers use its state
identity, lineage, six horizon summaries, calibrations, and matrices; none
rehydrates evidence history.

The build receipt is bounded: scalar row/page counts, first/last source
identity, per-horizon/per-family counts and Effective N, manifest hash, and
receipt hash. It has no list of source identities. Note that the existing
production builder's temporary `source_identities` list is O(n), although the
receipt retains only its endpoints.

## Measurements

Environment: Linux x86-64, CPython 3.14.4, local overlay filesystem. Each cell
ran in a new interpreter. Values are absolute process peak RSS; the report also
records each fresh process baseline (31.37–31.45 MB), elapsed time, hashes,
component hashes, and exact object counts. No prior cell's `ru_maxrss` can leak
into the next cell.

| Rows | state bytes | legacy construction peak | serialization peak | deserialization peak | live restore peak |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 8,171 | 41,082,880 | 31,371,264 | 31,371,264 | 31,371,264 |
| 10,000 | 8,172 | 118,620,160 | 31,371,264 | 31,371,264 | 31,371,264 |
| 65,535 | 8,172 | 592,826,368 | 31,371,264 | 31,371,264 | 31,371,264 |
| 65,536 | 8,172 | 592,867,328 | 31,391,744 | 31,371,264 | 31,371,264 |
| 65,537 | 8,172 | 592,891,904 | 31,375,360 | 31,453,184 | 31,371,264 |
| 200,000 | 8,172 | 1,756,434,432 | 31,371,264 | 31,391,744 | 31,440,896 |

Serialization, deserialization, and restore peaks are indistinguishable from
interpreter baseline at this resolution and do not trend with evidence count.
The checked-in raw JSON report is the authoritative machine-readable record.
The cardinalities 65,535/65,536/65,537 are exact, not generated page estimates.

## Golden and parity strategy

The checked-in golden fixture is generated solely through the frozen legacy
V2A→V2B→V2C→V2D functions. It contains canonical state bytes, SHA-256 of those
bytes, state hash, state ID, evidence manifest hash, V2A dataset hash, all
component hashes, canonical receipt bytes, receipt-byte SHA-256, and receipt
hash. Resource telemetry is zeroed because it is deliberately excluded from
receipt identity. Tests regenerate the fixture, demand exact JSON/byte parity,
round-trip through the frozen codec, and prove a source-cardinality/terminal
identity change changes dataset, manifest, state, and receipt identities.

The harness is intentionally the minimum future parity boundary: future
external work may produce candidate state and receipt bytes, then compare them
directly with this fixture and with fresh legacy results. It contains no
external adapter, alternate mathematics, schema, serializer, state-store write,
or production seam.

## Decision and smallest next phase

Proceed only to an **offline external V2A construction prototype**, initially
for one horizon and one directional family, with byte comparison against the
legacy dataset/component/state hashes and golden canonical state/receipt bytes.
It must preserve iteration and floating-point operation order and measure its
own staging disk separately from RAM. Do not call it end-to-end bounded until
external V2B/V2C calculations and candidate validation also stay within a fixed
RAM budget.

No freeze exception is required to pursue byte-identical external construction:
the final frozen state and live restore are bounded. A freeze exception **would**
be required to replace V2A row tuples with references, change the canonical
state/receipt schema or codec, or alter formulas/operation order. None is
proposed here.
