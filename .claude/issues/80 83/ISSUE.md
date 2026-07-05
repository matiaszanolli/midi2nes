# #80 — EXP-04: inst_id and loop_start can exceed one byte and emit a 3-hex-digit .byte

**Severity:** MEDIUM · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-06-29.md

`inst_id` and `loop_start` can exceed one byte and emit a 3-hex-digit `.byte`.

## Description
`inst_id = instruments[inst]` grows with the count of unique (vol,arp,pitch,duty) tuples; with >256 unique instruments `${inst_id:02X}` formats as `$100` (3 hex digits), which `ca65` rejects (or, if it parsed, the engine's single-byte `CMD_INSTRUMENT` fetch reads the wrong id). Likewise `_compress_macro` stores `loop_start` (a raw frame index into the macro) as the `$FE` operand; for a single note longer than 256 frames whose macro loops late, `loop_start > 255` formats as `$1xx`.

## Location
`exporter/exporter_ca65.py:1118` (`.byte $80, ${inst_id:02X}`), `:825` (`comp = data[:loop_start + p_len] + [0xFE, loop_start]`, later emitted via `${val:02X}` at `:1052`).

## Spec ref
`docs/AUDIO_BYTECODE_SPEC.md` §3 (`$80 [id]` instrument id is one byte); §2.3 (`$FE,<offset>` loop offset is one byte).

## Evidence
- `:983` `instruments[inst] = len(instrument_defs)` (unbounded); `:1118` formats it `:02X`.
- `:823-825` `loop_start = n - (repeats + 1) * p_len` (bounded only by macro length `n`); `:1052` emits each macro byte `:02X`.

## Impact
Assembly failure (or wrong instrument/loop) on songs with very high timbre variety (>256 distinct instruments) or a single note > ~4.3 s with a late macro loop. Realistic only for dense/long material, hence MEDIUM, but it is a hard `ca65` error when hit.

## Related
EXP-01 (same `$FE` operand byte domain).

## Suggested Fix
Assert/guard `inst_id <= 0xFF` (and cap or split instrument count) and `loop_start <= 0xFF` (cap macro length before loop encoding), emitting a clear error rather than an out-of-range `.byte`.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte)
- [ ] **ROUNDTRIP**: If compression code changes, decompressed playback == original
- [ ] **SIBLING**: Same pattern checked in related emit sites
- [ ] **TESTS**: A regression test pins this specific fix

---

# #83 — EXP-07: AUDIO_BYTECODE_SPEC.md §3 contradicts the shipped engine/exporter on $FE, $87, and DPCM opcode

**Severity:** LOW · **Domain:** documentation · **Source:** AUDIT_EXPORTERS_2026-06-29.md

`docs/AUDIO_BYTECODE_SPEC.md` §3 contradicts the shipped engine/exporter on `$FE`, `$87`, and DPCM opcode.

## Description
The exporter and the shipped engine **agree** with each other but **disagree with the spec doc**: the exporter emits `$FE`+bank+ptr_lo+ptr_hi as `CMD_BANK_JUMP` (`exporter_ca65.py:1102`) and the engine decodes exactly that (`audio_engine.asm:260-276`); the exporter emits `$87`+level as `CMD_DMC_LEVEL` (`:1112`) and the engine decodes it (`:253-257`). But §2.3 defines `$FE` as the **macro-loop** control byte (true *inside macros*, a different namespace) and §3 lists **no** `$87` and no bank-jump opcode, while listing `$85 CMD_DPCM_PLAY` and `$84 CMD_JUMP` that the exporter never emits in this path. The doc is stale relative to the implemented sequencer commands.

## Location
`docs/AUDIO_BYTECODE_SPEC.md` §3 command table (lines ~65-73) and §2.3.

## Spec ref
`docs/AUDIO_BYTECODE_SPEC.md` §2.3 / §3 vs `nes/audio_engine.asm:253-276` and `exporter/exporter_ca65.py:1102, 1112, 1118`.

## Evidence
§3 table has `$80,$81,$82,$83,$84,$85,$86` and no `$87`/`$FE`-sequence-command rows; engine command dispatch handles `$FE` (`CMD_BANK_JUMP`, `:260`) and `$87` (`CMD_DMC_LEVEL`, `:253`).

## Impact
Documentation-only. Anyone implementing a second engine or tooling from the spec would mis-decode `$FE`/`$87`. No runtime effect because the exporter and engine match. LOW (doc-rot).

## Related
EXP-01 (the `$FE`/`$FF` macro-control collision is the *real* runtime issue in the macro namespace).

## Suggested Fix
Update §3 to document `$87 CMD_DMC_LEVEL` and the `$FE` four-byte sequence-level bank-jump (distinct from the in-macro `$FE` loop), and remove/realign the `$84`/`$85` rows that the implemented path does not use.

## Completeness Checks
- [ ] **DOC**: The `docs/*.md` is corrected to match the shipped engine/exporter
- [ ] **SIBLING**: Same doc-vs-code check applied to related opcode rows
