# REG-20
**Filed as:** #339

**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-07-18.md

## Description
Both tests assert only that the substring `"PATTERNS"` appears in the export (`tests/test_exporter_integration.py:121`, `tests/test_famistudio_export.py:61`), which would still pass if every note/volume value in the pattern rows were wrong. Each is partially rescued by an adjacent single note-value check (`assertIn("C-4 15", ...)`), and the path now has a dedicated golden-bytes class (`TestFamiStudioGoldenBytes`), so the residual risk is small — but the two structural checks themselves remain the weak-assertion shape this dimension exists to eliminate.

## Evidence
`grep 'assertIn("PATTERNS"' tests/` → the two lines above; both sit in general-structure test methods (`test_generate_famistudio_txt`, `test_famistudio_export_with_compression`).

## Impact
LOW — a values-wrong/structure-right regression in these two methods would pass, but the golden-bytes class covers the same emit path.

## Related
REG-05 (#45), REG-14 (#232).

## Suggested Fix
Either delete the redundant `assertIn("PATTERNS")` assertions (the golden-bytes class already pins the pattern rows), or extend each to assert a full expected pattern-row line (note + volume + frame) rather than the section header alone.

## Completeness Checks
- [ ] **TESTS**: each weak check is either removed or upgraded to a full pattern-row assertion