# Exporters Audit — 2026-08-06

Scope: `exporter/exporter_ca65.py` (default CA65 path — both `export_direct_frames`
and the MMC3 macro-bytecode `export_tables_with_patterns`), `exporter/exporter_nsf.py`,
`exporter/exporter_famistudio.py`, and their consumers (`nes/project_builder.py`,
`nes/audio_engine.asm`, `main.py` export dispatch). Cross-checked against
`docs/AUDIO_BYTECODE_SPEC.md`, `docs/MACRO_USAGE_GUIDE.md`, and the mapper linker
configs (`mappers/mmc3.py`, `mappers/mmc1.py`, `mappers/base.py`).

Since the last exporter audit (`AUDIT_EXPORTERS_2026-08-05.md`, 0 findings), exactly
one commit touched `exporter/`: `20f627e` (#136 partial, #137, #202 — #202 lives in
`dpcm_sampler/`, out of this audit's scope). The `exporter/` portion of that commit is
an extract-method refactor of `export_direct_frames`: 8 new per-channel emitter methods
(`_emit_pulse_or_triangle_table`, `_emit_noise_table`, `_emit_dpcm_table`,
`_emit_pulse1_proc`, `_emit_pulse2_proc`, `_emit_triangle_proc`, `_emit_noise_proc`,
`_emit_dpcm_proc`) plus a comment fix replacing the stale `; TODO: Insert actual
.incbin statements` line (#137/TD-08, closed) with an accurate explanation of why the
`DPCM` segment is deliberately left empty. This audit specifically re-derived the
refactor's "byte-for-byte identical" claim line-by-line against the pre-refactor
version (git diff `20f627e` on `exporter/exporter_ca65.py`) rather than trusting the
commit message, since extract-method refactors are exactly where subtle bugs
(parameter-order swaps, closure-capture mistakes, dropped lines) creep in.

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
None. The default `python main.py input.mid out.nes` CA65 path (both the
empty-patterns direct emitter and the MMC3 macro-bytecode emitter) remains clean.
The one substantive change since the last audit — extracting 8 per-channel emitter
methods out of `export_direct_frames` — was verified line-by-line to be a pure
code-motion: every extracted method's parameter list matches its call site exactly,
the `_ensure_segment`/`_emit_byte_table` closures (which mutate the shared
`current_segment`/`lines`/`table_bank` state) are passed in unchanged rather than
duplicated, and no line of emitted-string logic was altered in the move. The
project's own golden-byte tests (`tests/test_ca65_export.py::test_pulse1_sequence_golden_bytes`,
`test_ntsc_period_low_golden_bytes`) and the 10 new isolated unit tests for the
extracted methods (`tests/test_ca65_export.py:1233+`, e.g.
`test_emit_pulse_or_triangle_table_pulse1`,
`test_emit_pulse_or_triangle_table_triangle_uses_gate_not_volume`,
`test_emit_noise_table_silent_frame_is_zero`) all pass, corroborating the "no
behavior change" claim.

## Refactor verification detail (#136 partial, extract-method pass)

| Check | Result |
|-------|--------|
| `_emit_pulse_or_triangle_table(self, lines, channel_name, channel_data, max_frame, ensure_segment)` call site `self._emit_pulse_or_triangle_table(lines, channel_name, all_channels[channel_name], max_frame, _ensure_segment)` (`:744`) | Argument order/count matches signature exactly. |
| `_emit_noise_table(self, lines, channel_data, max_frame, emit_byte_table)` call site `self._emit_noise_table(lines, all_channels['noise'], max_frame, _emit_byte_table)` (`:747`) | Matches. |
| `_emit_dpcm_table(self, lines, channel_data, max_frame, emit_byte_table)` call site (`:750`) | Matches. |
| `_emit_pulse1_proc`/`_emit_pulse2_proc`/`_emit_triangle_proc`/`_emit_noise_proc`/`_emit_dpcm_proc` all take `(self, lines, mapper, table_bank, bank_size)`; call sites (`:915,918,921,924,927`) | All match; no transposition of `mapper`/`table_bank`/`bank_size`. |
| Closures `_ensure_segment`/`_emit_byte_table` still defined once inside `export_direct_frames` (`:718-731`) over the same mutable `current_segment = ['']` cell (`:716`) and `table_bank` dict (`:708-710`), passed by reference into the extracted methods rather than re-implemented | Confirmed — bank-packed segment interleaving across channels is unchanged, since the same closure instances (not copies) are invoked from inside the extracted methods. |
| Body text of each extracted method vs. the pre-refactor inline block (diff `20f627e`) | Identical line-for-line (only indentation/`self.` prefix changes from becoming a method); pulse1/pulse2's historical comment asymmetry (pulse1 has extra inline comments pulse2 lacks) preserved verbatim as the commit message claims, not "fixed" into false symmetry that would have altered emitted bytes. |
| `.segment "DPCM"` block comment (`:1088-1094`) | Old stale `; TODO: Insert actual .incbin statements for DPCM files here` replaced with an accurate explanation citing `DpcmPacker` and the `optional = yes` linker config; this is a comment-only change (`;`-prefixed), cannot affect assembly. |
| Full exporter test suite | `test_ca65_export.py`, `test_exporter_integration.py`, `test_famistudio_export.py`, `test_nsf_export.py`, `test_nsf_integration.py`, `test_triangle_control_constant.py`, `test_audio_fixes.py` — 129 tests, all pass. |

No regression found. #136 remains open only for its `run_full_pipeline` half
(tracked separately as #406, `main.py`-scoped, out of this audit's file scope).
#137 is fully closed — the DPCM-segment comment now accurately describes the
packer-owned bank layout instead of implying missing work.

## Verification results (closed fixes re-confirmed in place, unchanged from 2026-08-05)

| Dimension | Item | Result |
|-----------|------|--------|
| D1 | `.export`/`.import`/`.importzp` symbols all resolve: bytecode path exports `pulse1_sequence…dpcm_sequence`, `ntsc_period_low/high`, `triangle_period_low/high`, `instrument_table`, `channel_start_banks`; `nes/audio_engine.asm` imports exactly these. `.importzp ptr1, temp1, temp2, frame_counter` (`:1083`) matched by engine `.exportzp`. Direct path `.importzp frame_counter, temp_ptr` (`:656`) matched by `project_builder.py` ZEROPAGE. `.import audio_init, audio_update` (`:1419`) matched by engine `.export audio_init, audio_update`. | ✅ holds |
| D1 | Segments `CODE_8000`/`DPCM`/`BANK_00..59` all defined in MMC3 linker config; direct-export `RODATA_BANK_NN` segments defined in MMC1 config. | ✅ holds |
| D1 | Bank-overflow guard raises `ValueError` on `next_bank > MAX_SEQUENCE_BANK` before emitting an undefined `BANK_NN` segment. | ✅ holds |
| D2 | Per-channel register blocks correct ($4000-03 / $4004-07 / $4008,$400A,$400B / $400C,$400E,$400F); no off-by-$4. `$4015`/`$4017` init present in both standalone reset and `init_music`. | ✅ holds |
| D2 | **#364** — triangle control byte is `TRIANGLE_CONTROL_ON` (`0x80\|0x7F = 0xFF`, `:40-42`), a named linear-counter constant; volume 0 maps to `$00` (silent). | ✅ holds |
| D2 | **#78** continuation-frame pitch uses per-channel table via `midi_note_to_timer_value(note, channel)` at both note-start and continuation call sites, both `channel`-qualified. | ✅ holds |
| D2 | **#81** NSF `export()`/`export_nsf()` raise `NotImplementedError`; `NSFHeader`/`NSFMacroPacker` have no live caller (grep clean). | ✅ holds |
| D3 | Empty-`patterns` path early-returns to `export_direct_frames`. `references` appears only in the method signature/docstring, never in the method body (grep confirmed clean). | ✅ holds |
| D4 | **#80** `_register_instrument` raises `ValueError` above 256 unique instruments. **#77** all four pitch/arp encode sites route through `_encode_macro_offset` (grep-confirmed exhaustive). **#158** note clamped both ends (>95→95, tone <24→24). **#298** clamp tally fires on both boundaries with a printed warning. No `$87`/`CMD_DMC_LEVEL`/`$85` emission anywhere in the exporter (grep clean). | ✅ holds |
| D5 | Length+note encoding `(write_dur-1)+0x60` with `write_dur=min(rem,32)` → `$60–$7F`, matches spec §3. **#83** spec §3 documents `$FE CMD_BANK_JUMP` (sequence-level) as distinct from the in-macro `$FE` loop byte (§2.3, reserved); exporter and engine (`@cmd_bank_jump`) agree. Channel/terminator order `pulse1,pulse2,triangle,noise,dpcm` + `$FF` matches §2.1. | ✅ holds |
| D6 | `instrument_table` rows emit Vol,Arp,Pitch,Duty in order, built and unpacked consistently — no transposition. `macro_*_0 = ((0xFF,), id 0)` null/sustain macro seeded for all four kinds. `_compress_macro` is sustain-only, never emits `$FE`. Macro dicts dedupe by tuple. | ✅ holds |
| D7 | **#82** `midi_note_to_famistudio` clamps octave to 0-7 (`exporter_famistudio.py:177`); dpcm branch recovers `sample_id` via `.get()` fallback from `note-1` (`:117-119`), no `KeyError`. FamiStudio iterates the same 5-channel list as CA65. | ✅ holds |
| D8 | **#79** `--format` `choices=['ca65']` (`main.py:1273`); `run_export` branches only on `"ca65"` (`main.py:662`); no dead `nsftxt` branch. | ✅ holds |

## Deduped against open issues / prior audits (noted, not counted)

Re-checked against current code and confirmed still unfixed / still open — not
re-reported as new:
- **#369 (EXP-2026-07-19-1, open, LOW)** — DPCM `note` in the macro-bytecode
  stream is still clamped only to `<= 255`, not to the engine's `$00-$5F`
  note-dispatch range. Unreachable in practice (requires >94 distinct packed DPCM
  samples on one song). Code unchanged since the last audit.
- **#370 (EXP-2026-07-19-2, open, LOW)** — `exporter_famistudio.py` still reads
  `event['note']` / `event['volume']` via direct subscript rather than `.get()`
  in the non-dpcm branch, unlike the CA65 path. Not CLI-reachable (`--format`
  offers only `ca65`). Code unchanged since the last audit.
- **#302 (EXP-09, closed)** — `exporter/compression.py` dead code, removed.
- **#167 (NH-25, closed)** — direct-path pulse control bytes now set the
  length-counter-halt flag; confirmed by the current commit's investigation
  (already fixed by `cb2a8ac`, issue was simply left open).
- **#348 (closed)** — direct-export APU init zeroes the DMC DAC ($4011).
- **#137 (TD-08, closed this cycle)** — stale `; TODO: Insert actual .incbin`
  comment replaced with an accurate explanation. Re-verified above.
- **#136 (TD-11, closed for the exporter half this cycle)** — `export_direct_frames`
  extract-method refactor landed and was verified byte-for-byte identical (see
  refactor verification table above). The `run_full_pipeline` half is tracked
  separately as **#406** (`main.py`-scoped, not this file).

Closed issues re-verified as still-fixed this pass: #78, #77, #80, #81, #82, #83,
#79, #158, #298, #163/NH-21, #72, #4, #67, #364, #167, #348, and newly **#137**,
**#136** (exporter half).

## Findings

None. No new findings in this audit cycle. The single commit touching `exporter/`
since the last audit was a verified-safe extract-method refactor plus a
comment-only fix.

---
Suggested next step:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-08-06.md
```
