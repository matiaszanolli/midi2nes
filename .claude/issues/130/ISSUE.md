# TD-02: Two parallel ROM-validators — root validate_rom.py vs main.py:validate_rom

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-06-29.md

## Description
The root `validate_rom.py` is a standalone iNES header/reset-vector/zero-fill checker; `main.py:validate_rom` (line 115) is the pipeline's post-build gate (delegating to `debug.rom_diagnostics`). They validate overlapping properties (reset vectors, header) with separate, divergent logic. The root script is referenced only by tests (`tests/test_validate_rom_script.py`, `tests/test_main_pipeline.py`), not by any pipeline path.

**Location:** `validate_rom.py:6` (root) and `main.py:115`

## Evidence
`grep` for importers of `validate_rom` finds only test files; `main.py:115`'s gate calls `ROMDiagnostics(...).diagnose_rom`, a different code path entirely.

## Impact
A validation rule fixed in one is not reflected in the other; the root script's tests give false confidence that "ROM validation" is centrally covered.

## Suggested Fix
Either fold the root checker's checks into `debug.rom_diagnostics` and make `validate_rom.py` a thin CLI over it, or document it as a deliberately minimal independent cross-check.

## Related
F-02 (ROM-validation gate only blocks on ERROR), TD-06.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (other validators / diagnostics paths)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
