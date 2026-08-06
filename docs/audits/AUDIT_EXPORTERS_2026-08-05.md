# Exporters Audit — 2026-08-05

Scope: `exporter/exporter_ca65.py` (default CA65 path — both `export_direct_frames`
and the MMC3 macro-bytecode `export_tables_with_patterns`), `exporter/exporter_nsf.py`,
`exporter/exporter_famistudio.py`, and their consumers (`nes/project_builder.py`,
`nes/audio_engine.asm`, `main.py` export dispatch). Cross-checked against
`docs/AUDIO_BYTECODE_SPEC.md`, `docs/MACRO_USAGE_GUIDE.md`, and the mapper linker
configs (`mappers/mmc3.py`, `mappers/mmc1.py`, `mappers/base.py`).

This is again predominantly a fix-verification pass. Since the last exporter audit
(`AUDIT_EXPORTERS_2026-07-19.md`), only two commits touched `exporter/`:
`36348ce` (#361/#362/#363 — mapper auto-select export-mode-awareness, direct-DPCM
marker, capacity-gate extraction) and `7a2054d` (#364 — named triangle
linear-counter constant, dropped inert loudness scaling). Both were reviewed line
by line against their diffs and found correct and well-documented; no new bug
introduced. Every closed fix re-verified in the 2026-07-19 report was re-confirmed
again in current code (see table below), and the full exporter-relevant test suite
(`test_ca65_export.py`, `test_exporter_integration.py`, `test_famistudio_export.py`,
`test_nsf_export.py`, `test_nsf_integration.py`, `test_triangle_control_constant.py`,
`test_audio_fixes.py`, `test_mapper_capacity_fixes.py` — 142 tests total) passes.

## Summary

### Counts by severity
| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 0 |
| **Total**| **0** |

### Counts by dimension
| Dimension | Count |
|-----------|-------|
| D1 CA65 well-formedness / builder compat | 0 |
| D2 APU register serialization | 0 |
| D3 Pattern-vs-empty paths | 0 |
| D4 Byte-range safety | 0 (see dedup: #369 still open) |
| D5 Bytecode-spec conformance | 0 |
| D6 Macro emission | 0 |
| D7 Cross-exporter consistency | 0 (see dedup: #370 still open) |
| D8 Format-string / CLI choices | 0 |

### Three highest-impact findings
None. No new findings this pass. The default `python main.py input.mid out.nes`
CA65 path (both the empty-patterns direct emitter and the MMC3 macro-bytecode
emitter) remains clean: every emitted label and segment resolves against the
builder's linker config, APU register blocks are correct per-channel (including
the newly-named `TRIANGLE_CONTROL_ON` constant from #364), all byte operands are
guarded, and the bytecode matches `docs/AUDIO_BYTECODE_SPEC.md`. The two
previously-identified LOW findings (#369, #370) remain open and unfixed in code —
not re-reported here, see the dedup table below.

## Verification results (closed fixes re-confirmed in place)

| Dimension | Item | Result |
|-----------|------|--------|
| D1 | `.export`/`.import`/`.importzp` symbols all resolve: bytecode path exports `pulse1_sequence…dpcm_sequence`, `ntsc_period_low/high`, `triangle_period_low/high`, `instrument_table`, `channel_start_banks` (`exporter_ca65.py:1035-1039`); `nes/audio_engine.asm:4-11` imports exactly these. `.importzp ptr1, temp1, temp2, frame_counter` (`:1015`) matched by engine `.exportzp` (`audio_engine.asm:17`). Direct path `.importzp frame_counter, temp_ptr` (`:253`) matched by `project_builder.py` ZEROPAGE (`temp_ptr` `:331,334`; conditional `frame_counter` `:299-301,334`). `.import audio_init, audio_update` (`:1346`) matched by engine `.export audio_init, audio_update` (`:54`). | ✅ holds |
| D1 | Segments `CODE_8000`/`DPCM`/`BANK_00..59` all defined in MMC3 linker config; direct-export `RODATA_BANK_NN` segments defined in MMC1 config. | ✅ holds |
| D1 | Bank-overflow guard (`exporter_ca65.py:1290-1300`) raises `ValueError` on `next_bank > MAX_SEQUENCE_BANK` before emitting an undefined `BANK_NN` segment. | ✅ holds |
| D2 | Per-channel register blocks correct ($4000-03 / $4004-07 / $4008,$400A,$400B / $400C,$400E,$400F); no off-by-$4. `$4015`/`$4017` init present in both standalone reset (`:494-499`) and `init_music` (`:881-884`). | ✅ holds |
| D2 | **#364 (this sprint's new fix)** — triangle control byte is now `TRIANGLE_CONTROL_ON` (`0x80\|0x7F = 0xFF`, `:40-42`), a named linear-counter constant, replacing the inert-but-opaque `0x80 \| (volume*7)` loudness scaling. Volume 0 still maps to `$00` (silent). Matches the bytecode engine's fixed `$FF` write. Test `tests/test_triangle_control_constant.py` (37 lines, new) pins the exact value; `tests/test_audio_fixes.py` updated to match. | ✅ holds, newly verified |
| D2 | **#78** continuation-frame pitch uses per-channel table: `midi_note_to_timer_value(note, channel)` at both note-start (`:1170`) and continuation (`:1189`), both `channel`-qualified. | ✅ holds |
| D2 | **#81** NSF `export()`/`export_nsf()` raise `NotImplementedError` (`exporter_nsf.py:73-80`); `NSFHeader`/`NSFMacroPacker` have no live caller (grep clean). | ✅ holds |
| D3 | Empty-`patterns` path early-returns to `export_direct_frames` (`:1007-1008`). `references` appears only in the method signature/docstring (`:996,1003-1004`), never in the method body (grep confirmed clean). | ✅ holds |
| D4 | **#80** `_register_instrument` (`:940-958`) raises `ValueError` above 256 unique instruments. **#77** all four pitch/arp encode sites route through `_encode_macro_offset` (`:1172,1176,1191,1192`, grep-confirmed exhaustive). **#158** note clamped both ends (`:1117` >95→95, `:1119-1127` tone <24→24). **#298** clamp tally (`notes_clamped_high`/`notes_clamped_low`, `:1083-1084,1134-1140,1362`) fires on both boundaries with a printed warning. No `$87`/`CMD_DMC_LEVEL`/`$85` emission anywhere in the exporter (grep clean). | ✅ holds |
| D5 | Length+note encoding `(write_dur-1)+0x60` with `write_dur=min(rem,32)` (`:1285,1322`) → `$60–$7F`, matches spec §3. **#83** spec §3 documents `$FE CMD_BANK_JUMP` (sequence-level, `AUDIO_BYTECODE_SPEC.md:107`) as distinct from the in-macro `$FE` loop byte (§2.3, marked reserved); exporter (`:1302`) and engine (`@cmd_bank_jump`) agree. Channel/terminator order `pulse1,pulse2,triangle,noise,dpcm` + `$FF` matches §2.1 (`SEQUENCE_CHANNELS`, `:1256`). | ✅ holds |
| D6 | `instrument_table` rows emit Vol,Arp,Pitch,Duty in order (`:1226-1227`), built (`:1163`) and unpacked (`:1226`) consistently — no transposition. `macro_*_0 = ((0xFF,), id 0)` null/sustain macro seeded for all four kinds (`:1067-1074`) and emitted (`:1230-1235`). `_compress_macro` (`:960-994`) is sustain-only, never emits `$FE`. Macro dicts dedupe by tuple. | ✅ holds |
| D7 | **#82** `midi_note_to_famistudio` clamps octave to 0-7 (`exporter_famistudio.py:177`); dpcm branch recovers `sample_id` via `.get()` fallback from `note-1` (`:117-119`), no `KeyError`. FamiStudio iterates the same 5-channel list as CA65; `dpcm_sample_map` excluded (`:88,94`). | ✅ holds |
| D8 | **#79** `--format` `choices=['ca65']` (`main.py:1204`); `run_export` branches only on `"ca65"` (`:538`); no dead `nsftxt` branch. `run_config_validate` NSF load-address print (`:1430`) remains cosmetic-only (no live NSF consumer). | ✅ holds |

## New commits reviewed this pass (post 2026-07-19)

- **`36348ce`** (#361/#362/#363): Adds `BaseMapper.direct_export_capacity()` /
  `MMC3Mapper.direct_export_capacity()` and `MapperFactory.auto_select(direct=True)`
  so direct-export mapper selection ranks by MMC3's real ~6 KB fixed-bank budget
  instead of its 512 KB banked capacity. The only `exporter/` change is a new
  comment-only marker line (`"; Direct export DPCM (MMC3-only)"`,
  `exporter_ca65.py:231-232`) emitted when `frames.get('dpcm')` is truthy in the
  direct-export path — purely informational for `main.py:resolve_mapper` to
  recover mapper intent from a standalone `music.asm`; it does not alter any
  assembled byte and cannot break `ca65`/`ld65` (it's a `;`-prefixed line). No
  finding.
- **`7a2054d`** (#364): reviewed above (D2). No finding.

Both commits are mapper/capacity-domain fixes that only marginally touch the
exporter (a marker comment); the substantive logic lives in `mappers/` and is
better covered by `/audit-mappers`.

## Deduped against open issues / prior audits (noted, not counted)

Re-checked against current code and confirmed still unfixed / still open — not
re-reported as new:
- **#369 (EXP-2026-07-19-1, open, LOW)** — DPCM `note` in the macro-bytecode
  stream is still clamped only to `<= 255` (`exporter_ca65.py:1114-1116`), not to
  the engine's `$00-$5F` note-dispatch range. Unreachable in practice (requires
  >94 distinct packed DPCM samples on one song, beyond any real ROM budget). Code
  unchanged since the last audit.
- **#370 (EXP-2026-07-19-2, open, LOW)** — `exporter_famistudio.py:105-107` still
  reads `event['note']` / `event['volume']` via direct subscript rather than
  `.get()`, unlike the CA65 path and unlike the DPCM branch in the same function
  (already hardened by #82). Not CLI-reachable (`--format` offers only `ca65`).
  Code unchanged since the last audit.
- **#302 (EXP-09, open, LOW)** — `exporter/compression.py` dead code. Tech-debt,
  unchanged.
- **#167 (NH-25, open)** — direct-path pulse control bytes omit the
  length-counter-halt flag. Producer-side (`emulator_core`), D2-adjacent, not
  re-reported here.
- **#348 (NH-HW-2026-07-18-1, open)** — direct-export APU init never zeroes the
  DMC DAC ($4011). D2-adjacent, not re-reported here.
- **#137 (TD-08, open)** — stale `; TODO: Insert actual .incbin` comment in the
  bytecode DPCM segment (`exporter_ca65.py:1022`). Doc/tech-debt, unchanged.
- **#136 (TD-11, open)** — `export_direct_frames` monolith. Tech-debt, not
  correctness.

Closed issues re-verified as still-fixed this pass: #78, #77, #80, #81, #82, #83,
#79, #158, #298, #163/NH-21, #72, #4, #67, and newly **#364** (triangle constant,
verified for the first time in this report).

## Findings

None. No new findings in this audit cycle.

---
Suggested next step:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-08-05.md
```
