# ARR-2026-08-06-3: _assign_channels's BASS/triangle overflow recheck is unreachable from the live analysis pipeline

**Severity:** LOW · **Domain:** arranger · **Source:** docs/audits/AUDIT_ARRANGER_2026-08-06.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/410

## Description
The `if track.role == MusicalRole.BASS and not triangle_assigned:` recheck at
`role_analyzer.py:382` can never be true from the live pipeline, since `_determine_role`
always sets `preferred_channel == TRIANGLE` exactly when `role == BASS`, so any such
track is already handled by the earlier TRIANGLE branch. Only reachable via
hand-constructed test fixtures. Same reasoning applies to the ANY_PULSE/FLEXIBLE branch.

## Location
- `arranger/role_analyzer.py:382` (and `:370-378`)

## Impact
Maintenance/confusion only; no behavioral bug.

## Suggested Fix
Simplify `_assign_channels`'s overflow block to drop the redundant special-casing, or
comment that these branches only matter for non-`_determine_role`-derived input.
