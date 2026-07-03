# Exporters Audit — 2026-07-03

Scope: `exporter/` output generators (CA65 macro-bytecode + direct-frame paths, NSF,
FamiStudio) per `.claude/commands/audit-exporters/SKILL.md`, cross-checked against
`docs/AUDIO_BYTECODE_SPEC.md`, `docs/MACRO_USAGE_GUIDE.md`, the shipped engine
`nes/audio_engine.asm`, and the consumer `nes/project_builder.py`. Severity floors from
`.claude/commands/_audit-severity.md`. Dedup against `gh issue list --state all` (306
issues) and all prior reports in `docs/audits/`, in particular
`docs/audits/AUDIT_EXPORTERS_2026-06-29.md` (four days prior, HEAD then was pre-sprint).

**Baseline re-verification**: a bug-fixing sprint between the two audits closed EXP-01
(#77), EXP-02 (#78), EXP-03 (#79), EXP-05 (#81), EXP-06 (#82), plus NH-16 (#158) and
D-09 (#72) which touch this file. I re-read the current code for every one of those
fixes (not just trusted the closed-issue label) — all seven hold at HEAD `9cfa0e2`. See
"Re-verified fixes" below for the evidence per fix. Two prior findings remain open and
unchanged: EXP-04 (#80, byte-range on `inst_id`/`loop_start`) and EXP-07 (#83, spec
doc-rot on `$FE`/`$87`) — confirmed still present, not re-counted.

## Summary

### Counts by severity
- CRITICAL: 0
- HIGH: 1 (new)
- MEDIUM: 1 (new)
- LOW: 1 (new)
- Existing / deduped, not re-counted: 6 (EXP-04 #80, EXP-07 #83, NH-21 #163, NH-22 #164,
  NH-23 #165, NH-25 #167, F-10 #23)

### Counts by dimension
- D1 (CA65 well-formedness/builder compat): 0 new (re-verified clean)
- D2 (APU register serialization): 0 new (re-verified clean; `ora #$08` on $4003/$4007/$400B confirmed intentional — see notes)
- D3 (pattern-vs-empty paths): 0 new (Existing #4, re-verified)
- D4 (byte-range safety): 1 new (EXP-08, cross-stage) + Existing #80 re-verified open
- D5 (bytecode-spec conformance): 0 new (Existing #83 re-verified open)
- D6 (macro emission): 0 new (re-verified clean; NH-21 #163 cross-ref only, not duplicated)
- D7 (cross-exporter consistency): 1 new (EXP-09, dead code)
- D8 (format-string / CLI mismatch): 0 new (re-verified clean)
- Cross-cutting (note clamp diagnostics): 1 new (EXP-10)

### Three highest-impact findings
1. **EXP-08 (HIGH)** — `arranger/pipeline_integration.py:281` still clamps DPCM
   `sample_id` with the exact `min(95, sample_id + 1)` formula that #67/D-04 fixed at
   the other two producers (`nes/emulator_core.py`, `exporter/exporter_ca65.py`). Any
   song run with `--arranger` and more than 94 distinct DPCM samples silently plays the
   wrong drum for every `sample_id >= 94` — the #67 bug is still live behind the
   arranger front-end.
2. **EXP-10 (MEDIUM)** — the exporter's tone-channel note clamps (`note > 95 → 95`,
   `0 < note < 24 → 24`, `exporter_ca65.py:987-997`) are silent: no counter, log, or
   warning anywhere in the pipeline records that a note was altered. A song with
   melodic content above B6 or below C1 plays a different, unannounced pitch.
3. **EXP-09 (LOW)** — `exporter/compression.py`'s `CompressionEngine` and
   `BaseExporter.compress_channel_data`/`decompress_channel_data` have unit test
   coverage but zero production caller; dead code in the exporter's own scope.

---

## Findings

### EXP-08: Arranger's DPCM sample_id clamp still collapses high ids to one wrong drum (misses the #67/D-04 fix)
- **Severity**: HIGH
- **Dimension**: D4 (byte-range safety) — cross-stage producer/consumer contract
- **Spec ref**: `docs/APU_DMC_REFERENCE.md` §2 (sample selection is by address/length
  table index, not a MIDI-note-shaped value); consumer contract documented at
  `exporter/exporter_ca65.py:979-986` ("DPCM channel's `note` is sample_id + 1 ... bounded
  only by the single-byte frame format (<=255), not the 0-95 tone-note range").
- **Location**: `arranger/pipeline_integration.py:276-283`, specifically `:281`
  (`'note': min(95, data['sample'] + 1)`).
- **Status**: Regression of #67 (D-04) — more precisely, an incomplete fix: #67's fix
  commit (`fb70f56`) updated `nes/emulator_core.py:124` and `exporter/exporter_ca65.py`'s
  clamp to a 255 ceiling and left an explicit code comment recording the contract, but
  never touched `arranger/pipeline_integration.py`, which independently builds the same
  `output['dpcm'][frame]` shape for the `--arranger` front-end. The original issue's own
  "Completeness Checks" only list `emulator_core` and `exporter_ca65` as siblings
  checked — `arranger/pipeline_integration.py` was not on that list and was missed.
- **Description**: `arrange_for_nes` (the `--arranger` entry point, wired at
  `main.py:514` via `from arranger import arrange_for_nes`) builds its own DPCM frame
  dict independently of `nes/emulator_core.py`. Its conversion clamps
  `note = min(95, data['sample'] + 1)`, which is exactly the pre-#67 formula. The
  exporter (`exporter_ca65.py:979-986`) now trusts frames-producers to hand it
  `note = sample_id + 1` unclamped up to 255 and applies its own ceiling of 255 only —
  it has no way to detect that a producer already pre-clamped the value at 95. Any
  `data['sample'] >= 94` therefore arrives at the exporter as `note = 95` regardless of
  the real sample id, and the exporter faithfully emits `.byte $XX, $5F` — the engine's
  `@cmd_dpcm_play` (`audio_engine.asm:231-256`) then looks up `dpcm_bank_table[94]` /
  `dpcm_pitch_table[94]` / etc. for every one of those hits, playing one fixed sample
  instead of whichever distinct drum the song actually specified.
- **Evidence**:
  ```python
  # arranger/pipeline_integration.py:276-283
  for frame, data in frames['dpcm'].items():
      output['dpcm'][frame] = {
          'note': min(95, data['sample'] + 1),
          'volume': 15,
      }
  ```
  Compare `nes/emulator_core.py:124` (`"note": min(255, sample_id + 1)`, fixed by #67)
  and the exporter's own comment at `exporter_ca65.py:979-984` describing the contract
  this line violates. `grep -rn "min(95" arranger/ nes/ exporter/` returns only this one
  remaining call site.
- **Impact**: Silent wrong-drum substitution — the exact D-04 impact ("Any song using
  more than ~94 distinct DPCM samples ... silently maps every high-id hit to a single
  wrong sample. Audible drum substitution with no warning") — but now scoped to the
  `--arranger` pipeline mode specifically. `--arranger` is a documented, supported
  top-level flag (`CLAUDE.md`, `main.py --help`), so any user relying on it for a
  drum-heavy song with a large DPCM sample palette hits this. Blast radius: DPCM/noise
  channel, `--arranger` front-end only (the default/legacy front-end via
  `track_mapper.py` + `emulator_core.py` is unaffected — it uses the already-fixed
  `min(255, ...)`).
- **Related**: #67/D-04 (original bug + partial fix); #9/NH-01, #84/ARR-01 (other
  DPCM-contract mismatches between arranger and exporter — same root cause class: the
  arranger's independent frame-shaping code drifting from the emulator/exporter
  contract).
- **Suggested Fix**: Change `arranger/pipeline_integration.py:281` to
  `'note': min(255, data['sample'] + 1)`, matching `nes/emulator_core.py:124` and the
  exporter's stated contract. Consider factoring the DPCM-note encoding
  (`sample_id + 1`, capped at 255) into one shared helper both front-ends call, so a
  future third producer can't silently reintroduce this class of bug again.

### EXP-10: Tone-channel note clamps in the exporter have no log/counter — silent pitch change on out-of-range notes
- **Severity**: MEDIUM
- **Dimension**: Cross-cutting (D4 byte-range safety / diagnostics gap)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` §3 "Note Range ($00-$5F)" — the note byte
  is hard-capped at 95 by the bytecode format itself (values $60+ are Length/other
  commands), so *some* clamp is mandatory and correct; the gap is the missing diagnostic,
  not the clamp itself.
- **Location**: `exporter/exporter_ca65.py:987-997` (`elif note > 95: note = 95` /
  `elif channel != 'noise' and 0 < note < 24: note = 24`).
- **Status**: NEW
- **Description**: Per the SKILL's own verification note on the #158/NH-16 fix, a
  clamped note should be "at least logged/counted somewhere upstream." It is not.
  Neither `exporter_ca65.py` nor any upstream stage (`nes/emulator_core.py`,
  `arranger/pipeline_integration.py`, `tracker/track_mapper.py`) counts, logs, or warns
  when a note gets clamped at either boundary. A melodic line that goes above MIDI note
  95 (B6) or, for tone channels, below 24 (C1) is silently re-pitched with zero
  indication to the user — the ROM plays a different note than the MIDI file specified,
  and nothing in the CLI output, `--verbose` trace, or any diagnostic tool
  (`debug/rom_diagnostics.py`, `debug/check_rom.py`) surfaces it.
- **Evidence**:
  ```python
  elif note > 95:
      note = 95
  elif channel != 'noise' and 0 < note < 24:
      note = 24
  ```
  `grep -rn "out of range\|clamped\|clamp_count\|notes_clamped" nes/ exporter/ arranger/
  tracker/ main.py` turns up no counter/log tied to this clamp (the only other clamp-like
  logging is unrelated velocity clamping in `nes/emulator_core.py`).
- **Impact**: Any song with content above B6 (fairly common for piccolo/flute/high lead
  lines, or a track transposed up) or, for tone channels, below C1 plays wrong,
  unannounced notes — a "MEDIUM, silent, no workaround without inspecting output audio"
  case per the severity rubric's clamp-diagnostics guidance. Not CRITICAL because the
  clamp is bytecode-format-mandated (there is no valid alternative encoding to fall back
  to) and it does not corrupt other channels/data — it only mis-pitches the affected
  notes.
- **Related**: #158/NH-16 (the low-end clamp's *value* was fixed there; this finding is
  about the *lack of any diagnostic* on both clamp directions, which was out of scope for
  that fix). #41/NH-11 (a different, unused method's inconsistent range guard — not the
  same code path).
- **Suggested Fix**: Have `export_tables_with_patterns` accumulate a per-song count of
  clamped notes (both directions) and print a one-line summary (e.g.
  `"⚠️  12 notes clamped to NES tone range (24-95); pitch may differ from the MIDI file"`)
  at the end of export, similar to how other lossy pipeline steps already report their
  own stats.

### EXP-09: `exporter/compression.py`'s `CompressionEngine` and `BaseExporter` compress/decompress helpers are dead code
- **Severity**: LOW
- **Dimension**: D7 (cross-exporter consistency) — dead code in the exporter's own scope
- **Spec ref**: none (tech-debt observation, not a spec-conformance issue).
- **Location**: `exporter/compression.py:1-254` (the whole `CompressionEngine` class);
  `exporter/base_exporter.py:12-46` (`compress_channel_data`/`decompress_channel_data`).
- **Status**: NEW
- **Description**: `BaseExporter.__init__` instantiates a `CompressionEngine`, and
  `compress_channel_data`/`decompress_channel_data` wrap its RLE+delta
  `compress_pattern`/`decompress_pattern` methods. None of the three live exporters
  (`CA65Exporter`, `NSFExporter`, `FamiStudioExporter`) — nor `main.py`, nor any other
  production module — ever call `compress_channel_data`, `decompress_channel_data`, or
  `CompressionEngine` directly. `export_tables_with_patterns`/`export_direct_frames` do
  their own inline compression (`_compress_macro`, the direct frame tables); this
  RLE/delta engine is entirely unused at runtime. It is exercised only by
  `tests/test_compression.py`, `tests/test_compression_integration.py`, and
  `tests/test_exporter_integration.py` — tested code with no caller. (This is distinct
  from `tracker/pattern_detector.py`'s unrelated `PatternCompressor` class, which *is*
  live on the default pipeline via `ParallelPatternDetector` — grepped and confirmed
  these are two separate classes with no relationship; a recent `docs/audits/
  AUDIT_PATTERNS_2026-07-03.md` reference to "`CompressionEngine`" in that context
  appears to be a naming mix-up with `PatternCompressor`, not evidence this file is used.)
- **Evidence**: `grep -rn "compress_channel_data\|decompress_channel_data\|CompressionEngine"
  --include=*.py .` (excluding `venv/`) matches only `exporter/compression.py`,
  `exporter/base_exporter.py`, and the three test files above — no exporter or `main.py`
  call site.
- **Impact**: None functionally (dead code, not reachable from any pipeline path).
  Maintenance/confusion cost: a future contributor could reasonably assume this is the
  live compression path for exported channel data (it is the only "compression" concept
  living in `exporter/`) and modify it expecting an effect on ROM output.
- **Related**: none.
- **Suggested Fix**: Either wire it in (if RLE/delta channel-data compression is still a
  planned feature) or remove `CompressionEngine`/`compress_channel_data`/
  `decompress_channel_data` and their dedicated tests, noting the removal in
  `docs/ROADMAP.md` if it was ever an advertised feature.

---

## Re-verified fixes (from `AUDIT_EXPORTERS_2026-06-29.md`, all confirmed holding)

- **EXP-01 (#77, macro `$FE`/`$FF` collision)**: `_encode_macro_offset`
  (`exporter_ca65.py:71-86`) clamps to `[-128,127]` and snaps `-1→0x00`, `-2→0xFD`; both
  pitch/arp call sites (note-start `:1031-1032`, continuation `:1047-1048`) route through
  it. No raw `& 0xFF` formatting of a signed offset remains.
- **EXP-02 (#78, triangle continuation pitch)**: both the note-start (`:1029`) and
  continuation (`:1045`) `midi_note_to_timer_value` calls now pass `channel`; the
  continuation call site carries an explicit regression comment citing #78.
- **EXP-03 (#79, `--format nsf` dead dispatch)**: `main.py:814`
  `add_argument('--format', choices=['ca65'], default='ca65')` — `nsf` removed from
  `choices` entirely; `run_export` only branches on `"ca65"`.
- **EXP-05 (#81, non-playable NSF)**: `NSFExporter.export()`/`export_nsf()`
  (`exporter_nsf.py:74-81`) unconditionally `raise NotImplementedError(...)` citing #81;
  the old JSON-serialization/hand-assembled play routine is gone. `NSFHeader`/
  `NSFMacroPacker` remain as documented, inert scaffolding with no caller.
- **EXP-06 (#82, FamiTracker/FamiStudio channel & octave bugs)**: the old
  `exporter/exporter.py`/`pattern_exporter.py` FamiTracker-text path no longer exists in
  the repo (removed per #101). `exporter_famistudio.py`'s `midi_note_to_famistudio`
  clamps `octave = max(0, min(7, (note // 12) - 1))`; the dpcm branch falls back to
  `event.get('note', 1) - 1` when `sample_id` is absent (no more `KeyError`).
- **NH-16 (#158, sub-C1 pitch macro wrap)**: `midi_note_to_timer_value` clamps
  `midi_note = max(24, min(midi_note, 119))`; the bytecode-stream note is separately
  floored to 24 for tone channels (`:989-997`), noise excluded.
- **D-09 (#72, dead `$87 CMD_DMC_LEVEL` emitter)**: `grep -n "CMD_DMC_LEVEL\|\$87"
  exporter/exporter_ca65.py` returns nothing — the emitter is gone from the exporter (the
  engine's unreachable handler is separate, already tracked as dead code elsewhere).

## Existing findings re-confirmed open (not re-counted)

- **EXP-04 (#80)** — `inst_id` (`:1164`, unbounded `instruments[inst] = len(...)`) and
  `loop_start` (`_compress_macro:857-859`, emitted via the generic `:02X` formatter at
  `:1092`) still have no upper-bound guard. Confirmed unchanged from the 2026-06-29
  report.
- **EXP-07 (#83)** — `docs/AUDIO_BYTECODE_SPEC.md` §3 still lists `$84`/`$85` and omits
  `$87`/the sequence-level `$FE` bank-jump that the exporter (`:1152`) and engine
  (`audio_engine.asm:259-276`) both actually implement and agree on. Doc-rot only, no
  runtime effect — confirmed unchanged.
- **NH-21 (#163)** — cross-referenced, not duplicated: `_compress_macro`'s loop encoding
  (`[0xFE, loop_start]`) is emitted correctly per the spec's data-structure rules (D6), but
  `EVAL_MACRO` (`audio_engine.asm:58-88`) only checks `cmp #$FF` and never decodes `$FE` —
  confirmed by re-reading the macro: a loop-compressed macro is read as raw data (`$FE` =
  254) instead of looping. This is an engine-decode bug (NH-21's territory), not an
  exporter emission bug; re-confirmed the emission side is correct.
- **NH-22 (#164)**, **NH-23 (#165)**, **NH-25 (#167)**, **F-10 (#23)** — spot-checked, all
  still reproduce as described in their filed issues; no change in this file since.

## Methodology notes (disproved candidates)

- **D2 `ora #$08` on `$4003`/`$4007`/`$400B`**: initially flagged as a possible
  length-counter-load-index bug. Traced the resulting index (L=00001, index 1) against
  the real NES length-lookup table (index 1 = 254) — 254 half-frames ≈ 2.1 s, matching
  the already-filed NH-25 (#167) description of "index 1 (~2.1s via `ora #$08`)".
  Deliberate choice to arm a long hardware length-counter safety net, not a bug — the
  halt-flag gap NH-25 already covers is the real (LOW) issue here.
- **D2 `$4017` init value `$40`**: `docs/APU_FRAME_COUNTER_REFERENCE.md` §4 explicitly
  recommends "Writing `$40` (`%01000000`) sets 4-step mode, IRQ disabled" — the value is
  correct. The stale inline comment ("Frame counter mode 1") mislabeling 4-step as
  "mode 1" is already tracked as NH-22 (#164); not re-filed.
- **D6 instrument-tuple order**: `(vol_macros[v_seq], arp_macros[a_seq],
  pitch_macros[p_seq], duty_macros[d_seq])` built at `:1023` and unpacked
  `v_id, a_id, p_id, d_id = inst` at `:1084` in the same order — no transposition.
  Disproved as a candidate finding.
- **D1 label/segment cross-check**: `.importzp ptr1, temp1, temp2, frame_counter`
  (`:885`) matches `.exportzp ptr1, temp1, temp2, frame_counter`
  (`audio_engine.asm:16`); `.import audio_init, audio_update` (`:1180`) matches
  `.export audio_init, audio_update` (`audio_engine.asm:53`); `BANK_00..59` segments
  match `MMC3Mapper.SWAP_BANK_COUNT = 60` and the `MAX_SEQUENCE_BANK` guard
  (`:1099-1151`) raises before exceeding it. No new D1 finding.
- **D6/D4 DPCM instrument macros**: the exporter builds a full vol/arp/pitch/duty
  instrument tuple for DPCM channel events too (wasteful — DPCM has no macro-driven
  volume/pitch), but confirmed the engine's `@is_note` handler
  (`audio_engine.asm:~330-336`, `cpx #4 / bne :+ / jmp @write_dpcm`) branches straight to
  `@write_dpcm` before any macro evaluation for the DPCM channel (x=4), so the
  unnecessary `CMD_INSTRUMENT` byte is harmless (2 wasted bytes per instrument change,
  no playback effect). Not filed — cosmetic byte waste below the LOW bar for a new
  finding; folded into this note for future reference.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-07-03.md
```
