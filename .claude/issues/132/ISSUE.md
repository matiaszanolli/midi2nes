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
