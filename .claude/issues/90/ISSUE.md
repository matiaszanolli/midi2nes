# ARR-07: Dead noise branch in midi_note_to_nes_pitch returns an unclamped MIDI note

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-06-29.md

## Description
The `else` branch of `midi_note_to_nes_pitch` returns `midi_note` directly (no clamp) for `channel="noise"`. `arrange_for_nes` never calls it with `"noise"` (noise period comes from `_allocate_noise`'s 0–15 clamp), so the branch is unreachable on the live path, but it is a latent unclamped value (0–127) if ever wired to the 4-bit noise period.

## Location
- `arranger/pipeline_integration.py:285-287`

## Evidence
`pipeline_integration.py:285-287`; noise frames built from `data["period"]` at `:243-246`, not this function.

## Impact
None today (dead). LOW — magic/dead code that contradicts the 4-bit noise range.

## Related
ARR-06.

## Suggested Fix
Remove the noise branch or clamp to 0–15; the noise period is the allocator's responsibility.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **TESTS**: A regression test pins this specific fix
