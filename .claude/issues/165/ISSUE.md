# NH-23: Dead hardware-adjacent code in the exporter: `NOISE_PERIODS` table and `is_midi_velocity`

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

## Description
(a) `NOISE_PERIODS` duplicates the NTSC noise period lookup from
`docs/APU_NOISE_REFERENCE.md` §3 but has zero references — the engine correctly writes the
4-bit *index*, never these CPU-cycle values. (b) The bytecode path computes
`is_midi_velocity = max_vol > 15` per channel and never uses it — a vestige of an
unimplemented 0-127->0-15 rescale. If a producer ever did hand this path raw MIDI
velocities, `vol_seq` bytes up to 127 would be emitted into `macro_vol_*` unscaled (the
engine masks `and #$0F`, so 127 -> 15, 100 -> 4 — wrong but in-range). The dead flag
suggests the normalization was intended and lost.

## Location
`exporter/exporter_ca65.py:40` (`NOISE_PERIODS`), `:953-959` (`is_midi_velocity` computed, never read).

## Evidence
`grep -rn NOISE_PERIODS` / `is_midi_velocity` — definitions only. Live volume producers all
clamp to 0-15 (`nes/emulator_core.py:94,100,144`), so both are inert today.

## Impact
None today; maintenance noise and a mild trap (same class as removed #108).

## Related
#108 (closed — `PULSE_DUTY_CYCLES`, same pattern), #34.

## Hardware ref
`docs/APU_NOISE_REFERENCE.md` §3 (the table it shadows) and §2 (`$400E` takes the 4-bit index `P`, not the period value).

## Suggested Fix
Delete both; if velocity-domain detection is wanted, implement the rescale it implies (or assert `max_vol <= 15`).

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
