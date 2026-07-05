# NH-21: Serializer emits `$FE` macro-loop control that the live engine cannot decode

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/163
**Severity:** MEDIUM
**Domain:** nes-hardware
**Source:** AUDIT_NES_HARDWARE_2026-07-01.md
**Labels:** medium, nes-hardware, bug

## Description
The macro bytecode contract (`docs/AUDIO_BYTECODE_SPEC.md` §2.3) defines `$FF` (end/sustain)
and `$FE, <offset>` (loop). `_compress_macro` implements both and picks whichever encoding
is shorter. The shipped evaluator implements only `$FF`: on reading `$FE` it treats it as a
data value (`@not_end`), writes it to the channel parameter, consumes the `loop_start`
operand as the next frame's value, then walks the step index past the macro's end into the
adjacent macro's bytes until some `$FF` appears. Today all generated macro sequences are
constant per note (frame-invariant), and for a constant sequence sustain (`[v, $FF]`, 2
bytes) always beats loop (`[v, $FE, 0]`, 3 bytes) — so `$FE` is not emitted on typical
input. But it is reachable: a merged run of same-note frames with alternating volumes
(e.g. a 60Hz drum-roll/tremolo re-strike pattern) makes loop compression win and emits `$FE`
into `macro_vol_*`, desyncing that channel's volume stream at runtime.

## Location
`exporter/exporter_ca65.py:836-860` (`_compress_macro` loop compression emits
`[..., 0xFE, loop_start]`); consumer `nes/audio_engine.asm:53-83` (`EVAL_MACRO` handles only
`$FF`); the `$FE`-capable macro runtime exists only in the unused `process_channel_macros`
copy (`nes/project_builder.py:274-330`, `.global` with zero callers).

## Impact
None on typical songs today; wrong volumes/pitches on the affected channel when the
alternating-value case is hit, and a guaranteed break for the first future producer of
non-constant macros (vibrato, ADSR wiring). Also every bytecode ROM ships the dead
`process_channel_macros` runtime whose behavior diverges from the live one.

## Related
#77 (closed — data-byte side), #83 (spec doc-rot), #38 (dead duplicate core pattern).

## Suggested Fix
Either implement `$FE` in `EVAL_MACRO` (mirror the dead copy's `@loop_vol` logic) or delete
loop compression from `_compress_macro` (and the dead `process_channel_macros`) so the
emitted format matches the engine exactly.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# NH-22: `$4017` init comments claim "mode 1" but `$40` is 4-step (mode 0)

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/164
**Severity:** LOW
**Domain:** nes-hardware
**Source:** AUDIT_NES_HARDWARE_2026-07-01.md
**Labels:** low, nes-hardware, enhancement, documentation

## Description
Both init paths write `$40` to `$4017`, which per the frame-counter reference is Mode 0
(4-step) with the IRQ-inhibit bit set — the doc's explicitly recommended value. The
accompanying comments call it "mode 1" (which would be `$C0`/`$80`, the 5-step sequence).
Functionally fine — IRQ is inhibited either way and the engine bypasses the sequencer — but
the comment misstates the hardware mode bit in two places.

## Location
`exporter/exporter_ca65.py:755` ("Frame counter mode 1, disable frame IRQ");
`nes/audio_engine.asm:126-127` ("$4017 = $40: frame counter mode 1 …").

## Impact
None at runtime; comment/doc divergence only.

## Suggested Fix
s/mode 1/4-step mode (mode 0)/ in both comments.

## Completeness Checks
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
