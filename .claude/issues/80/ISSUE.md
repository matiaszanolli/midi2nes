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
