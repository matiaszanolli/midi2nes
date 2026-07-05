ARR-NEW-3: Closed hi-hat's curated noise_period=0 is floored to 1 by the rest-sentinel floor

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-05.md

## Description
`GM_DRUM_MAP[42]` (Closed Hi-Hat) curates `noise_period = 0` (top noise frequency); the code comment in `_allocate_noise` explicitly calls out "closed hi-hat (period 0)". But the noise-frame conversion floors the period to 1 — `period = max(1, data['period'] & 0x0F)` — because period 0 is the bytecode rest sentinel. So the one drum that *wants* period 0 can never emit it; its timbre shifts to period 1.

## Location
`arranger/pipeline_integration.py:274-282` (noise conversion) vs. `arranger/gm_instruments.py` (`GM_DRUM_MAP` closed hi-hat `noise_period = 0`).

## Evidence
`get_drum_mapping(42).noise_period == 0` (verified); conversion at `pipeline_integration.py:275` is `period = max(1, data['period'] & 0x0F)`. Currently unobservable because ARR-NEW-1 drops the noise channel entirely; becomes live once ARR-NEW-1 is fixed.

## Impact
A single drum's timbre is subtly wrong (period 1 instead of 0). LOW — cosmetic timbral shift on one instrument, and it is an inherent tension with the rest sentinel, not a crash or dropped note.

## Suggested Fix
Decide explicitly how period-0 drums should render (accept the period-1 shift and note it in `GM_DRUM_MAP`, or remap sentinel handling so period 0 is representable). At minimum, align the `GM_DRUM_MAP` comment with the floored reality.

## Related
ARR-NEW-1 (masks this today); #84 (the rest-sentinel floor rationale).

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (4-bit noise period)
- [ ] **DOC**: The `GM_DRUM_MAP` comment is aligned with the floored reality
- [ ] **TESTS**: Coverage pins the chosen period-0 rendering behavior
