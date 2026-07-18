# EXP-12: nes/project_builder.py ships a second, fully dead macro-instrument/DPCM-trigger implementation

**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-18.md
**Filed as:** #314

## Description
`seq_cmd_instrument` and `seq_cmd_dpcm_play` (plus ~85 bytes of supporting ch_* BSS state) appended by `NESProjectBuilder.prepare_project` into every bytecode-mode music.asm are never called — nes/audio_engine.asm implements both operations inline. `fetch_sequence_byte` in the same block IS live and must be kept.

## Location
`nes/project_builder.py:136-168` (seq_cmd_dpcm_play), `:171-288` (BSS + seq_cmd_instrument at :244-286)

## Suggested Fix
Delete the two dead routines and their dedicated BSS block; keep fetch_sequence_byte.

## Note
Same issue as DP-06 in AUDIT_DPCM_2026-07-18.md — filed once here since exporters report processed first; DP-06 to be skipped as duplicate of #314.

## Related
#203/NH-28, #163/NH-21 (closed)
