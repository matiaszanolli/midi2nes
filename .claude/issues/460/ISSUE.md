# TD-40: velocity/volume dual-key event read copy-pasted at 15 sites across 6 modules — with inconsistent precedence and defaults

- **Issue**: #460

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** NEW (the idiom predates this cycle, but `ffccf51` added the 15th site and a comment claiming a uniformity that does not exist)

## Description
Parsed events carry `volume` (from `tracker/parser_fast.py`) while synthetic/legacy events carry `velocity`, so every consumer defensively reads both. The fallback is hand-rolled at each site and has already diverged on both axes: key precedence (velocity-first in `nes/`/`dpcm_sampler/`/`arranger/`, volume-first in `tracker/`) and missing-key default (0 at 13 sites, 100 at 2). The comment added in `ffccf51` (`dpcm_sampler/enhanced_drum_mapper.py:318-322`) says it matches "the defensive dual-key idiom used everywhere else in this codebase (e.g. tracker/track_mapper.py…)" — but it wrote velocity-first while `track_mapper` is volume-first, demonstrating the drift is already invisible to authors.

## Evidence
```
$ grep -rn "get('velocity'.*get('volume'\|get('volume'.*get('velocity'" --include='*.py' . | grep -v tests/
tracker/track_mapper.py:16:        vel = e.get('volume', e.get('velocity', 0))
tracker/track_mapper.py:29:        vel = e.get('volume', e.get('velocity', 0))
tracker/track_mapper.py:302:            notes = [e['note'] for e in events if e.get('volume', e.get('velocity', 0)) > 0]
tracker/pattern_detector.py:615:        sequence = [(e['note'], e.get('volume', e.get('velocity', 100))) for e in events]
arranger/pipeline_integration.py:196:                velocity = event.get('velocity', event.get('volume', 100))
nes/emulator_core.py:32,37,40,72,86,94,157,211,229  (9 sites, velocity-first, default 0)
dpcm_sampler/enhanced_drum_mapper.py:324:                velocity = e.get('velocity', e.get('volume', 0))
```
15 sites total across 6 modules — confirmed unchanged since the report was written.

## Impact
An event carrying both keys with different values, or missing both, is interpreted differently per module (note kept vs dropped; loudness 0 vs 100). Today's producers appear to emit exactly one of the keys, so this is drift *risk*, not a live bug — hence LOW.

## Suggested Fix
Add one helper (e.g. `core/events.py: event_velocity(e, default=0)`) with a single documented precedence, and migrate all 15 sites; the 2 default-100 sites should justify or drop their divergent default at migration time.

## Related
`ffccf51` (site 15); DPCM-2026-08-21-1 / PIPE-2026-08-21-1 (the same commit's CRITICAL functional bug — separate root cause, reported by siblings).

## Completeness Checks
- [ ] **CONTRACT**: The new helper's precedence is documented once and every one of the 15 call sites migrates to it (no lingering hand-rolled fallback)
- [ ] **SIBLING**: Same pattern checked in related files — all 6 modules (`nes/`, `tracker/`, `arranger/`, `dpcm_sampler/`) covered, not just the newest site
- [ ] **TESTS**: A regression test pins the chosen precedence/default so a future edit can't silently re-diverge
