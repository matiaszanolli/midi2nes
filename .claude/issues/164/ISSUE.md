# NH-22: `$4017` init comments claim "mode 1" but `$40` is 4-step (mode 0)

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

## Description
Both init paths write `$40` to `$4017`, which per the frame-counter reference is Mode 0
(4-step) with the IRQ-inhibit bit set — the doc's explicitly recommended value. The
accompanying comments call it "mode 1" (which would be `$C0`/`$80`, the 5-step sequence).
Functionally fine — IRQ is inhibited either way and the engine bypasses the sequencer — but
the comment misstates the hardware mode bit in two places and will mislead the next person
touching init.

## Location
`exporter/exporter_ca65.py:755` ("Frame counter mode 1, disable frame IRQ");
`nes/audio_engine.asm:126-127` ("$4017 = $40: frame counter mode 1 …").

## Evidence
`docs/APU_FRAME_COUNTER_REFERENCE.md` §2 (`MI--.----`, M=0 => 4-step) and §4 (recommended `$40` vs `$C0` values); code comments above.

## Impact
None at runtime; comment/doc divergence only.

## Related
#43 (previous doc-rot class).

## Hardware ref
`docs/APU_FRAME_COUNTER_REFERENCE.md` §2 Register Map, §3 Sequencer Modes, §4 Engine Implementation Notes.

## Suggested Fix
s/mode 1/4-step mode (mode 0)/ in both comments.

## Completeness Checks
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
