# ARR-06: Hand-rolled midi_note_to_nes_pitch diverges from the canonical nes/pitch_table.py used elsewhere

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-06-29.md

## Description
`arrange_for_nes` pre-bakes a `pitch` per pulse/triangle frame using a float formula (`int(CPU_CLOCK/(16*f)-1)` for pulse, `/32` for triangle, clamped 0–2047). The macro export path recomputes its own `base_timer = midi_note_to_timer_value(note, channel)` and stores only `pitch_offset = clamp(pitch - base_timer, -128, 127)`. If the two formulas disagree by more than ±127 the offset saturates; for in-range notes they agree closely, so the pre-baked `pitch` is largely redundant on the macro path. Two pitch sources for the same value is a divergence risk; the clamp is correct vs `docs/APU_PITCH_TABLE_REFERENCE.md` (11-bit), so this is hardening, not a live wrong-pitch bug.

## Location
- `arranger/pipeline_integration.py:258-290`
- canonical `nes/pitch_table.py` / exporter `midi_note_to_timer_value` (`exporter/exporter_ca65.py:990, 1005`)

## Evidence
`pipeline_integration.py:281` `period = int(CPU_CLOCK / (16 * frequency) - 1)` vs `exporter_ca65.py:990` `base_timer = self.midi_note_to_timer_value(note, channel)`.

## Impact
Potential small pitch drift / dead pre-bake; no observed out-of-range emission. LOW.

## Related
ARR-07.

## Suggested Fix
Have the arranger reuse `nes/pitch_table.py` (or `midi_note_to_timer_value`) so there is a single authoritative pitch source.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
