# NH-15: PULSE_DUTY_CYCLES is dead and its 8-bit values contradict the 2-bit duty field

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-29.md

## Description
`PULSE_DUTY_CYCLES` maps duty IDs `1..4` to 8-bit waveform bit patterns (`0b00000001`, `0b00000011`, `0b00001111`, `0b01111100`). A repo-wide search shows the constant is **referenced nowhere** outside its own definition — it is dead. It is also hardware-wrong as a "duty cycle" value: the NES pulse duty is a **2-bit** field (`DD`, values 0–3) in bits 6–7 of `$4000`/`$4004`, and the live control byte correctly uses `(duty_cycle & 0x03) << 6` (`nes/envelope_processor.py:121`). The 8-bit patterns here resemble the *sequencer output waveforms* per duty, not anything the engine writes, so the constant invites a future contributor to write an 8-bit "duty" into a 2-bit field.

## Location
`nes/audio_constants.py:9-14` (and the unused `NES_ENVELOPES` block in the same file).

## Evidence
`grep -rn PULSE_DUTY_CYCLES` → only `nes/audio_constants.py:9` (confirmed at HEAD). The live duty packing is `duty_bits = (duty_cycle & 0x03) << 6` at `nes/envelope_processor.py:121`. The doc duty table is 2-bit (`%00`/`%01`/`%10`/`%11`) at `docs/APU_PULSE_REFERENCE.md` §4.

## Impact
None today (dead); a correctness trap and stale-constant noise.

## Hardware ref
`docs/APU_PULSE_REFERENCE.md` §4 (Duty Cycles — 2-bit `DD`, values 0–3).

## Suggested Fix
Delete `PULSE_DUTY_CYCLES` (and the unused `NES_ENVELOPES`/commented blocks), or, if a duty table is wanted, store the canonical 2-bit values `{0,1,2,3}` with a doc cross-reference.

## Related
#34 (NH-08, other dead audio code); #107 (NH-14).

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other dead audio constants)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
