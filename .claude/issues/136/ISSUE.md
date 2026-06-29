# TD-11: export_direct_frames (~723-line method) and run_full_pipeline (~260 lines) are monoliths

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-06-29.md

## Description
`export_direct_frames` is a single method spanning ~723 lines (lines 59-781) that emits pitch tables, per-channel playback routines (pulse/triangle/noise/DPCM), and the data tables inline — the file is 1154 lines total. `run_full_pipeline` is a ~260-line procedure threading parse → map/arrange → frames → patterns → export → DPCM-pack → prepare → compile → validate with inline branching. Both concentrate too much in one frame and are hard to test in isolation (cf. REG-05/#45).

**Location:** `exporter/exporter_ca65.py:59-781` (`export_direct_frames`); `main.py:386-645` (`run_full_pipeline`)

## Evidence
Next method after `export_direct_frames` is `_compress_macro` at line 782; `wc -l` main.py = 997, pipeline occupies 386-645; per-channel blocks are inline string lists.

## Impact
High change-cost and weak testability on the two hottest modules; correctness audits (NH-*, M-*) repeatedly point into these monoliths.

## Suggested Fix
Extract per-channel emitters (`_emit_pulse`, `_emit_triangle`, `_emit_noise`, `_emit_dpcm`) from `export_direct_frames`, and split `run_full_pipeline` into per-stage helpers returning artifacts, so stages can be unit-tested.

## Related
REG-05 (#45), TD-12.

## Completeness Checks
- [ ] **TESTS**: Extracted per-channel emitters become independently unit-testable (addresses REG-05)
- [ ] **CONTRACT**: Refactor preserves the exact emitted `music.asm` byte output
