# TD-38: Closed #346/#347 fixes never reached master — dead tracker/parser.py and orphaned src/ NSF scaffolding still ship

- **Issue**: #458

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** Regression of #346 and #347 (both CLOSED "Fixed in 197e0e3" — but `git cherry master fix/issues-346-347` shows the commit is not on master, and no equivalent change landed via any other commit)

## Description
Commit `197e0e3` deletes `tracker/parser.py` (retargeting its three test importers to `tracker.parser_fast`) and removes the unreferenced NSF-player scaffolding in `src/`. It exists only on the unmerged branch `fix/issues-346-347`. On master, all of it is still present: `tests/test_midi_parser_integration.py:5`, `tests/test_integration.py:6`, and `tests/test_pattern_integration.py:6` still import `tracker.parser`, and `git ls-files src/` still lists the three `.s`/`.inc` files that `grep -rn "music_driver\|nsf_main_driver" --include='*.py'` confirms nothing reads.

Re-verified 2026-08-21: `tracker/parser.py` exists on master; all three test files still import it; `src/music_driver.s`, `src/nsf_main_driver.s`, `src/nes.inc` are still tracked; `git branch --contains 197e0e3` returns only `fix/issues-346-347`.

## Evidence
```
$ ls tracker/parser.py                      # exists
$ grep -n "from tracker.parser import" tests/test_midi_parser_integration.py tests/test_integration.py tests/test_pattern_integration.py
tests/test_integration.py:6:from tracker.parser import parse_midi_to_frames
tests/test_midi_parser_integration.py:5:from tracker.parser import parse_midi_to_frames
tests/test_pattern_integration.py:6:from tracker.parser import parse_midi_to_frames
$ git ls-files src/
src/music_driver.s
src/nes.inc
src/nsf_main_driver.s
$ git branch --contains 197e0e3
  fix/issues-346-347
```
Issue #347's closing comment says "Fixed in 197e0e3".

## Impact
The exact drift risk #346 was filed for (a production-dead parser kept alive by tests, silently diverging from the real front-end) persists, while the issue tracker says it is gone. Developer-confusion blast radius only; no runtime effect.

## Suggested Fix
Merge (or cherry-pick) `197e0e3` onto master. If merging is undesirable, reopen #346/#347 so the tracker state is honest.

## Related
PIPE-2026-08-21-2 (same stranded-branch pattern for #377, HIGH); #346/TD-26, #347/TD-27.

## Completeness Checks
- [ ] **TESTS**: A regression test (or the retargeted imports themselves) pins the fix so `tracker.parser` cannot silently reappear as a live test dependency
