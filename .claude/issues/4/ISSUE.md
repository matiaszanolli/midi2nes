# F-01: export_tables_with_patterns ignores its references argument and uses patterns only as a boolean switch

**Severity:** HIGH · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #4

## Description
The SKILL flags a "references-format gap": `run_full_pipeline` converts references to `{frame_str:(pattern_id,offset)}` (`main.py:352-361`) while `run_export` passes the detector's raw `{pattern_id:[positions]}` straight through (`main.py:90`). Re-reading the consumer shows the gap is moot in a worse way: `export_tables_with_patterns` never reads `references` at all, and reads `patterns` only at line 652 (`if not patterns: return self.export_direct_frames(...)`). All emitted bytes are re-derived from `frames`. The entire `ca65_references` block is dead computation.

## Evidence
`references` appears only in the signature and docstring; never read in the function body. `patterns` is read only at the gate (652). All emitted bytes derive from `frames`.

## Impact
(a) Pattern compression has no effect on output bytes. (b) Default vs step-by-step paths emit different ROMs because step-by-step export hits export_direct_frames while default hits the macro path. (c) Future references-format fixes are wasted until the exporter consumes references.

## Related
F-06, F-07, F-08

## Suggested Fix
Either make export_tables_with_patterns consume references/patterns to emit compressed sequence data, or delete the references parameter and dead ca65_references build and document "compression" as analysis-only. Unify default and step-by-step export.

**Location:** `exporter/exporter_ca65.py:646-895`; producers `main.py:352-370` and `main.py:88-102`
