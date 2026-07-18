# Exporters Audit — 2026-07-18

Scope: `exporter/` output generators — the CA65 macro-bytecode path
(`export_tables_with_patterns`, the default `python main.py input.mid out.nes`
run, weighted first), the direct-frame path (`export_direct_frames`,
`--no-patterns`), NSF (`exporter_nsf.py`), and FamiStudio
(`exporter_famistudio.py`) — per `.claude/commands/audit-exporters/SKILL.md`.
Cross-checked against `docs/AUDIO_BYTECODE_SPEC.md`, `docs/MACRO_USAGE_GUIDE.md`,
the shipped engine `nes/audio_engine.asm`, the frame producer
`nes/emulator_core.py`, the MMC3 mapper `mappers/mmc3.py`, and the consumer
`nes/project_builder.py`. Severity floors from `.claude/commands/_audit-severity.md`.

Dedup sources: `gh issue list --repo matiaszanolli/midi2nes --limit 300 --json
number,title,state,labels` (saved to `/tmp/audit/issues.json`, 24 open issues)
and every prior report in `docs/audits/`. Per the SKILL's framing this is a
delta / re-verify pass. **This report supersedes an earlier same-day draft of
`AUDIT_EXPORTERS_2026-07-18.md`: its two findings (EXP-11, EXP-12) were both
landed as fixes by commit `08e7fb2` between that draft and this pass — see
"Resolved this cycle" — so both are re-verified fixed here rather than
re-reported.**

**Baseline re-verification (all prior exporter fixes re-read at HEAD, confirmed
holding):**
- EXP-01 / #77 — `_encode_macro_offset` (`exporter_ca65.py:71-86`) clamps to
  `[-128,127]` and snaps `-1`→`$00`, `-2`→`$FD` off the reserved `$FF`/`$FE`
  control bytes; routed from all four encode sites (`:1140`, `:1144`, `:1159`,
  `:1160`). Holds.
- EXP-02 / #78 — `midi_note_to_timer_value(note, channel)` is called **with**
  `channel` on both note-start (`:1138`) and continuation (`:1157`) paths, so
  sustained triangle uses `NES_TRIANGLE_TABLE`. Holds.
- EXP-03 / #79 (D8) — `main.py:1198` `choices=['ca65']`; `run_export` (`:544`)
  branches only on `"ca65"`; `--format nsf` fails argparse up front. Holds.
- EXP-04 / #80 — `_register_instrument` (`:908-927`) raises when `inst_id`
  would exceed `$FF`. `MAX_SEQUENCE_BANK` guard (`:1252-1260`) still raises on
  every over-budget bank path. Holds.
- EXP-05 / #81 — `NSFExporter.export()`/`export_nsf()` (`exporter_nsf.py:73-80`)
  raise `NotImplementedError`; the deleted JSON/hand-assembled routines are
  gone; `NSFHeader`/`NSFMacroPacker` have no live caller. Holds.
- #158 — `midi_note_to_timer_value` clamps `[24,119]` (`:46`); the note baked
  into the bytecode is clamped on both ends (`:1085-1095`). Holds.
- #163 / NH-21 — `_compress_macro` (`:929-963`) emits only `$FF`, never `$FE`.
  Holds. Spec §2.3 marks the in-macro `$FE` reserved/not-implemented; §3
  documents the sequence-level `$FE CMD_BANK_JUMP` as distinct (EXP-07 / #83).
- #298 / EXP-10 — tone-note clamp is counted and reported
  (`:1049-1105`, `:1311-1318`). Fixed and holds.
- #72 / D-09 — no `$87` / `CMD_DMC_LEVEL` emitter in `exporter_ca65.py`. Holds.

---

## Summary

### Counts by severity
- CRITICAL: 1 (EXP-13 — NEW)
- HIGH: 0
- MEDIUM: 0
- LOW: 1 (EXP-09 — re-confirmed open, #302, unchanged)
- **Genuinely new this cycle: 1**
- Resolved since the earlier same-day draft: EXP-11 (#313), EXP-12 (#314/#315)

### Counts by dimension
- D1 (CA65 well-formedness / builder compat): **1 new (EXP-13 — multi-bank
  channel-start bank not communicated to the engine)**
- D2 (APU register serialization): 0 new (re-verified clean)
- D3 (pattern-vs-empty paths): 0 new (`references`-unused docstring accurate;
  grep confirms `references` appears only in the signature/docstring of
  `export_tables_with_patterns`)
- D4 (byte-range safety): 0 new (EXP-04/#80 guards hold; every macro/`.byte`
  operand ≤ 255)
- D5 (bytecode-spec conformance): 0 new (spec §3 in sync with exporter + engine)
- D6 (macro emission): 0 new (null macro seeded, Vol/Arp/Pitch/Duty order intact)
- D7 (cross-exporter consistency): 0 new (EXP-11 FamiStudio crash fixed by #313;
  NSF raises loudly)
- D8 (format-string / CLI mismatch): 0 new (re-verified clean)

### Three highest-impact findings (default CA65 macro-bytecode path first)
1. **EXP-13 (CRITICAL, NEW)** — In the default macro-bytecode path, a song whose
   total sequence bytecode exceeds one 8 KB MMC3 bank makes every channel *after*
   the first spill start in a PRG bank the engine cannot reach: the exporter
   never resets its bank counter per channel, so `pulse2/triangle/noise/dpcm`
   `*_sequence` labels can be emitted into `BANK_01+`, but `audio_init` hardcodes
   `stream_bank = $00` for all five channels. Those channels are read from the
   wrong physical bank → wrong notes then silence. Silent, no diagnostic, on the
   supported multi-bank path MMC3's 512 KB exists to serve.
2. **EXP-11 (RESOLVED)** — FamiStudio `dpcm_sample_map` crash fixed by #313
   (commit `08e7fb2`): `generate_famistudio_txt` now skips the side table
   (`exporter_famistudio.py:88`, `:94`).
3. **EXP-12 (RESOLVED)** — the dead second macro/DPCM engine block in
   `nes/project_builder.py` was removed by #314/#315 (commit `08e7fb2`); a
   regression test (`tests/test_nes_project_builder.py:578-599`) asserts its
   absence.

---

## Findings

### EXP-13: Multi-bank songs — channel sequence-start bank is never communicated to the engine, which assumes bank 0 for all channels
- **Severity**: CRITICAL
- **Dimension**: 1 (CA65 Well-Formedness & Builder Compatibility) — the exporter
  emits `*_sequence` labels into MMC3 swap banks the consumer engine's
  initialization cannot locate.
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` §2.1 (the song header "Points to
  the initial bytecode streams for all 5 channels") and §3 `$FE CMD_BANK_JUMP`
  ("for songs whose bytecode outgrows one 8KB bank"). Consumers:
  `nes/audio_engine.asm:90-125` (`audio_init`) and `nes/project_builder.py:149`
  (`fetch_sequence_byte`).
- **Location**: `exporter/exporter_ca65.py:1210-1211` (`current_bank`/
  `bytes_in_current_bank` initialized **once**, before the channel loop, and
  never reset per channel), `:1220-1221` (`{channel}_sequence:` label emitted
  into whatever segment the previous channel left active), `:1250-1268` (bank
  rollover advances `current_bank` mid-channel and never returns to bank 0).
  Consumer mismatch: `nes/audio_engine.asm:96-125` (`sta stream_bank+0..+4`, all
  loaded from `#$00`).
- **Status**: NEW (no open issue in `/tmp/audit/issues.json`; not raised by any
  prior `docs/audits/AUDIT_EXPORTERS_*.md` or `AUDIT_MAPPERS_*.md` — the mapper
  audits covered `CODE_8000`/`BANK_NN`/`DPCM_NN` capacity and the `MAX_SEQUENCE_BANK`
  overflow guard, but not the per-channel *starting* bank).
- **Description**: The macro-bytecode emitter writes the five channel sequences
  (`pulse1, pulse2, triangle, noise, dpcm`) consecutively into `.segment
  "BANK_NN"` regions. `current_bank` starts at 0 (`:1210`) and is advanced only
  when a channel's bytecode overflows the current 8 KB bank (`:1250`,
  `next_bank = current_bank + 1`, then `.segment "BANK_{next_bank}"`). It is
  **never reset between channels** (grep of `current_bank`/`bytes_in_current_bank`
  shows assignments only at `:1210-1211` init, `:1264-1265` on rollover, and
  the `+= 1/2` accumulators). So once the cumulative bytecode of the earlier
  channels crosses ~7936 bytes (`BANK_SIZE_LIMIT = 8192 - 256`), the next
  channel's `{channel}_sequence:` label is defined inside `BANK_01` (or higher)
  — i.e. physical `PRG_BANK_01`, linked at `$C000` per
  `mappers/mmc3.py:generate_linker_config` (all `BANK_NN` load at `start=$C000`).

  At runtime `audio_init` (`nes/audio_engine.asm:90-125`) seeds each channel's
  stream pointer from its exported label **and hardcodes `stream_bank = $00`**
  for all five channels. `fetch_sequence_byte`
  (`nes/project_builder.py:149-177`) swaps `sequence_bank` (← `stream_bank,x`)
  into the MMC3 R7 window and reads the byte via a `$C000→$A000` address
  translation. So for a channel whose label physically lives in bank 1+, the
  engine maps **bank 0** into the window and reads bank 0's bytes at the
  translated address — arbitrary macro/other-channel data — interpreting it as
  that channel's sequence stream until it happens to hit a `$FF` and halts. The
  within-stream `CMD_BANK_JUMP` path is correct (it updates both `sequence_bank`
  and `stream_bank,x` at `nes/audio_engine.asm:260-261`); only the **initial**
  bank of each channel is wrong, and only `pulse1` (always the first label,
  always in `BANK_00`) is guaranteed correct.
- **Evidence**:
  ```
  # exporter/exporter_ca65.py — bank counter set once, never reset per channel
  1210:        current_bank = 0
  1211:        bytes_in_current_bank = 0
  1217:        lines.append(f'.segment "BANK_{current_bank:02d}"')   # BANK_00 once, up front
  1220:        for channel in ['pulse1','pulse2','triangle','noise','dpcm']:
  1221:            lines.append(f'{channel}_sequence:')               # emitted in the *current* bank
  ...  1264:            current_bank = next_bank                       # advances, never resets
  ```
  ```asm
  ; nes/audio_engine.asm — every channel initialized to bank 0
  99:     lda #<pulse2_sequence ... 103:  lda #$00 / sta stream_bank+1
  106:    lda #<triangle_sequence ... 110: lda #$00 / sta stream_bank+2
  ...  # stream_bank+3 (noise), stream_bank+4 (dpcm) likewise = $00
  194:    lda stream_bank, x / 195: sta sequence_bank      ; used as-is by fetch_sequence_byte
  ```
  The exporter explicitly supports up to `MMC3Mapper.SWAP_BANK_COUNT - 1 = 59`
  sequence banks (`:1209`, `:1252-1260`) and MMC3 exists to hold 512 KB "for
  large DPCM drum libraries" (`mappers/mmc3.py:9`), so multi-bank sequence
  output is a deliberately-supported path, not an out-of-spec input.
- **Impact**: Any song whose macro bytecode across `pulse1..pulse2/triangle/…`
  crosses one 8 KB bank boundary before a later channel's start label plays
  garbage-then-silence on that channel and every channel after it, with no
  diagnostic. `pulse1` (first label) is always safe; `pulse2/triangle/noise/dpcm`
  are corrupted whenever they land past bank 0. This is the default
  `python main.py in.mid out.nes` (pattern/macro) path. Reachability threshold:
  > ~7936 bytes of cumulative sequence bytecode (a long/dense multi-channel
  song — precisely the material MMC3 is selected for). Silent contract
  corruption / garbage playback with no workaround the user can apply → CRITICAL
  per `_audit-severity.md` ("Pipeline stage emits data a downstream stage parses
  as valid but means something else", and the multi-bank/garbage-playback rows).
- **Related**: `MAX_SEQUENCE_BANK` overflow guard (`:1252-1260`, #127) and the
  within-stream `CMD_BANK_JUMP` (EXP-07 / #83) — both handle *other* facets of
  multi-bank output correctly; this is the one uncovered facet (channel *entry*
  bank). Same subsystem as the mapper capacity checks in `mappers/mmc3.py:validate`.
- **Suggested Fix**: Make the channel start bank explicit and agree on both
  sides. Simplest: have `export_tables_with_patterns` record the bank each
  `{channel}_sequence:` label is emitted in, emit it as a 5-byte
  `channel_start_banks` table (`.export`ed), and have `audio_init` load
  `stream_bank+0..+4` from that table instead of hardcoding `#$00`. (Resetting
  `current_bank`/`bytes_in_current_bank` per channel is **not** a fix on its own —
  it would force overlapping labels into `BANK_00` and overflow it; the engine
  still needs to be told each channel's bank.) Add a regression test that builds
  a >8 KB multi-channel song and asserts each `*_sequence` label's bank matches
  the `stream_bank` the engine initializes.

---

## Existing findings re-confirmed, already tracked (not re-counted as new)

- **EXP-09 (#302, OPEN, LOW)** — `exporter/compression.py`'s `CompressionEngine`
  and `BaseExporter.compress_channel_data`/`decompress_channel_data`
  (`base_exporter.py:4,10,12-46`) remain dead: grep across `*.py` (excluding
  tests/docs) returns only the definitions and the `BaseExporter` wrappers — no
  exporter or `main.py` call site. Unchanged.
- **TD-08 (#137, OPEN)** — stale DPCM `.incbin` TODO in the macro path
  (`exporter_ca65.py:991`); real DPCM work is done by `DpcmPacker` elsewhere.
  Tracked as tech debt.
- **TD-11 (#136, OPEN)** — `export_direct_frames` remains a ~700-line monolith;
  tech debt, not re-counted here.

## Resolved this cycle (since the earlier same-day draft)

- **EXP-11 (#313) — FIXED** by commit `08e7fb2`. `generate_famistudio_txt` now
  skips `dpcm_sample_map` in both the max-frame scan and the pattern loop
  (`exporter/exporter_famistudio.py:88`, `:94-99`). Re-ran the exact repro from
  the prior draft (`frames` with a populated `dpcm_sample_map` and a
  multi-hundred-frame tone channel) → **no crash**.
- **EXP-12 (#314/#315) — FIXED** by commit `08e7fb2`. The dead
  `seq_cmd_instrument`/`seq_cmd_dpcm_play` routines and their `ch_*` BSS block
  are gone from `nes/project_builder.py` (now only a "removed" comment at
  `:137`); `tests/test_nes_project_builder.py:578-599` asserts these symbols are
  absent from the generated `music.asm`. `fetch_sequence_byte` (the one live
  routine that shared that block) is retained.

## Methodology notes (disproved / re-disproved candidates)

- **DPCM `note` byte (0-255) colliding with the macro-path command ranges
  (D4/D5)** — re-verified disproved: the DPCM `note = sample_id + 1` byte is
  always emitted as the *second* byte of a Length-command pair
  (`${length:02X}, ${note:02X}`, `:1282`); the engine's dispatch inspects only
  the *first* byte of each fetch (`@read_next`, `nes/audio_engine.asm:197-213`),
  so a high DPCM note is consumed as length-command data, never misread as
  `$FE`/`$FF`/`$80`. (Matches the 2026-07-06 conclusion.)
- **Direct-path triangle control `0x80 | (volume*7)` (D2)** — re-verified
  targets `$4008` linear-counter load; `volume*7 ≤ 105` stays in 7 bits and is
  forced to `$00` when `volume == 0` (`:343-346`). Not a finding.
- **D1 segment/label cross-check** — the macro path `.export`s
  `pulse1_sequence…dpcm_sequence`, `ntsc_period_low/high`,
  `triangle_period_low/high`, `instrument_table` (`:1004-1007`), all `.import`ed
  by `nes/audio_engine.asm:4-10`; `.importzp ptr1,temp1,temp2,frame_counter`
  resolve via `audio_engine.asm:16` `.exportzp`; non-standalone
  `.import audio_init,audio_update` resolve via `audio_engine.asm:53`. Direct
  path `.importzp frame_counter,temp_ptr` resolve via `project_builder.py:319`
  (`temp_ptr`) and `:284-286` (`frame_counter`, direct-only). All segments the
  exporters emit (`CODE_8000`, `BANK_NN`, `DPCM`, `RODATA[_BANK_NN]`, `HEADER`,
  `ZEROPAGE`, `BSS`, `CODE`, `VECTORS`) are declared by
  `mappers/mmc3.py:generate_linker_config`. No new D1 finding beyond EXP-13
  (which is a *bank-assignment* mismatch, not a missing label/segment).

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-07-18.md
```
