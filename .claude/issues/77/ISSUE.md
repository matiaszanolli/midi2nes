**Severity:** HIGH · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-06-29.md

Macro pitch/arp data values collide with the `$FE`/`$FF` macro control bytes.

## Description
Pitch macro entries are `pitch_offset = max(-128, min(127, pitch_val - base_timer)) & 0xFF`. A bend of −1 timer unit yields `0xFF`; −2 yields `0xFE`. Arp entries are `frame_data.get('arp', 0) & 0xFF`; a negative arpeggio offset (semitone down) yields `0xFF`/`0xFE` likewise. These bytes are appended to the macro sequence and then handed to `_compress_macro`, which also *appends its own* `$FF`/`$FE` control bytes. The 6502 macro evaluator (`EVAL_MACRO` and the duplicate `process_channel_macros`) treats the **first** `$FF` it reads as "end of macro / sustain" and `$FE` as "loop". So a legitimate −1 pitch-bend frame in the middle of a vibrato macro terminates the macro early; a −2 frame is read as a loop command and consumes the following data byte as a loop offset, desyncing the whole stream.

## Location
`exporter/exporter_ca65.py:992`, `:1007` (pitch), `:993`, `:1008` (arp); consumed by `_compress_macro` `:782-825` and emitted as `macro_pitch_*`/`macro_arp_*` `.byte` rows at `:1048-1052`.

## Spec ref
`docs/AUDIO_BYTECODE_SPEC.md` §2.3 ("`$FF`: End of macro (sustain last value)", "`$FE, <offset>`: Loop"); engine `nes/audio_engine.asm` `EVAL_MACRO` (`cmp #$FF / bne @not_end`).

## Evidence
- `:992` `pitch_offset = max(-128, min(127, pitch_val - base_timer)) & 0xFF` — no exclusion of `0xFE`/`0xFF`.
- `:993` `arp_val = frame_data.get('arp', 0) & 0xFF` — no exclusion either.
- `_compress_macro` (`:787-825`) inserts `[0xFF]` and `[0xFE, loop_start]` as terminators on the *same value domain*.
- Engine `EVAL_MACRO`: `lda (ptr1), y / cmp #$FF / bne @not_end` — any `$FF` in the data ends the macro.

## Impact
Wrong pitch / truncated envelope on any note carrying a small downward pitch bend or a downward arpeggio step — i.e. vibrato, portamento, and minor-interval arps, which `docs/MACRO_USAGE_GUIDE.md` §1–2 actively advertise. Macro-bytecode (default) path; affects pulse1/pulse2/triangle. Silently changes the played song with no diagnostic.

## Related
EXP-04 (loop_start byte range); `docs/MACRO_USAGE_GUIDE.md` §1.

## Suggested Fix
Reserve `$FE`/`$FF` for control only. Bias/encode signed offsets so the data domain cannot reach `0xFE`/`0xFF` (e.g. store offset as `127+value`, or use a separate escape), or clamp the offset domain to `[-125, 125]` and document the limit. The engine's `EVAL_MACRO` must agree with whatever encoding is chosen.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
