# ARR-08: arp_speed is not validated — arp_speed=0 raises ZeroDivisionError in the allocator

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-06-29.md

## Description
`_allocate_pulse` advances the arp index via `self.frame_count % self.arp_speed`. `arp_speed` is passed through `arrange_for_nes`/`allocate_with_arpeggiation` with no guard; a value of 0 raises `ZeroDivisionError` mid-arrangement. The live CLI hardcodes `arp_speed=3` (`main.py:433`), so this is unreachable from the CLI but exposed to any programmatic caller of the public `arrange_for_nes`.

## Location
- `arranger/voice_allocator.py:201`
- call site `main.py:431-435` (hardcoded 3)

## Evidence
`voice_allocator.py:201` `if self.frame_count % self.arp_speed == 0:` with no `arp_speed >= 1` validation in `__init__`, `allocate_with_arpeggiation`, or `arrange_for_nes`.

## Impact
Crash on a degenerate parameter from an API caller; not reachable via the CLI. LOW (missing input validation on a recoverable path).

## Related
SKILL Dimension 5 note on ZeroDivision.

## Suggested Fix
Clamp/validate `arp_speed = max(1, arp_speed)` at the `VoiceAllocator` boundary.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
