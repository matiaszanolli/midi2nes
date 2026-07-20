# Exporters Audit — 2026-07-19

Scope: `exporter/exporter_ca65.py` (default CA65 path), `exporter/exporter_nsf.py`,
`exporter/exporter_famistudio.py`, and their consumers (`nes/project_builder.py`,
`nes/audio_engine.asm`, `main.py` export dispatch). Cross-checked against
`docs/AUDIO_BYTECODE_SPEC.md`, `docs/MACRO_USAGE_GUIDE.md`, and the mapper linker
configs.

This audit is predominantly a **fix-verification pass**: the prior sprint closed the
bulk of the exporter findings (see `AUDIT_EXPORTERS_2026-06-29.md`). All closed fixes
listed in the skill dimensions were re-confirmed against current code (see
"Verification results" below). Two new low-severity divergences were found.

## Summary

### Counts by severity
| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 2 |
| **Total**| **2** |

### Counts by dimension
| Dimension | Count |
|-----------|-------|
| D1 CA65 well-formedness / builder compat | 0 |
| D2 APU register serialization | 0 |
| D3 Pattern-vs-empty paths | 0 |
| D4 Byte-range safety | 1 (EXP-2026-07-19-1) |
| D5 Bytecode-spec conformance | (cross-ref EXP-2026-07-19-1) |
| D6 Macro emission | 0 |
| D7 Cross-exporter consistency | 1 (EXP-2026-07-19-2) |
| D8 Format-string / CLI choices | 0 |

### Three highest-impact findings
The default `python main.py input.mid out.nes` CA65 path (both the empty-patterns
direct emitter and the MMC3 macro-bytecode emitter) is **clean**: every emitted label
and segment resolves against the builder's linker config, APU register blocks are
correct per-channel, all byte operands are guarded, and the bytecode matches
`docs/AUDIO_BYTECODE_SPEC.md`. The only findings are two low-severity, effectively
unreachable / non-default-path divergences:

1. **EXP-2026-07-19-1 (LOW, D4/D5)** — DPCM note in the macro-bytecode stream is clamped
   to 255, not to the `$00–$5F` note-range the engine's byte dispatcher and the spec
   require; a song with >94 packed DPCM samples would desync the DPCM stream. Unreachable
   in practice (ROM budget).
2. **EXP-2026-07-19-2 (LOW, D7)** — `exporter_famistudio.py` reads `event['note']` /
   `event['volume']` via direct subscript where the CA65 path uses defensive `.get()`;
   a frame missing either key raises `KeyError` instead of degrading. Not CLI-reachable.

## Verification results (closed fixes re-confirmed in place)

| Dimension | Item | Result |
|-----------|------|--------|
| D1 | All `.export`/`.import`/`.importzp` symbols resolve: bytecode path exports `pulse1_sequence…dpcm_sequence`, `ntsc_period_low/high`, `triangle_period_low/high`, `instrument_table`, `channel_start_banks`; engine `nes/audio_engine.asm:4-11` imports exactly these. `.importzp ptr1,temp1,temp2,frame_counter` matched by engine `.exportzp` (`:17`). Direct path `.importzp frame_counter,temp_ptr` matched by `project_builder` ZEROPAGE (`temp_ptr` `:320,323`; `frame_counter` `:288-290`). `.import audio_init,audio_update` defined in engine (`:54`). | ✅ holds |
| D1 | Segments `CODE_8000`/`DPCM`/`BANK_00..59` all defined in MMC3 linker config (`SWAP_BANK_COUNT=60`, `MAX_SEQUENCE_BANK=59`). Direct `RODATA_BANK_NN` segments defined in MMC1 config (`bank_size=16384`, `RODATA_BANK_00..06`). | ✅ holds |
| D1 | Bank-overflow guard (`exporter_ca65.py:1261-1269`) raises `ValueError` on `next_bank > MAX_SEQUENCE_BANK`. | ✅ holds |
| D2 | Per-channel register blocks correct ($4000-03 / $4004-07 / $4008,$400A,$400B / $400C,$400E,$400F); no off-by-$4. Triangle control is linear-counter (`0x80|(vol*7)`, max 0xE9, 7-bit reload) to $4008, never a pulse volume nibble. `$4015`/`$4017` init present in both reset and `init_music`. | ✅ holds |
| D2 | **#78** continuation-frame pitch uses per-channel table: `midi_note_to_timer_value(note, channel)` at both note-start (`:1139`) and continuation (`:1158`). | ✅ holds |
| D2 | **#81** NSF `export()`/`export_nsf()` raise `NotImplementedError` (`exporter_nsf.py:73-80`); deleted hand-assembled opcodes gone; `NSFHeader`/`NSFMacroPacker` have no live caller (grep clean). | ✅ holds |
| D3 | Empty-`patterns` path early-returns to `export_direct_frames` (`:976-977`). `references` appears only in signature/docstring, never in the method body (grep confirmed). | ✅ holds |
| D4 | **#80** `_register_instrument` (`:919`) raises on >256 unique instruments. **#77** all pitch/arp encode sites route through `_encode_macro_offset` (`:1141,1145,1160,1161`). **#158** note clamped both ends (`:1086` >95→95, `:1088` tone <24→24). **#298** clamp tally (`:1103-1109,1331`) fires on both boundaries. No `$87`/`CMD_DMC_LEVEL`/`$85` in exporter (grep clean). | ✅ holds |
| D5 | Length+note encoding `(write_dur-1)+0x60` with `write_dur=min(rem,32)` → `$60–$7F`, matches spec §3. **#83** spec §3 documents `$FE CMD_BANK_JUMP` (sequence-level) distinct from in-macro `$FE`; exporter (`:1271`) and engine (`@cmd_bank_jump`) agree. Channel/terminator order `pulse1,pulse2,triangle,noise,dpcm` + `$FF` matches §2.1. | ✅ holds |
| D6 | `instrument_table` rows emit Vol,Arp,Pitch,Duty in order (`:1195-1196`), built/unpacked consistently. `macro_*_0 = ($FF,)` null macro seeded (`:1036-1043`) and emitted. `_compress_macro` sustain-only (`:929-963`), no `$FE`. Macro dicts dedupe by tuple. | ✅ holds |
| D7 | **#82** `midi_note_to_famistudio` clamps octave to 0–7 (`:177`); dpcm branch recovers `sample_id` from `note-1` (`:117-119`). FamiStudio iterates the same 5-channel list; `dpcm_sample_map` excluded (`:88,94`). | ✅ holds |
| D8 | **#79** `--format` `choices=['ca65']` (`main.py:1247`); `run_export` branches only on `ca65` (`:581`); dead `nsftxt` branch gone. `run_config_validate` NSF load-address print is cosmetic only. | ✅ holds (cosmetic-only, LOW-adjacent, no finding) |

## Findings

### EXP-2026-07-19-1: DPCM note in macro-bytecode stream clamped to 255, not the `$00–$5F` engine note range
- **Severity**: LOW
- **Dimension**: D4 Byte-Range Safety (cross-ref D5 Bytecode-Spec Conformance)
- **Location**: `exporter/exporter_ca65.py:1082-1096` and emission `:1291`; engine dispatch `nes/audio_engine.asm:213-219`
- **Status**: NEW
- **Description**: In the macro-bytecode path, the DPCM channel's `note` (= `sample_id + 1`)
  is deliberately clamped only to a single byte (`if note > 255: note = 255`, `:1084`),
  citing #67 which correctly stopped collapsing high drum ids to 95. But DPCM events are
  emitted through the *same* length+note serializer as tone channels
  (`.byte ${(write_dur-1)+0x60}, ${note:02X}`, `:1291`), and the 6502 engine re-dispatches
  every stream byte by range: `< $60` → note, `$60–$7F` → length, `>= $80` → command
  (`audio_engine.asm:213-219`). `docs/AUDIO_BYTECODE_SPEC.md` §3 states notes occupy
  `$00–$5F` and that "DPCM sample triggers are encoded as regular note bytes". A DPCM
  `note` of `$60` or higher (i.e. `sample_id >= 95`) is therefore misread as a Length or
  Engine command, desyncing the entire DPCM stream from that point — not just one wrong
  hit.
- **Evidence**: `note` cap for dpcm is 255 (`:1083-1085`), tone notes cap at 95 (`:1086`).
  The note byte is emitted positionally after the `$6X` length byte but the engine loops
  back through `@read_next` and re-dispatches it by range (`@is_note` requires `< $60`,
  `audio_engine.asm:215-217`). The direct-export path has no such limit (DPCM notes live in
  a dedicated `dpcm_note` byte table read by index, not dispatched), so the two paths
  diverge on the maximum supported `sample_id` (direct: 254; bytecode: 94).
- **Impact**: Latent. Requires a single song with >94 distinct packed DPCM samples, which
  is unreachable on any real NES PRG/DPCM ROM budget (each sample is multiple KB). No
  current input triggers it. Blast radius if reached: DPCM channel only, bytecode path only.
- **Related**: #67 (dpcm 95-clamp removal), spec §3, EXP-07/#83 (bytecode dispatch).
- **Suggested Fix**: Either clamp DPCM `note` to `0x5F` in the bytecode path (accepting the
  same collapse #67 removed, but only for the >94-sample edge), or — better — assert
  `sample_id < 95` and raise a clear `ValueError` (mirroring the instrument/bank-budget
  guards) so an impossible song fails loudly instead of emitting a stream that decodes to
  garbage. Document the 94-sample bytecode ceiling next to the `:1083` comment.

### EXP-2026-07-19-2: FamiStudio export uses direct `event[...]` subscripts where the CA65 path uses defensive `.get()`
- **Severity**: LOW
- **Dimension**: D7 Cross-Exporter Consistency
- **Location**: `exporter/exporter_famistudio.py:105-107`
- **Status**: NEW
- **Description**: For `pulse1/pulse2/triangle` frames the FamiStudio emitter reads
  `event['note']` and `event['volume']` via direct subscript. The CA65 emitter reads the
  same fields defensively (`frame_data.get('note', 0)`, `frame_data.get('volume', 0)`), and
  the DPCM branch here was already hardened to `.get()` in #82. A frame dict that is missing
  `note` or `volume` (which the CA65 path tolerates) raises `KeyError` from the FamiStudio
  path, so the two exporters disagree on what counts as a valid `frames` input.
- **Evidence**: `note = midi_note_to_famistudio(event['note'])` and
  `volume = min(15, event['volume'])` (`:105-107`) vs. `frame_data.get('pitch', 0)` /
  `.get('note', 0)` / `.get('volume', 0)` in `exporter_ca65.py:334-341`.
- **Impact**: Low and non-default: `generate_famistudio_txt` is not wired to any CLI
  subcommand (`--format` offers only `ca65`), and `NESEmulatorCore` always populates
  `note`/`volume`, so no current pipeline input hits the `KeyError`. It is a latent
  robustness/consistency gap reachable only via direct API use or a future producer that
  omits a key.
- **Related**: #82 (dpcm branch hardening in the same function), D7.
- **Suggested Fix**: Switch the tone-channel reads to `event.get('note', 0)` /
  `event.get('volume', 0)` to match the CA65 path's tolerance.

## Deduped against open issues / prior audits (noted, not counted)

These remain OPEN and relevant to the exporter surface; not re-reported as new:
- **#167 (NH-25, open)** — direct-path pulse control bytes omit the length-counter-halt
  flag the docs mandate. D2-adjacent; producer-side (`emulator_core`) but surfaces here.
- **#348 (NH-HW-2026-07-18-1, open)** — direct-export APU init never zeroes the DMC DAC
  ($4011). D2-adjacent.
- **#137 (TD-08, open)** — stale `; TODO: Insert actual .incbin` in the bytecode DPCM
  segment (`exporter_ca65.py:991`); real work is done by the DPCM packer. Doc/tech-debt.
- **#136 (TD-11, open)** — `export_direct_frames` monolith. Tech-debt, not correctness.
- **#302 (EXP-09, open)** — `exporter/compression.py` dead code. Tech-debt.

Closed issues re-verified as still-fixed: #78, #77, #80, #81, #82, #83, #79, #158, #298,
#163/NH-21, #72, #4, #67 (see Verification results table).

---
Suggested next step:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-07-19.md
```
