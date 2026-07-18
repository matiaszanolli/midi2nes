# EXP-13: Multi-bank songs — per-channel sequence-start bank never told to the engine
**Filed as:** #328

**Severity:** CRITICAL · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-18.md

## Description
In the default macro-bytecode export path, the CA65 exporter writes the five channel sequences (`pulse1, pulse2, triangle, noise, dpcm`) consecutively into `.segment "BANK_NN"` regions. `current_bank` is initialized **once** before the channel loop (`exporter/exporter_ca65.py:1210`) and advanced only when a channel's bytecode overflows the current 8 KB bank (`:1264`, `current_bank = next_bank`). It is **never reset between channels**. So once the cumulative bytecode of the earlier channels crosses ~7936 bytes (`BANK_SIZE_LIMIT = 8192 - 256`), the next channel's `{channel}_sequence:` label (`:1221`) is defined inside `BANK_01` (or higher) — physical `PRG_BANK_01`, linked at `$C000` per `mappers/mmc3.py:generate_linker_config`.

At runtime `audio_init` (`nes/audio_engine.asm:90-125`) seeds each channel's stream pointer from its exported label but **hardcodes `stream_bank = $00`** for all five channels (`sta stream_bank+0..+4`, each preceded by `lda #$00`). `fetch_sequence_byte` (`nes/project_builder.py`) swaps `sequence_bank` (← `stream_bank,x`) into the MMC3 R7 window and reads the byte via a `$C000→$A000` address translation. So for a channel whose label physically lives in bank 1+, the engine maps **bank 0** into the window and reads bank 0's bytes at the translated address — arbitrary macro/other-channel data — interpreting it as that channel's sequence stream until it happens to hit a `$FF` and halts.

The within-stream `CMD_BANK_JUMP` path is correct (it updates both `sequence_bank` and `stream_bank,x` at `nes/audio_engine.asm:261`); only the **initial** bank of each channel is wrong. `pulse1` (always the first label, always in `BANK_00`) is guaranteed correct; `pulse2/triangle/noise/dpcm` are corrupted whenever they land past bank 0.

## Evidence
```
# exporter/exporter_ca65.py — bank counter set once, never reset per channel
1210:        current_bank = 0
1211:        bytes_in_current_bank = 0
1217:        lines.append(f'.segment "BANK_{current_bank:02d}"')   # BANK_00 once, up front
1220:        for channel in ['pulse1','pulse2','triangle','noise','dpcm']:
1221:            lines.append(f'{channel}_sequence:')               # emitted in the *current* bank
1264:                    current_bank = next_bank                    # advances, never resets to 0
```
```asm
; nes/audio_engine.asm — every channel initialized to bank 0
96:     lda #$00 / 97:  sta stream_bank+0
103:    lda #$00 / 104: sta stream_bank+1   ; pulse2
110:    lda #$00 / 111: sta stream_bank+2   ; triangle
117:    lda #$00 / 118: sta stream_bank+3   ; noise
124:    lda #$00 / 125: sta stream_bank+4   ; dpcm
194:    lda stream_bank, x / 195: sta sequence_bank      ; used as-is by fetch_sequence_byte
```
The exporter explicitly supports up to `MMC3Mapper.SWAP_BANK_COUNT - 1 = 59` sequence banks (`:1252-1260`) and MMC3 exists to hold 512 KB, so multi-bank sequence output is a deliberately-supported path, not an out-of-spec input.

## Impact
Any song whose macro bytecode across the channels crosses one 8 KB bank boundary before a later channel's start label plays garbage-then-silence on that channel and every channel after it, with no diagnostic. This is the default `python main.py in.mid out.nes` (pattern/macro) path. Reachability threshold: > ~7936 bytes of cumulative sequence bytecode (a long/dense multi-channel song — precisely the material MMC3 is selected for). Silent contract corruption / garbage playback with no workaround the user can apply.

## Related
`MAX_SEQUENCE_BANK` overflow guard (`exporter_ca65.py:1252-1260`, #127) and the within-stream `CMD_BANK_JUMP` (EXP-07 / #83) both handle *other* facets of multi-bank output correctly; this is the one uncovered facet (channel *entry* bank).

## Suggested Fix
Make the channel start bank explicit and agree on both sides. Have `export_tables_with_patterns` record the bank each `{channel}_sequence:` label is emitted in, emit it as a 5-byte `.export`ed `channel_start_banks` table, and have `audio_init` load `stream_bank+0..+4` from that table instead of hardcoding `#$00`. (Resetting `current_bank`/`bytes_in_current_bank` per channel is **not** a fix on its own — it would force overlapping labels into `BANK_00` and overflow it; the engine still needs to be told each channel's bank.) Add a regression test that builds a >8 KB multi-channel song and asserts each `*_sequence` label's bank matches the `stream_bank` the engine initializes.

## Completeness Checks
- [ ] **CONTRACT**: exporter's per-channel bank assignment propagated to `audio_init`'s `stream_bank` initialization in lockstep
- [ ] **CC65**: the new `channel_start_banks` table is `.export`ed and `.import`ed so a missing symbol fails at link, not silently
- [ ] **SIBLING**: same start-bank assumption checked for any future 6th channel / DPCM bank paths
- [ ] **TESTS**: a regression test builds a >8 KB multi-channel song and asserts each `*_sequence` label's bank matches the engine's `stream_bank`
- [ ] **DOC**: `docs/AUDIO_BYTECODE_SPEC.md` §2.1 updated to document the per-channel start-bank table