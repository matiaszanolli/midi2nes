# NH-08: Dead/contradictory pulse volume expression in compile_channel_to_frames

**Severity:** MEDIUM · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #34

## Description
The pulse-branch `volume` is `min(15, velocity // 8) if velocity == 0 else max(1, int(15*pow(velocity/127,1.5)))`. The `velocity == 0` arm is unreachable (loop `continue`s on velocity 0 at emulator_core.py:29-30). The dead arm is a linear mapping contradicting the 1.5-power curve used elsewhere. Harmless (pulse uses the `control` byte from `get_envelope_control_byte`), but misleading dead code.

## Evidence
`if velocity == 0: continue` (emulator_core.py:29) then `... if velocity == 0 else ...` (line 59).

## Impact
None functionally; cosmetic/maintenance.

## Hardware ref
`docs/APU_PULSE_REFERENCE.md` §1; `docs/APU_ENVELOPE_REFERENCE.md` §4–§5.

## Related
NH-10.

## Suggested Fix
Drop the unreachable branch; keep the single power-curve expression.
