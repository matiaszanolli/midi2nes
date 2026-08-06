# ARR-NEW-7: enhanced_track_mapper is an unused, re-exported public helper (dead API surface)

**URL:** https://github.com/matiaszanolli/midi2nes/issues/331
**Labels:** bug, low, arranger

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-18.md

## Description
`enhanced_track_mapper` (converts arranger frames back to an event-list format, `arranger/pipeline_integration.py:332-357`) has no call site anywhere in the repo — the live pipeline uses `arrange_for_nes` directly (`main.py:820`). It is nonetheless in `__all__` (`arranger/__init__.py:61,95`), so a maintainer may assume it is a supported/used entry point.

## Evidence
`grep -rn enhanced_track_mapper --include='*.py' .` returns only the definition and the `__init__` re-export; no callers.

## Impact
Maintenance noise / misleading API. No runtime effect.

## Related
Mirrors the #88/ARR-05 dead-code cleanup pattern.

## Suggested Fix
Remove it (and its `__all__`/import entries), or add a test/caller if it is intended as public API.

## Completeness Checks
- [ ] **SIBLING**: other `arranger/__init__.py` `__all__` entries checked for the same unused-export status
- [ ] **TESTS**: if kept as public API, a test exercises it; if removed, no import breaks

