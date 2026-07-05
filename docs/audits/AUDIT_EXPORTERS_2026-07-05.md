# Exporters Audit — 2026-07-05

Scope: `exporter/` output generators (CA65 macro-bytecode + direct-frame paths, NSF,
FamiStudio) per `.claude/commands/audit-exporters/SKILL.md`, cross-checked against
`docs/AUDIO_BYTECODE_SPEC.md`, `docs/MACRO_USAGE_GUIDE.md`, the shipped engine
`nes/audio_engine.asm`, the frame producers (`nes/emulator_core.py`,
`nes/envelope_processor.py`, `arranger/`), and the consumer `nes/project_builder.py`.
Severity floors from `.claude/commands/_audit-severity.md`.

Dedup sources: the pre-fetched open-issue snapshot at `/tmp/audit/issues.json` (36 open
issues) and every prior report in `docs/audits/`, in particular
`docs/audits/AUDIT_EXPORTERS_2026-07-03.md` (two days prior). Per skill instructions, no
`gh issue list` was re-run and no issues were created.

**Baseline re-verification.** Since the 2026-07-03 report, a further bug-fixing sprint
landed three exporter-relevant commits, which I re-read at HEAD rather than trusting the
labels:

- `b7c99c8` "guard single-byte bytecode operands and correct stale spec doc (#80, #83)"
  — closes **EXP-04 (#80)** and **EXP-07 (#83)**, the only two findings the 2026-07-03
  report left open.
- `60522b5` "…arranger DPCM clamp…(#195, #196, #197)" — closes **EXP-08**, the HIGH the
  2026-07-03 report opened (`arranger/pipeline_integration.py` DPCM `min(95, …)` →
  `min(255, …)`).
- `b49a648` "dense per-song DPCM sample id remap…(#200, #201)" — narrows the DPCM
  sample-id collision surface upstream; no exporter regression introduced.

Every prior re-verified fix (EXP-01 #77, EXP-02 #78, EXP-03 #79, EXP-05 #81, EXP-06 #82,
NH-16 #158, D-09 #72) still holds at HEAD. The two findings the 2026-07-03 report opened
as new that were *not* addressed by the sprint — **EXP-10** (silent note clamp) and
**EXP-09** (dead `compression.py`) — remain present, re-confirmed below.

## Summary

### Counts by severity
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 1 (EXP-10, re-confirmed open from 2026-07-03; not a new regression)
- LOW: 1 (EXP-09, re-confirmed open from 2026-07-03)
- **Genuinely new this cycle: 0**
- Deduped / already tracked, not re-counted: EXP-04 (#80, now fixed), EXP-07 (#83, now
  fixed), EXP-08 (now fixed), `is_midi_velocity` dead code (Existing #165/NH-23),
  NH-25 (#167), NH-21 (#163).

### Counts by dimension
- D1 (CA65 well-formedness / builder compat): 0 new (re-verified clean)
- D2 (APU register serialization): 0 new (independently re-verified clean)
- D3 (pattern-vs-empty paths): 0 new (#4 docstring re-verified accurate)
- D4 (byte-range safety): 0 new — **EXP-04 (#80) now fixed** (`_register_instrument`
  raises past 256 instruments; `_compress_macro` skips loop candidates with
  `loop_start > 0xFF`)
- D5 (bytecode-spec conformance): 0 new — **EXP-07 (#83) now fixed** (spec §3 rewritten)
- D6 (macro emission): 0 new (re-verified clean)
- D7 (cross-exporter consistency): 1 re-confirmed (EXP-09 dead code); EXP-08 now fixed
- D8 (format-string / CLI mismatch): 0 new (re-verified clean)
- Cross-cutting: 1 re-confirmed (EXP-10 clamp diagnostics)

### Three highest-impact findings
1. **EXP-10 (MEDIUM, re-confirmed open)** — the exporter's tone-channel note clamps
   (`note > 95 → 95`, `0 < note < 24 → 24`, `exporter_ca65.py:1023-1033`) are still
   silent: no counter, log, or warning anywhere records that a note was re-pitched. A
   song with content above B6 or below C1 plays altered, unannounced notes.
2. **EXP-09 (LOW, re-confirmed open)** — `exporter/compression.py`'s `CompressionEngine`
   and `BaseExporter.compress_channel_data`/`decompress_channel_data` remain dead code:
   tested but with zero production caller.
3. *(No third finding — no new HIGH/MEDIUM surfaced this cycle.)*

---

## Findings

### EXP-10: Tone-channel note clamps in the exporter have no log/counter — silent pitch change on out-of-range notes
- **Severity**: MEDIUM
- **Dimension**: Cross-cutting (D4 byte-range safety / diagnostics gap)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` §3 "Note Range ($00-$5F)" — the note byte
  is hard-capped at 95 by the bytecode format (values $60+ are Length/other commands),
  so *some* clamp is mandatory and correct; the gap is the missing diagnostic, not the
  clamp itself.
- **Location**: `exporter/exporter_ca65.py:1020-1033` (the `if channel == 'dpcm' … elif
  note > 95: note = 95 … elif channel != 'noise' and 0 < note < 24: note = 24` block).
- **Status**: Existing (prior report `docs/audits/AUDIT_EXPORTERS_2026-07-03.md`, EXP-10,
  reported NEW; re-confirmed still present at HEAD — not in the pre-fetched open-issue
  snapshot, so no GitHub issue number is known).
- **Description**: Per the SKILL's verification note on the #158/NH-16 fix, a clamped note
  should be "at least logged/counted somewhere upstream." It still is not. Neither
  `exporter_ca65.py` nor any upstream stage (`nes/emulator_core.py`,
  `arranger/pipeline_integration.py`, `tracker/track_mapper.py`) counts, logs, or warns
  when a note is clamped at either boundary. A melodic line above MIDI note 95 (B6) or,
  for tone channels, below 24 (C1) is silently re-pitched with zero indication to the
  user — no CLI output, `--verbose` trace, or diagnostic tool
  (`debug/rom_diagnostics.py`, `debug/check_rom.py`) surfaces it.
- **Evidence**:
  ```python
  # exporter/exporter_ca65.py
  if channel == 'dpcm':
      if note > 255:
          note = 255
  elif note > 95:
      note = 95
  elif channel != 'noise' and 0 < note < 24:
      note = 24
  ```
  `grep -rn "clamp\|out of range\|notes_clamped\|warn" exporter/exporter_ca65.py` returns
  only explanatory comments (`:1016`, `:1026`, `:1029`, `:1032`) — no counter or log tied
  to this clamp. The two commits that touched this region since the last audit
  (`421c01f` #158/#159/#160, `b49a648` #200/#201) adjusted clamp *values* but added no
  diagnostic.
- **Impact**: Any song with content above B6 (common for piccolo/flute/high lead lines,
  or a track transposed up) or, for tone channels, below C1 plays wrong, unannounced
  notes. MEDIUM (silent, no workaround short of inspecting output audio) per the severity
  rubric's clamp-diagnostics guidance. Not CRITICAL: the clamp is bytecode-format-mandated
  (no valid alternative encoding to fall back to) and does not corrupt other channels/data.
- **Related**: #158/NH-16 (fixed the low-end clamp *value*; this is about the missing
  *diagnostic*). Sibling to the same clamp-visibility gap other audits flag on lossy
  pipeline steps.
- **Suggested Fix**: Have `export_tables_with_patterns`/`export_direct_frames` accumulate
  a per-song count of clamped notes (both directions) and print a one-line summary at end
  of export (e.g. `"⚠ 12 notes clamped to NES tone range (24-95); pitch may differ from
  the MIDI file"`), mirroring how other lossy steps report their stats.

### EXP-09: `exporter/compression.py`'s `CompressionEngine` and `BaseExporter` compress/decompress helpers are dead code
- **Severity**: LOW
- **Dimension**: D7 (cross-exporter consistency) — dead code in the exporter's own scope
- **Spec ref**: none (tech-debt observation).
- **Location**: `exporter/compression.py` (`CompressionEngine`); `exporter/base_exporter.py:12-46`
  (`compress_channel_data`/`decompress_channel_data`).
- **Status**: Existing (prior report `docs/audits/AUDIT_EXPORTERS_2026-07-03.md`, EXP-09,
  reported NEW; re-confirmed still present at HEAD — not in the pre-fetched open-issue
  snapshot).
- **Description**: `BaseExporter.__init__` instantiates a `CompressionEngine` and wraps its
  RLE+delta `compress_pattern`/`decompress_pattern`, but none of the three live exporters
  (`CA65Exporter`, `NSFExporter`, `FamiStudioExporter`), nor `main.py`, nor any production
  module ever calls `compress_channel_data`, `decompress_channel_data`, or
  `CompressionEngine`. The CA65 paths do their own inline compression
  (`_compress_macro`, direct frame tables); this engine is unused at runtime, exercised
  only by `tests/test_compression.py`, `tests/test_compression_integration.py`, and
  `tests/test_exporter_integration.py`.
- **Evidence**:
  ```
  $ grep -rn 'compress_channel_data\|decompress_channel_data\|CompressionEngine' --include='*.py' .
  tests/test_exporter_integration.py:8, :46
  exporter/base_exporter.py:4, :10, :12, :34
  tests/test_compression.py:4, :6, :8
  tests/test_compression_integration.py:3, :8
  exporter/compression.py:6
  ```
  No exporter or `main.py` call site — only the definition, the `BaseExporter` wrappers,
  and tests.
- **Impact**: None functional. Maintenance/confusion cost: a contributor could assume this
  is the live compression path for exported channel data (it is the only "compression"
  concept in `exporter/`) and modify it expecting a ROM-output effect.
- **Related**: distinct from `tracker/pattern_detector.py`'s live `PatternCompressor`.
- **Suggested Fix**: Either wire it in (if RLE/delta channel compression is still planned)
  or remove `CompressionEngine`/`compress_channel_data`/`decompress_channel_data` and their
  dedicated tests.

---

## Re-verified fixes (all confirmed holding at HEAD)

- **EXP-04 (#80, byte-range on `inst_id`/`loop_start`) — NOW FIXED** (commit `b7c99c8`).
  `_register_instrument` (`exporter_ca65.py:822-841`) raises `ValueError` when
  `new_id > 0xFF`, and is the single registration path used by both the mid-stream change
  (`:1057`) and final-flush (`:1109`) call sites. `_compress_macro` (`:892-893`) skips any
  loop candidate whose `loop_start > 0xFF`, falling back to the always-byte-safe
  sustain/no-compression baseline. No raw unbounded `${val:02X}` byte remains on either
  operand.
- **EXP-07 (#83, spec doc-rot on `$FE`/`$87`) — NOW FIXED** (commit `b7c99c8`).
  `docs/AUDIO_BYTECODE_SPEC.md` §3 was rewritten to list only what the engine dispatches
  (`$80`, `$85`, `$87`, `$FE`), note `$85` is engine-supported but not exporter-emitted,
  and cross-reference the two distinct `$FE` bytes (sequence-level bank-jump vs in-macro
  loop control §2.3).
- **EXP-08 (arranger DPCM `sample_id` clamp) — NOW FIXED** (commit `60522b5`).
  `arranger/pipeline_integration.py:289` now reads `'note': min(255, data['sample'] + 1)`,
  matching `nes/emulator_core.py`'s `min(255, …)` and the exporter's stated 255-ceiling
  contract. `grep -rn "min(95" arranger/ nes/emulator_core.py exporter/exporter_ca65.py`
  returns nothing.
- **EXP-01 (#77, macro `$FE`/`$FF` collision)**: `_encode_macro_offset`
  (`exporter_ca65.py:71-84`) clamps to `[-128,127]` and snaps `-1→0x00`, `-2→0xFD`; both
  pitch/arp call sites (note-start `:1065-1066`, continuation `:1081-1082`) route through
  it.
- **EXP-02 (#78, triangle continuation pitch)**: both note-start (`:1063`) and
  continuation (`:1079`) `midi_note_to_timer_value` calls pass `channel`; the continuation
  site carries an explicit regression comment citing #78.
- **EXP-03 (#79) / D8 (`--format nsf` dead dispatch)**: `main.py`'s `export` subcommand
  offers `choices=['ca65']`; `run_export` branches only on `"ca65"`.
- **EXP-05 (#81, non-playable NSF)**: `NSFExporter.export()`/`export_nsf()`
  (`exporter_nsf.py:74-81`) unconditionally `raise NotImplementedError` citing #81; the old
  JSON/hand-assembled play routine is gone. `NSFHeader`/`NSFMacroPacker` remain inert,
  uncalled scaffolding.
- **EXP-06 (#82, FamiStudio channel/octave bugs)**: `midi_note_to_famistudio`
  (`exporter_famistudio.py:168-171`) clamps `octave = max(0, min(7, (note // 12) - 1))`;
  the DPCM branch (`:109-112`) falls back to `event.get('sample_id')` then
  `max(0, event.get('note', 1) - 1)` when absent — no `KeyError`. The five-channel list
  matches the CA65 set.
- **NH-16 (#158, sub-C1 pitch macro wrap)**: `midi_note_to_timer_value` clamps
  `[24, 119]`; the bytecode-stream note is separately floored to 24 for tone channels
  (`:1023-1033`), noise excluded.
- **D-09 (#72, dead `$87 CMD_DMC_LEVEL` emitter)**: `grep` for `CMD_DMC_LEVEL`/`$87` in
  `exporter_ca65.py` returns nothing.

## Existing findings re-confirmed, already tracked (not re-counted)

- **`is_midi_velocity` dead code = Existing #165 (NH-23, OPEN)** — `exporter_ca65.py:993-999`
  computes `is_midi_velocity = max_vol > 15` with a comment about applying a "power curve,"
  but the value is never consumed and `vol` flows raw into `vol_seq` (`:1067`/`:1083`). I
  independently confirmed this is harmless in practice: every live frame producer clamps
  volume to 0-15 (`nes/emulator_core.py:112/118/168/181` power curve → `max(1, int(15*…))`;
  `nes/envelope_processor.py:78` `max(0, min(15, …))`; `arranger/voice_allocator.py`
  `vel // 8`; `arranger/pipeline_integration.py:276` `max(1, min(15, …))`), so
  `is_midi_velocity` is always False and no >15 volume reaches the `${val:02X}` macro-byte
  emit. Dead code with a latent (currently-unreachable) correctness footgun — already
  covered by NH-23 (#165); not re-filed.
- **NH-25 (#167, OPEN)** — direct-path pulse control bytes omit the length-counter halt
  flag; `ora #$08` on `$4003`/`$4007`/`$400B` (`:493`/`:565`/`:634`) arms length index 1
  (~2.1 s), a deliberate safety net, not the halt-flag gap NH-25 tracks. Unchanged.
- **NH-21 (#163)** — cross-referenced, not duplicated: `_compress_macro`'s loop encoding
  (`[0xFE, loop_start]`, `:895`) is emitted correctly per spec §2.3, but the engine's
  `EVAL_MACRO` only decodes `$FF`. Emission side is correct here; the decode gap is
  engine-side (NH-21's territory).

## Methodology notes (disproved candidates)

- **D2 register-block correctness (independent re-check)**: direct-path stores map each
  channel to its own APU block — pulse1 `$4000/$4002/$4003`, pulse2 `$4004/$4006/$4007`,
  triangle `$4008/$400A/$400B`, noise `$400C/$400E/$400F`, DMC `$4010-$4013`, status/frame
  `$4015/$4017`. Triangle control is `0x80 | (volume * 7)` written to `$4008` (linear
  counter, bit 7 = control flag) — max `0xE9`, a single byte, targeting linear-counter
  semantics, not a pulse volume/duty nibble. No off-by-$4 misassignment. Disproved.
- **D4 macro-path volume overflow**: chased whether raw MIDI velocity (0-127) could leak
  into a 4-bit volume macro byte via the unused `is_midi_velocity`. All four live
  producers clamp to 0-15 (evidence above), so no >15 volume reaches the macro emit.
  Reduced to the already-tracked dead-code observation (#165), not a live byte-range bug.
- **D4 DPCM note byte**: `note` for the DPCM channel is clamped to `[0, 255]` (`:1021-1022`)
  and emitted as the operand of a Length command (`:1204`), consumed as data by the engine
  rather than dispatched, so a DPCM note of `$FE`/`$FF` is not misread as a control byte.
  Not a finding.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-07-05.md
```
