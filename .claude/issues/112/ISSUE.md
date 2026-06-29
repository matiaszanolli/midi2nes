# P-04: Unused top-level import of the old full parser (tracker.parser.parse_midi_to_frames)

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-29.md

## Description
`from tracker.parser import parse_midi_to_frames` (`main.py:16`) is imported at module top but **never called** — every live path imports the fast parser locally as `parse_fast` (`main.py:41`, `:421`). The dangling import of the *older full parser* is a foot-gun: a future edit that calls the module-level `parse_midi_to_frames` (e.g. by deleting a local `parse_fast` import) would silently switch a path to the slower, behaviorally-different parser with no error.

## Evidence
`grep -n parse_midi_to_frames main.py` — line 16 import; all call sites (`main.py:42`, `:422`) use the locally-imported `parse_fast`.

## Impact
No current behavior change; latent parser-drift risk. Code-quality / LOW.

## Related
SKILL Dimension 2 (parser-selection drift); #33 / F-14 (third-parser drift in song-bank — same old-parser foot-gun, different file).

## Suggested Fix
Remove the unused top-level import so the only way to parse is the fast parser.

## Completeness Checks
- [ ] **SIBLING**: Same old-parser foot-gun in `nes/song_bank.py` (#33)
- [ ] **TESTS**: A regression test pins this specific fix
