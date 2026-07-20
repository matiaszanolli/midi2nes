# EXP-2026-07-19-1: DPCM note in macro-bytecode stream clamped to 255, not the $00–$5F engine note range

**Issue:** #369
**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-19.md
**Labels:** low, exporters, bug

**Dimension:** D4 Byte-Range Safety (cross-ref D5 Bytecode-Spec Conformance)
**Location:** `exporter/exporter_ca65.py:1082-1096` and emission `:1291`; engine dispatch `nes/audio_engine.asm:213-219`

## Description
In the macro-bytecode path, the DPCM channel's `note` (= `sample_id + 1`) is deliberately clamped only to a single byte (`if note > 255: note = 255`, `:1084`), citing #67 which correctly stopped collapsing high drum ids to 95. But DPCM events are emitted through the *same* length+note serializer as tone channels (`.byte ${(write_dur-1)+0x60}, ${note:02X}`, `:1291`), and the 6502 engine re-dispatches every stream byte by range: `< $60` → note, `$60–$7F` → length, `>= $80` → command (`audio_engine.asm:213-219`). `docs/AUDIO_BYTECODE_SPEC.md` §3 states notes occupy `$00–$5F` and that "DPCM sample triggers are encoded as regular note bytes". A DPCM `note` of `$60` or higher (i.e. `sample_id >= 95`) is therefore misread as a Length or Engine command, desyncing the entire DPCM stream from that point.

## Evidence
`note` cap for dpcm is 255 (`:1083-1085`), tone notes cap at 95 (`:1086`). The direct-export path has no such limit (DPCM notes live in a dedicated `dpcm_note` byte table read by index, not dispatched), so the two paths diverge on the maximum supported `sample_id` (direct: 254; bytecode: 94).

## Impact
Latent. Requires a single song with >94 distinct packed DPCM samples, unreachable on any real NES PRG/DPCM ROM budget. Blast radius if reached: DPCM channel only, bytecode path only.

## Related
#67 (dpcm 95-clamp removal), spec §3, EXP-07/#83 (bytecode dispatch).

## Suggested Fix
Either clamp DPCM `note` to `0x5F` in the bytecode path, or assert `sample_id < 95` and raise a clear `ValueError`. Document the 94-sample bytecode ceiling next to the `:1083` comment.

## Status as filed
NEW, CONFIRMED against current code (clamp at exporter_ca65.py:1084; emission :1291).
