# ARR-05: get_role_priority() is dead and inconsistent with the live drop order

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-06-29.md

## Description
`get_role_priority()` defines a role ordering (BASS=1 best … SFX=6) but is only re-exported in `arranger/__init__.py` and never called. The actual channel-drop order in `_assign_channels` sorts `plan.tracks` by the integer `TrackAnalysis.priority` (set in `_determine_role`), which is a *different* scale (higher = keep). The two are inconsistent and the named-role table is dead.

## Location
- `arranger/gm_instruments.py:1300-1309`
- live order at `arranger/role_analyzer.py:299` + `:306-391`

## Evidence
`grep get_role_priority` -> definition + `__init__.py` export only; no allocation call. `role_analyzer.py:299` sorts by `t.priority` (reverse), not by role.

## Impact
Maintenance/readability only — a reader may assume role priority governs drops. No runtime effect. LOW (dead code / inconsistent helper).

## Related
ARR-03.

## Suggested Fix
Either remove `get_role_priority()` or make `_assign_channels` use it as a tie-break; document that `TrackAnalysis.priority` is the live drop key.

## Completeness Checks
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
