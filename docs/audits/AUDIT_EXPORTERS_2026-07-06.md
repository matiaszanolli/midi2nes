# Exporters Audit — 2026-07-06

Scope: `exporter/` output generators — the CA65 macro-bytecode path
(`export_tables_with_patterns`, the default `python main.py input.mid out.nes`
run), the direct-frame path (`export_direct_frames`, `--no-patterns`), NSF
(`exporter_nsf.py`), and FamiStudio (`exporter_famistudio.py`) — per
`.claude/commands/audit-exporters/SKILL.md`. Cross-checked against
`docs/AUDIO_BYTECODE_SPEC.md`, `docs/MACRO_USAGE_GUIDE.md`, the shipped engine
behavior, the frame producers, and the consumer `nes/project_builder.py`.
Severity floors from `.claude/commands/_audit-severity.md`.

Dedup sources: the pre-fetched issue snapshot at `/tmp/audit/issues.json`
(29 issues) and every prior report in `docs/audits/`, in particular
`docs/audits/AUDIT_EXPORTERS_2026-07-05.md` (one day prior). Per skill
instructions, no `gh issue list` was re-run and no issues were created.

**Baseline re-verification.** Since the 2026-07-05 report, three exporter-relevant
commits landed, re-read at HEAD rather than trusting the labels:

- `a3c021b` "stop emitting undecodable macro loop control byte, fix frame-counter
  comments (#163, #164)" — `_compress_macro` (`exporter_ca65.py:926-960`) now
  performs **sustain compression only** and never emits a `$FE` loop byte. This
  is the fix the SKILL anticipates for NH-21; confirmed clean (see D5/D6 below).
- `1bf4a95` "remove dead exporter tables; prune inert arpeggio plumbing (#165,
  #166)" — the previously-flagged `is_midi_velocity` dead code (Existing #165 /
  NH-23) is **gone**; `grep is_midi_velocity exporter/` returns nothing. The arp
  macro is still emitted (neutral offset, one pointer per instrument) with a
  `#166` comment at `:1121`/`:1137`, preserving the 4-pointer instrument layout.
- `833174b` / `7af88a4` (#281-285) — direct-export bank-pack + DPCM/mapper
  guards. These touch the non-default `export_direct_frames` path only; the marker
  emission (`:206-207`) and the `_pack_direct_tables_into_banks` guard
  (`:126-134`, raises `ExportError` if one table exceeds the bank window) are
  internally consistent. No exporter regression introduced.

Every fix re-verified by the 2026-07-05 report still holds at HEAD: EXP-01 (#77,
`_encode_macro_offset` `:71-86` snaps `-1→0x00`/`-2→0xFD`, both pitch/arp sites
`:1117`/`:1121`/`:1136`/`:1137` route through it), EXP-02 (#78, `channel` passed
to `midi_note_to_timer_value` on both note-start `:1115` and continuation `:1134`),
EXP-03/D8 (#79, `main.py:1143` `choices=['ca65']`; `run_export` `:519` branches
only on `"ca65"`), EXP-04 (#80, `_register_instrument` `:906-924` raises past 256
instruments), EXP-05 (#81, `NSFExporter.export()`/`export_nsf()`
`exporter_nsf.py:73-80` raise `NotImplementedError`, no live caller), EXP-06 (#82,
FamiStudio octave clamp `exporter_famistudio.py:168`), EXP-07 (#83, spec §3 `$FE`
`CMD_BANK_JUMP` row present and distinct from the in-macro `$FE`,
`docs/AUDIO_BYTECODE_SPEC.md:95`), NH-16 (#158, `midi_note_to_timer_value` clamps
`[24,119]`; bytecode note floored to 24 for tone channels `:1075-1085`), D-09 (#72,
no `$87`/`CMD_DMC_LEVEL` in `exporter_ca65.py`).

The two findings the 2026-07-05 report carried open — **EXP-10** (silent note
clamp) and **EXP-09** (dead `compression.py`) — remain present, re-confirmed below.

## Summary

### Counts by severity
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 1 (EXP-10 — re-confirmed open from 2026-07-03/07-05; not a new regression)
- LOW: 1 (EXP-09 — re-confirmed open)
- **Genuinely new this cycle: 0**
- Resolved since last cycle: `is_midi_velocity` dead code (Existing #165/NH-23,
  removed by `1bf4a95`); NH-21 macro-loop hazard (#163, loop compression removed
  by `a3c021b`).

### Counts by dimension
- D1 (CA65 well-formedness / builder compat): 0 new (re-verified clean)
- D2 (APU register serialization): 0 new (independently re-verified clean)
- D3 (pattern-vs-empty paths): 0 new (#4 docstring re-verified accurate)
- D4 (byte-range safety): 0 new (EXP-04 #80 guard holds; all macro bytes ≤255)
- D5 (bytecode-spec conformance): 0 new (spec §3 in sync; `_compress_macro` emits
  only `$FF`)
- D6 (macro emission): 0 new (null macros seeded `:1032-1039`; Vol/Arp/Pitch/Duty
  order intact `:1108`/`:1171`/`:1172`)
- D7 (cross-exporter consistency): 1 re-confirmed (EXP-09 dead code)
- D8 (format-string / CLI mismatch): 0 new (re-verified clean)
- Cross-cutting: 1 re-confirmed (EXP-10 clamp diagnostics)

### Three highest-impact findings
1. **EXP-10 (MEDIUM, re-confirmed open)** — the CA65 macro path's tone-channel note
   clamps (`note > 95 → 95`, `0 < note < 24 → 24`, `exporter_ca65.py:1075-1085`)
   are still silent: no counter, log, or warning records that a note was
   re-pitched. A song with content above B6 or below C1 plays altered, unannounced
   notes on the default pipeline.
2. **EXP-09 (LOW, re-confirmed open)** — `exporter/compression.py`'s
   `CompressionEngine` and `BaseExporter.compress_channel_data` /
   `decompress_channel_data` remain dead code: tested but with zero production
   caller.
3. *(No third finding — no new HIGH/MEDIUM surfaced this cycle.)*

---

## Findings

### EXP-10: Tone-channel note clamps in the CA65 macro path have no log/counter — silent pitch change on out-of-range notes
- **Severity**: MEDIUM
- **Dimension**: Cross-cutting (D4 byte-range safety / diagnostics gap)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` §3 Note Range ($00–$5F) — the note
  byte is hard-capped at 95 by the bytecode format (values $60+ are Length/other
  commands), so *some* clamp is mandatory and correct; the gap is the missing
  diagnostic, not the clamp itself.
- **Location**: `exporter/exporter_ca65.py:1072-1085` (the `if channel == 'dpcm'
  … elif note > 95: note = 95 … elif channel != 'noise' and 0 < note < 24: note =
  24` block).
- **Status**: Existing (prior reports `docs/audits/AUDIT_EXPORTERS_2026-07-03.md`
  and `…_2026-07-05.md`, both EXP-10; re-confirmed still present at HEAD — not in
  the pre-fetched open-issue snapshot, so no GitHub issue number is known).
- **Description**: Per the SKILL's verification note on the #158/NH-16 fix, a
  clamped note should be "at least logged/counted somewhere upstream." It still is
  not. Neither `exporter_ca65.py` nor any upstream stage (`nes/emulator_core.py`,
  `arranger/pipeline_integration.py`, `tracker/track_mapper.py`) counts, logs, or
  warns when a note is clamped at either boundary. A melodic line above MIDI note
  95 (B6) or, for tone channels, below 24 (C1) is silently re-pitched with zero
  indication to the user — no CLI output, `--verbose` trace, or diagnostic tool
  (`debug/rom_diagnostics.py`, `debug/check_rom.py`) surfaces it.
- **Evidence**:
  ```python
  # exporter/exporter_ca65.py:1072-1085
  if channel == 'dpcm':
      if note > 255:
          note = 255
  elif note > 95:
      note = 95
  elif channel != 'noise' and 0 < note < 24:
      note = 24
  ```
  `grep -rn "clamp\|out of range\|notes_clamped\|warn" exporter/exporter_ca65.py`
  returns only explanatory comments (`:44`, `:50-51`, `:1068`, `:1078-1084`) — no
  counter or log tied to this clamp. The commits that touched this region since
  the finding was first opened (`421c01f` #158, `b49a648` #200/#201) adjusted
  clamp *values* but added no diagnostic; `a3c021b`/`1bf4a95` did not touch it.
  Note the same information loss surfaces in the secondary FamiStudio exporter,
  which clamps the *octave* instead (`exporter_famistudio.py:168`,
  `max(0, min(7, (note//12)-1))`), so for a sub-C1 or above-B6 input the two
  exporters describe different pitches — a consequence of this same missing-clamp
  visibility, not an independent FamiStudio bug.
- **Impact**: Any song with content above B6 (common for piccolo/flute/high lead
  lines, or a track transposed up) or, for tone channels, below C1 plays wrong,
  unannounced notes on the default (macro-bytecode) pipeline. MEDIUM (silent, no
  workaround short of inspecting output audio) per the severity rubric's
  clamp-diagnostics guidance. Not CRITICAL: the clamp is bytecode-format-mandated
  (no valid alternative encoding to fall back to) and does not corrupt other
  channels/data.
- **Related**: #158/NH-16 (fixed the low-end clamp *value*; this is about the
  missing *diagnostic*). Sibling to the same clamp-visibility gap other audits
  flag on lossy pipeline steps.
- **Suggested Fix**: Have `export_tables_with_patterns` accumulate a per-song count
  of clamped notes (both directions) and print a one-line summary at end of export
  (e.g. `"⚠ 12 notes clamped to NES tone range (24-95); pitch may differ from the
  MIDI file"`), mirroring how other lossy steps report their stats.

### EXP-09: `exporter/compression.py`'s `CompressionEngine` and `BaseExporter` compress/decompress helpers are dead code
- **Severity**: LOW
- **Dimension**: D7 (cross-exporter consistency) — dead code in the exporter's own scope
- **Spec ref**: none (tech-debt observation).
- **Location**: `exporter/compression.py` (`CompressionEngine`);
  `exporter/base_exporter.py:12-46` (`compress_channel_data` /
  `decompress_channel_data`).
- **Status**: Existing (prior reports `…_2026-07-03.md` / `…_2026-07-05.md`,
  EXP-09; re-confirmed still present at HEAD — not in the pre-fetched open-issue
  snapshot).
- **Description**: `BaseExporter.__init__` instantiates a `CompressionEngine` and
  wraps its RLE+delta `compress_pattern`/`decompress_pattern`, but none of the
  three live exporters (`CA65Exporter`, `NSFExporter`, `FamiStudioExporter`), nor
  `main.py`, nor any production module ever calls `compress_channel_data`,
  `decompress_channel_data`, or `CompressionEngine`. The CA65 paths do their own
  inline compression (`_compress_macro`, direct frame tables); this engine is
  unused at runtime, exercised only by `tests/test_compression.py`,
  `tests/test_compression_integration.py`, and `tests/test_exporter_integration.py`.
- **Evidence**:
  ```
  $ grep -rn 'compress_channel_data\|decompress_channel_data\|CompressionEngine' --include='*.py' . | grep -v test
  exporter/base_exporter.py:4:  from exporter.compression import CompressionEngine
  exporter/base_exporter.py:10:     self.compression_engine = CompressionEngine()
  exporter/base_exporter.py:12:     def compress_channel_data(...)
  exporter/base_exporter.py:34:     def decompress_channel_data(...)
  exporter/compression.py:6:    class CompressionEngine:
  ```
  No exporter or `main.py` call site — only the definition, the `BaseExporter`
  wrappers, and tests.
- **Impact**: None functional. Maintenance/confusion cost: a contributor could
  assume this is the live compression path for exported channel data (it is the
  only "compression" concept in `exporter/`) and modify it expecting a ROM-output
  effect.
- **Related**: distinct from `tracker/pattern_detector.py`'s live pattern
  compression.
- **Suggested Fix**: Either wire it in (if RLE/delta channel compression is still
  planned) or remove `CompressionEngine` / `compress_channel_data` /
  `decompress_channel_data` and their dedicated tests.

---

## Re-verified fixes (all confirmed holding at HEAD)

- **NH-21 / macro-loop hazard (#163) — NOW FIXED** (`a3c021b`). `_compress_macro`
  (`:926-960`) only ever appends `$FF` (sustain); loop compression (`$FE,
  loop_start`) is removed. The docstring (`:930-938`) documents that the live
  `EVAL_MACRO` has no `$FE` branch, so no `$FE` reaches a macro stream. The
  sequence-level `$FE` `CMD_BANK_JUMP` (`:1239`) lives in a separate stream and is
  documented in spec §3 (`docs/AUDIO_BYTECODE_SPEC.md:95`). No live `$FE` ambiguity.
- **`is_midi_velocity` dead code (Existing #165/NH-23) — NOW REMOVED** (`1bf4a95`).
  `grep is_midi_velocity exporter/` returns nothing; volume flows through the
  0–15-clamped producers only. The latent (unreachable) >15-volume footgun the
  2026-07-05 report noted is gone.
- **EXP-04 (#80)**: `_register_instrument` (`:906-924`) raises `ValueError` past
  256 instruments — the single registration path used by both `:1109` and `:1164`.
- **EXP-07 (#83)**: spec §3 lists `$80`/`$85`/`$87`/`$FE`; `$85`/`$87` each note
  the Python exporter does not emit them; `$FE` distinguishes sequence-level
  bank-jump from the in-macro loop byte. Exporter and doc agree.
- **EXP-05 (#81)**: `NSFExporter.export()`/`export_nsf()` raise
  `NotImplementedError`; no live caller (`grep NSFExporter/export_nsf` outside the
  module + tests is empty). `main.py` `export` offers `choices=['ca65']` only.
- **EXP-06 (#82)**: FamiStudio octave clamp `max(0, min(7, …))` (`:168`); DPCM
  branch falls back to `max(0, event.get('note', 1) - 1)` (`:110-111`), no
  `KeyError`; five-channel list (`:151`) matches the CA65 set.
- **D2 register-block correctness (direct path, independent re-check)**: APU init
  `$4015=0 / $4017=$40 / $4015=$0F` + sweep-disable `$4001/$4005=$08` (`:463-473`)
  matches `docs/NES_APU_REFERENCE.md` / `docs/APU_PULSE_REFERENCE.md`. Triangle
  control is `0x80 | (volume * 7)` (max `0xE9`, single byte) targeting the linear
  counter at `$4008`, not a pulse volume/duty nibble.

## Existing findings re-confirmed, already tracked (not re-counted)

- **NH-25 (#167, OPEN)** — direct-path pulse control bytes omit the length-counter
  halt flag; `ora #$08` on `$4003`/`$4007`/`$400B` arms a length index as a
  deliberate safety net, not the halt-flag gap NH-25 tracks. Unchanged.
- **NH-14 (#107, OPEN)** — direct-export tone-channel `@silence` `beq` branches are
  unreachable dead code. Engine-side/direct-path tech debt, not a macro-path bug.
- **TD-08 (#137, OPEN)** — stale DPCM `.incbin` TODO in `exporter_ca65.py`; work is
  done by the DPCM packer elsewhere. Tech-debt, not a correctness bug.
- **TD-11 (#136, OPEN)** — `export_direct_frames` is a large monolith; tracked as
  tech debt.

## Methodology notes (disproved candidates)

- **DPCM note byte in the macro path (D4/D5)**: the DPCM channel goes through the
  same length+note encoder (`:1197`/`:1259`). A DPCM `note = sample_id + 1` can
  land in `$60-$7F` or `$80+`/`$FE`/`$FF`, but it is always emitted as the
  *operand* of a Length command, not as a dispatched command byte, so the engine
  reads it as data. Clamped to `[0,255]` (`:1072-1074`). Not a misparse. Disproved.
- **`_compress_macro` round-trip (D6)**: sustain compression only collapses a
  *trailing* run equal to the last value into `value + $FF`; the engine sustains
  the last emitted value on `$FF`. Traced `[15,14,13,10,10,10,10] → [15,14,13,10,
  $FF]`, `[10,10,10] → [10,$FF]`, `[5] → [5,$FF]` — all replay the same values. No
  lossy change to played volume/pitch/duty. Disproved.
- **FamiStudio vs CA65 octave divergence (D7)**: for notes within the shared
  playable range (MIDI 24–95) the two agree (FamiStudio labels MIDI-C1 as `C-1`,
  matching); they diverge only below 24 / above 95, which is a facet of the EXP-10
  clamp (CA65 loses the note, FamiStudio keeps a wider range), not an independent
  FamiStudio serialization bug. Folded into EXP-10's cross-reference, not filed
  separately.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-07-06.md
```
