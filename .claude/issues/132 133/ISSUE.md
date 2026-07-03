# TD-04: Five tracked root scratch .py files with zero importers

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-06-29.md

## Description
Five `.py` files are checked into git at the repo root and have **zero** importers across the codebase (and zero references from `tests/`): `implementation_examples.py`, `show_greeting.py`, `batch_test.py`, `nes_devflow.py`, `generate_test_midi.py`. `show_greeting.py` is an unrelated stray (`print(f"Hey {name}")`). `implementation_examples.py` is a 16 KB obsolete parser prototype superseded by `tracker/parser_fast.py`.

**Location:** `implementation_examples.py`, `show_greeting.py`, `batch_test.py`, `nes_devflow.py`, `generate_test_midi.py` (all repo root).

(The dead `ThreadedPatternDetector` class at `tracker/pattern_detector_parallel.py:314`, originally bundled in this finding, is already tracked as #105 / P-08 and is excluded here.)

## Evidence
`git ls-files` lists all five; `grep -rln "import <name>"` returns 0 non-self hits for each.

## Impact
Confuses navigation and audits; `implementation_examples.py` looks like a real parser. No runtime impact.

## Suggested Fix
Delete the five root scripts (move any still-wanted helper into `debug/` or `tools/`).

## Related
TD-05 (duplicate `check_rom.py`), TD-03, #105 (dead `ThreadedPatternDetector`), TD-12 (the dead parser prototype).

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (or confirm no test imports the deleted files)
- [ ] **DOC**: If behavior contradicted a `docs/*.md` / CLAUDE.md, the doc was corrected


---

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

