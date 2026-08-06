# ARR-2026-08-06-2: Last-resort triangle fallback lets a lower-priority HARMONY/DECORATIVE track survive while a higher-priority MELODY track is dropped

**Severity:** MEDIUM · **Domain:** arranger · **Source:** docs/audits/AUDIT_ARRANGER_2026-08-06.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/409

## Description
`_assign_channels`'s last-resort triangle fallback excludes only `MusicalRole.MELODY`,
not "everything except BASS" as `tests/test_role_analyzer.py`'s own docstring claims.
Since the exclusion is role-based rather than priority-based, a higher-priority MELODY
track can be dropped while a lower-priority HARMONY/DECORATIVE track processed later
claims the now-idle triangle — inverting the documented "highest priority survives" rule.

## Location
- `arranger/role_analyzer.py:380-397` (`_assign_channels` overflow block, `:394` guard)

## Impact
On MIDI with 3+ melodic/harmonic voices and no distinct bass line, the arranger can
silently drop a musically more important voice in favor of a less important one.

## Suggested Fix
Tighten the guard to `track.role == MusicalRole.BASS` only, or make the fallback
priority-aware if HARMONY/DECORATIVE-on-triangle is intentional.
