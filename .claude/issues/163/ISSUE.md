# NH-21: Serializer emits `$FE` macro-loop control that the live engine cannot decode

**Severity:** MEDIUM · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

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

## Evidence
`_compress_macro` comparison logic (`best_len`); `EVAL_MACRO`'s single `cmp #$FF`;
`_encode_macro_offset`'s own docstring treats `$FE` as reserved *because it is a live
control byte* — yet the engine can't honor it.

## Impact
None on typical songs today; wrong volumes/pitches on the affected channel when the
alternating-value case is hit, and a guaranteed break for the first future producer of
non-constant macros (vibrato, ADSR wiring). Also every bytecode ROM ships the dead
`process_channel_macros` runtime whose behavior diverges from the live one.

## Related
#77 (closed — data-byte side), #83 (spec doc-rot), #38 (dead duplicate core pattern).

## Hardware ref
`docs/AUDIO_BYTECODE_SPEC.md` §2.3 Macros (control bytes `$FF`, `$FE, <offset>`).

## Suggested Fix
Either implement `$FE` in `EVAL_MACRO` (mirror the dead copy's `@loop_vol` logic) or delete
loop compression from `_compress_macro` (and the dead `process_channel_macros`) so the
emitted format matches the engine exactly.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
