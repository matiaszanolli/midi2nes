# TD-23: Velocity-to-4-bit-volume power curve copy-pasted across 4 production sites

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-07-18.md
**Filed as:** #319

## Description
`max(1, int(15 * math.pow(velocity / 127.0, 1.5)))` hand-written at 4 sites in nes/emulator_core.py and nes/envelope_processor.py; no shared helper. Arranger uses a different linear formula. arranger/voice_allocator.py:453 (noise) has no floor at all.

## Location
`nes/emulator_core.py:113,119,168`, `nes/envelope_processor.py:119`; `arranger/voice_allocator.py:430,438,453`

## Suggested Fix
Add a shared velocity_to_volume() helper; decide deliberately whether arranger adopts power curve or documents the divergence.

## Related
First reported AUDIT_TECH-DEBT_2026-07-06.md (never filed), #89 (ARR-06)
