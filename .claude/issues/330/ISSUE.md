# ARR-NEW-6: Drum-track toms/agogos/cuicas always render as noise
**Filed as:** #330

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-18.md

## Description
A drum track claims only NOISE + DPCM (`role_analyzer.py`). `_route_note` (`arranger/voice_allocator.py:191-218`) returns `NESChannel.NOISE` for *any* non-sample drum note as soon as NOISE is in the track's channels (`:212-213`), which fires *before* the "honor the mapped channel" branch at `:216`. So `GM_DRUM_MAP` notes whose curated channel is TRIANGLE (toms 41/43/45/47/48/50) or PULSE2 (agogos 67/68, cuicas 78/79, mute/open triangle 80/81) are funneled to noise instead — and since those mappings carry no `noise_period`, they fall back to the generic period `5`. Pitched toms lose their pitch and sound like a generic noise hit.

## Evidence
`_route_note`: `if NESChannel.NOISE in channels: return NESChannel.NOISE` (`:212`) precedes `if mapping.channel in channels: return mapping.channel` (`:216`). Toms have `noise_period=None` → `_allocate_noise` fallback `5`.

## Impact
Musical-quality degradation on drum tracks that use melodic toms or the agogo/cuica/triangle percussion; the intended pitched-percussion timbre is lost. No crash, workaround is to author those on a separate pitched track. Structurally constrained (triangle is reserved for bass), but the current routing ignores the mapping table it otherwise consults.

## Related
#87/ARR-04 (routing driven by `GM_DRUM_MAP`).

## Suggested Fix
Before defaulting to NOISE, honor `mapping.channel` when that channel is in the track's assignment; only fall through to NOISE when the mapped channel isn't owned. Note the structural constraint: triangle is reserved for bass, so honoring a TRIANGLE mapping mid-song needs a collision policy.

## Completeness Checks
- [ ] **CHANNEL**: triangle-routed toms respect that triangle has no volume/duty and use the triangle pitch table
- [ ] **SIBLING**: same precedence bug checked for DPCM-vs-mapped-channel ordering
- [ ] **TESTS**: a regression test routes a tom on a NOISE+TRIANGLE drum track and asserts it does not collapse to noise period 5