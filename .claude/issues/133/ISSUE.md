# TD-05: Duplicate check_rom.py — root copy diverges from debug/check_rom.py

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-06-29.md

## Description
Two files named `check_rom.py` exist. The root one is a self-contained iNES header/vector dumper hardcoded to read `input.nes` in its `__main__`; `debug/check_rom.py` is the documented tool (CLAUDE.md references `python debug/check_rom.py`) that wraps `rom_diagnostics`. They are entirely different implementations sharing a name.

**Location:** `check_rom.py` (root) vs `debug/check_rom.py`

## Evidence
`diff check_rom.py debug/check_rom.py` shows no shared body; root `__main__` calls `check_rom('input.nes')` (hardcoded path, line 34).

## Impact
Ambiguity over which `check_rom` is authoritative; root copy is effectively dead (no caller, hardcoded input).

## Suggested Fix
Delete the root `check_rom.py`; keep the documented `debug/check_rom.py`.

## Related
TD-04, TD-02.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (or confirm no test imports the root file)
- [ ] **DOC**: CLAUDE.md continues to reference the surviving `debug/check_rom.py`
