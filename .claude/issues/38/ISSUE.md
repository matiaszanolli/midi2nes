# NH-10: Additive pitch modification in the dead duplicate core re-opens the 11-bit clamp

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #38

## Description
The duplicate `NESEmulatorCore.compile_channel_to_frames` in `nes/envelope_processor.py` adds vibrato (`modified_pitch += pitch_mod`) after the pitch was clamped, with no re-clamp; the exporter masks rather than clamps, so out-of-range wraps silently. Would be HIGH on a live path, but this core is dead — `main.py` imports `nes/emulator_core.py`. Filed LOW as a latent trap + duplication.

## Evidence
`main.py:18` imports `nes.emulator_core` (instantiated at 50, 287). Vibrato path only in envelope_processor.py: `class NESEmulatorCore` (162), `modified_pitch += pitch_mod` (206), emitted 218/231 with no re-clamp.

## Impact
None today (dead); becomes HIGH if wired in.

## Hardware ref
`docs/APU_PITCH_TABLE_REFERENCE.md` §1; `docs/APU_PULSE_REFERENCE.md` §3.

## Related
NH-08; NESEmulatorCore duplication.

## Suggested Fix
Delete the duplicate `NESEmulatorCore` in `envelope_processor.py`; if vibrato is wanted, add it to the live core with a re-clamp to `[8, 0x7FF]`.
