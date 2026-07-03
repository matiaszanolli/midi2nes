# REG-12: RoleAnalyzer._assign_channels (channel-contention fallback + track-drop logic) has zero test coverage

- **Issue**: #230
- **Severity**: MEDIUM
- **Dimension**: Untested subsystems (Dim 1) + round-trip/e2e gaps (Dim 3)
- **Location**: `arranger/role_analyzer.py:306-386` (`_assign_channels`, called from `create_arrangement_plan` at `:302`, itself called from the live `--arranger` path at `arranger/pipeline_integration.py:178`)
- **Status**: NEW (related to, but not covered by, the now-closed #44/REG-04)
- **Source**: `docs/audits/AUDIT_REGRESSION_2026-07-03.md`

## Description
This is the method that decides which MIDI track lands on which NES channel when
multiple tracks compete for the same preferred channel — e.g. two melody-role tracks both wanting
Pulse1 (one falls back to Pulse2 with an advisory note, `:339-343`), two harmony tracks wanting Pulse2
(falls back to Pulse1, `:350-354`), `ANY_PULSE`/`FLEXIBLE` tracks filling whichever pulse channel is
free (`:356-364`), and the final "try any available channel" fallback that can silently move a track to
`plan.dropped_tracks` (`:366-386`) when NES has run out of channels.

`grep -rn "create_arrangement_plan\|_assign_channels\|dropped_tracks\|ArrangementPlan" tests/*.py`
returns zero matches — no test calls `create_arrangement_plan()` directly, inspects
`plan.dropped_tracks`, or constructs a MIDI input with enough competing tracks (e.g. 3+ melody-role
tracks) to exercise the fallback branches. The existing arranger tests (`test_arranger.py`,
`test_arranger_frame_contract.py`) all use 1-2 track inputs — never enough to force channel contention.
`test_voice_allocator.py` tests a different, downstream concern (DPCM/noise routing inside
`VoiceAllocator`), not this method.

## Evidence
```
$ grep -rln "create_arrangement_plan\|_assign_channels\|dropped_tracks\|ArrangementPlan" tests/*.py
(no output)
$ grep -c "def test_" tests/test_arranger.py tests/test_arranger_frame_contract.py
tests/test_arranger.py:10
tests/test_arranger_frame_contract.py:2
```
`role_analyzer.py` coverage is 62% with the largest missed block at `:319-326,340-365,369-384` —
the fallback/drop branches of `_assign_channels` plus the unrelated (and legitimately untested,
print-only) `print_analysis`.

## Impact
A regression in the channel-contention logic (e.g. always dropping the second melody track
instead of falling back to Pulse2, or dropping a bass track that should have gone to Triangle) would
ship silently — the arranger would produce a playable ROM that is musically wrong (a voice missing)
with no test catching it. This is the arranger's single largest untested decision point.

## Related
#44 (REG-04, closed) — fixed role-tagging/arpeggiation/contract but not this method; #88
(ARR-05, open) — `get_role_priority()` dead code inconsistent with "the live drop order", which is
this exact method's fallback order; a test here would also pin down what "the live drop order" is for
that issue.

## Suggested Fix
Add `tests/test_arranger.py` (or a new `test_role_analyzer.py`) cases that build 3-4
competing tracks (e.g. two high-pitch melody-role tracks, two low-pitch bass-role tracks, one drum
track) through `RoleAnalyzer.create_arrangement_plan()` directly, and assert: (1) the second melody
track lands in `plan.pulse2_tracks` with the expected advisory note, (2) a track that truly can't fit
anywhere lands in `plan.dropped_tracks` with a note, not silently vanishes.

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
