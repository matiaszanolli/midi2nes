# NH-HW-2026-08-21-1: Bytecode engine addresses only 32 instruments but the exporter emits up to 256 — ids >= 32 silently alias mod 32

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/429
**Severity:** HIGH
**Domain:** nes-hardware
**Source report:** docs/audits/AUDIT_NES_HARDWARE_2026-08-21.md
**Filed:** 2026-08-21

## Location
- `nes/audio_engine.asm:486-491` (`lda current_inst, x` / `asl` ×3 / `sta temp_inst_base` — 8-bit multiply)
- `nes/audio_engine.asm:81-110` (`EVAL_MACRO`: 8-bit `Y` in both jukebox and non-jukebox branches)
- vs. `exporter/exporter_ca65.py:1009-1028` (`_register_instrument`, which only raises above `0xFF`)

## Description
Each instrument occupies 8 bytes of `instrument_table` (4 macro pointers). The engine computes
the row offset as `current_inst * 8` with three `asl`s of the 8-bit accumulator and indexes with
8-bit `Y`, so the reachable window is exactly 32 instruments; for `inst_id >= 32` the offset wraps
mod 256 and the engine reads instrument `inst_id % 32`'s macro pointers instead. The serializer's
`_register_instrument` guard only rejects ids above 255. Every note carrying an aliased
`CMD_INSTRUMENT` plays with another instrument's macros — wrong volume/pitch/duty/noise-mode.

## Impact
Bytecode-path songs (default pipeline and every `song build` ROM) with ≥ 33 unique instrument
combinations silently play wrong macros on all notes using instruments 32+. No error, no warning.
The repo's own `input.mid` already produces 22 unique instruments — 32 is a realistic ceiling.

## Suggested Fix
Lower `_register_instrument`'s ceiling to 32 (`new_id > 0x1F`), and document the limit in
`docs/AUDIO_BYTECODE_SPEC.md`. Alternatively widen the engine to 16-bit pointer math.

## Related
#80/EXP-04 (the >256 guard this slips under).

## Dedup check
Searched fresh `gh issue list --state open` snapshot (6 open issues at filing time: #425-428, #2,
#3) and prior `docs/audits/AUDIT_NES_HARDWARE_*` / `AUDIT_EXPORTERS_*` reports — no match found.
