# TD-26
**Filed as:** #346

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-07-18.md

## Description
No production code path imports `tracker.parser` anymore. `main.py` only imports `from tracker.parser_fast import parse_midi_to_frames` (lines 97, 810). The old full parser's `parse_midi_to_frames` (`tracker/parser.py:10`) is referenced exclusively by three tests (`tests/test_midi_parser_integration.py:5`, `tests/test_integration.py:6`, `tests/test_pattern_integration.py:6`). It is not dead-dead (tests keep it importable) but it is dead to the shipping pipeline, so it silently drifts from `parser_fast.py` with nothing but those tests guarding parity. `_audit-common.md` and CLAUDE.md still describe it as "the older full parser," implying it may be a live alternative — it is not.

## Evidence
```
$ grep -rn "from tracker.parser import" --include='*.py' . | grep -v parser_fast | grep -v tests/
(no production hits)
$ grep -rn "from tracker.parser import" tests/
tests/test_midi_parser_integration.py:5
tests/test_integration.py:6
tests/test_pattern_integration.py:6
```

## Impact
Two parsers to maintain; the test-only one can rot or diverge without affecting any ROM, and its continued presence in docs misleads readers about the real front-end. No runtime risk. Blast radius: developer time / test suite only.

## Related
P-04/#112 (unused top-level import of the old parser — now resolved in tree). Dimension 1 "two parsers drifting" hot spot.

## Suggested Fix
Decide the module's fate explicitly. Either (a) delete `tracker/parser.py` and migrate its three tests to `parser_fast` (if `parser_fast` covers their assertions), or (b) keep it but add a module docstring stating it is a test-only reference implementation and update the CLAUDE.md / `_audit-common.md` descriptions to say it is not on any pipeline path.

## Completeness Checks
- [ ] **TESTS**: if deleted, the three importing tests are migrated to `parser_fast` without losing coverage
- [ ] **DOC**: CLAUDE.md / `_audit-common.md` parser description corrected