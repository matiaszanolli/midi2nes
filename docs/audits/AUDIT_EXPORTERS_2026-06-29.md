# Exporters Audit — 2026-06-29

Scope: `exporter/` output generators (CA65 macro-bytecode + direct-frame paths,
NSF, FamiTracker, FamiStudio), cross-checked against `docs/AUDIO_BYTECODE_SPEC.md`,
`docs/MACRO_USAGE_GUIDE.md`, the shipped engine `nes/audio_engine.asm`, and the
consumer `nes/project_builder.py`. Default-pipeline path (`python main.py in.mid out.nes`
→ macro-bytecode via `export_tables_with_patterns` → `music.asm` → CC65) weighted first.

## Summary

### Counts by severity
- CRITICAL: 0
- HIGH: 4
- MEDIUM: 3
- LOW: 1
- (Existing / deduped, not re-counted: 2)

### Counts by dimension
- D1 (CA65 well-formedness/builder compat): 0 new
- D2 (APU register serialization): 1 (shared with D7)
- D3 (pattern-vs-empty paths): 0 new (Existing #4)
- D4 (byte-range safety): 2 + 1 cross-ref
- D5 (bytecode-spec conformance): 1
- D6 (macro emission): 1
- D7 (cross-exporter consistency): 2
- D8 (format-string / CLI mismatch): 1

### Three highest-impact findings (default CA65 path first)
1. **EXP-01 (HIGH)** — Macro data values `$FE`/`$FF` collide with the macro
   control bytes: a pitch-bend offset of −1/−2 (`0xFF`/`0xFE` after `& 0xFF`), or a
   negative arpeggio offset, is emitted into a `macro_pitch`/`macro_arp` stream where
   the 6502 engine reads `$FF` as end-of-macro and `$FE` as loop. Silently truncates
   the macro / changes the played pitch on bent notes. Default macro-bytecode path.
2. **EXP-02 (HIGH)** — Triangle continuation frames compute `base_timer` from the
   **pulse** `/16` table (the `channel` arg is dropped on the second call site), so
   `pitch_offset` on every sustained triangle frame is the ~−214..−855 difference
   between the two tables, clamped to −128 and added to the triangle period by the
   engine → detuned triangle on every held note. Default macro-bytecode path.
3. **EXP-03 (HIGH)** — `--format nsf` is dead: argparse allows `{nsf, ca65}` but
   `run_export` dispatches on the never-allowed string `"nsftxt"`, so `--format nsf`
   matches no branch and silently produces no output.

---

## Findings

### EXP-01: Macro pitch/arp data values collide with the `$FE`/`$FF` macro control bytes
- **Severity**: HIGH
- **Dimension**: D6 (macro emission) — also D4 (byte-range safety)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` §2.3 ("`$FF`: End of macro (sustain last value)", "`$FE, <offset>`: Loop"); engine `nes/audio_engine.asm` `EVAL_MACRO` (`cmp #$FF / bne @not_end`) and `nes/project_builder.py:283-285` (`cmp #$FF … cmp #$FE`).
- **Location**: `exporter/exporter_ca65.py:992`, `:1007` (pitch), `:993`, `:1008` (arp); consumed by `_compress_macro` `:782-830` and emitted as `macro_pitch_*`/`macro_arp_*` `.byte` rows at `:1048-1052`.
- **Status**: NEW
- **Description**: Pitch macro entries are `pitch_offset = max(-128, min(127, pitch_val - base_timer)) & 0xFF`. A bend of −1 timer unit yields `0xFF`; −2 yields `0xFE`. Arp entries are `frame_data.get('arp', 0) & 0xFF`; a negative arpeggio offset (semitone down) yields `0xFF`/`0xFE` likewise. These bytes are appended to the macro sequence and then handed to `_compress_macro`, which also *appends its own* `$FF`/`$FE` control bytes. The 6502 macro evaluator (`EVAL_MACRO` and the duplicate `process_channel_macros`) treats the **first** `$FF` it reads as "end of macro / sustain" and `$FE` as "loop". So a legitimate −1 pitch-bend frame in the middle of a vibrato macro terminates the macro early; a −2 frame is read as a loop command and consumes the following data byte as a loop offset, desyncing the whole stream.
- **Evidence**:
  - `:992` `pitch_offset = max(-128, min(127, pitch_val - base_timer)) & 0xFF` — no exclusion of `0xFE`/`0xFF`.
  - `_compress_macro` (`:786-830`) inserts `[0xFF]` and `[0xFE, loop_start]` as terminators on the *same value domain*.
  - Engine `EVAL_MACRO` (`audio_engine.asm:64-77`): `lda (ptr1), y / cmp #$FF / bne @not_end` — any `$FF` in the data ends the macro.
- **Impact**: Wrong pitch / truncated envelope on any note carrying a small downward pitch bend or a downward arpeggio step — i.e. vibrato, portamento, and minor-interval arps, which `docs/MACRO_USAGE_GUIDE.md` §1–2 actively advertise. Macro-bytecode (default) path; affects pulse1/pulse2/triangle. Borders CRITICAL because it silently changes the played song with no diagnostic.
- **Related**: `docs/MACRO_USAGE_GUIDE.md` §1 ("bending up to +/- 127 APU timer units"); EXP-04 (loop_start byte range).
- **Suggested Fix**: Reserve `$FE`/`$FF` for control only. Bias/encode signed offsets so the data domain cannot reach `0xFE`/`0xFF` (e.g. store offset as `127+value`, or use a separate escape), or clamp the offset domain to `[-125, 125]` and document the limit. The engine's `EVAL_MACRO` must agree with whatever encoding is chosen.

### EXP-02: Triangle continuation frames use the pulse `/16` base timer, corrupting sustained-triangle pitch
- **Severity**: HIGH
- **Dimension**: D6 (macro emission)
- **Spec ref**: `docs/APU_TRIANGLE_REFERENCE.md` (triangle period table is an octave below pulse for the same note); `docs/APU_PITCH_TABLE_REFERENCE.md`. Consumer: `audio_engine.asm:443-457` adds `temp_pitch` to `triangle_period_*`.
- **Location**: `exporter/exporter_ca65.py:1005` (`base_timer = self.midi_note_to_timer_value(note)` — **no `channel` arg**) vs `:990` (`...(note, channel)`).
- **Status**: NEW
- **Description**: On the **first** frame of a note (`:990`) `base_timer` is computed with the channel, so triangle correctly uses `NES_TRIANGLE_TABLE`. On every **continuation** frame of the same note (`:1005`, the `else` branch that extends `dur`) the `channel` argument is omitted, so `midi_note_to_timer_value` defaults `channel=None` and returns `NES_NOTE_TABLE` (the pulse `/16` table). The per-frame `pitch_offset` is then `triangle_pitch_val − pulse_base_timer`, a large constant (e.g. for note 36: `854 − 1709 = −855`, clamped to `−128`). The engine adds that offset to the genuine triangle period each frame.
- **Evidence**:
  ```python
  990:  base_timer = self.midi_note_to_timer_value(note, channel)   # first frame: correct
  1005: base_timer = self.midi_note_to_timer_value(note)            # continuation: pulse table
  ```
  `python -c` over `nes/pitch_table.py`: pulse vs triangle timer for note 36 = 1709 vs 854 (diff −855), note 48 = 854 vs 426 (−428), note 60 = 426 vs 212 (−214) — all far beyond the ±127 clamp.
- **Impact**: Every held triangle note (≥2 frames — essentially all bass/lead-triangle content) gets a spurious −128 pitch offset on its sustain frames, detuning it. Macro-bytecode (default) path, triangle channel. The first frame plays in tune, then the note bends; audible on every song with sustained triangle.
- **Related**: Code comments at `:50-57` and `:877-897` (the #12/#16 octave fixes) — this is the same class of bug re-introduced on the continuation call site.
- **Suggested Fix**: Pass `channel` on the `:1005` call: `base_timer = self.midi_note_to_timer_value(note, channel)`. (The same `pitch_val - base_timer` line is otherwise identical to the first-frame branch.)

### EXP-03: `--format nsf` dispatches on an impossible string and silently does nothing
- **Severity**: HIGH
- **Dimension**: D8 (format-string / CLI mismatch)
- **Spec ref**: consumer is `main.py run_export`; CLI declared at `main.py:705`.
- **Location**: `main.py:222` (`if args.format == "nsftxt":`) vs `main.py:705` (`p_export.add_argument('--format', choices=['nsf', 'ca65'], default='ca65')`).
- **Status**: NEW
- **Description**: argparse restricts `--format` to `nsf` or `ca65`. `run_export` checks `if args.format == "nsftxt":` for the NSF branch and `elif args.format == "ca65":` for CA65. `"nsftxt"` is not an allowed choice, so the NSF branch is unreachable; `--format nsf` matches neither branch and `run_export` returns having written nothing — no NSF file, no error.
- **Evidence**: `main.py:222-234` — the two branches are `"nsftxt"` and `"ca65"`; there is no `"nsf"` branch. argparse rejects any other value before dispatch.
- **Impact**: A documented/advertised output format (`nsf`) produces no output and no diagnostic for the `export` subcommand. User-facing silent no-op.
- **Related**: EXP-05 (the NSF exporter the branch would have called is itself non-functional); `main.py:~721` config `export.nsf.load_address` assumes NSF export works.
- **Suggested Fix**: Change the branch to `if args.format == "nsf":` (and fix the underlying NSF exporter per EXP-05), or drop `nsf` from `choices` until NSF is real.

### EXP-04: `inst_id` and `loop_start` can exceed one byte and emit a 3-hex-digit `.byte`
- **Severity**: MEDIUM
- **Dimension**: D4 (byte-range safety)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` §3 (`$80 [id]` instrument id is one byte); §2.3 (`$FE,<offset>` loop offset is one byte).
- **Location**: `exporter/exporter_ca65.py:1118` (`.byte $80, ${inst_id:02X}`), `:825` (`comp = data[:loop_start + p_len] + [0xFE, loop_start]`, later emitted via `${val:02X}` at `:1052`).
- **Status**: NEW
- **Description**: `inst_id = instruments[inst]` grows with the count of unique (vol,arp,pitch,duty) tuples; with >256 unique instruments `${inst_id:02X}` formats as `$100` (3 hex digits), which `ca65` rejects (or, if it parsed, the engine's single-byte `CMD_INSTRUMENT` fetch reads the wrong id). Likewise `_compress_macro` stores `loop_start` (a raw frame index into the macro) as the `$FE` operand; for a single note longer than 256 frames whose macro loops late, `loop_start > 255` formats as `$1xx`.
- **Evidence**: `:983` `instruments[inst] = len(instrument_defs)` (unbounded); `:1118` formats it `:02X`. `:823-825` `loop_start = n - (repeats + 1) * p_len` (bounded only by macro length `n`); `:1052` emits each macro byte `:02X`.
- **Impact**: Assembly failure (or wrong instrument/loop) on songs with very high timbre variety (>256 distinct instruments) or a single note > ~4.3 s with a late macro loop. Realistic only for dense/long material, hence MEDIUM, but it is a hard `ca65` error when hit.
- **Related**: EXP-01 (same `$FE` operand byte domain).
- **Suggested Fix**: Assert/guard `inst_id <= 0xFF` (and cap or split instrument count) and `loop_start <= 0xFF` (cap macro length before loop encoding), emitting a clear error rather than an out-of-range `.byte`.

### EXP-05: NSF exporter emits JSON-as-data and a hand-assembled play routine with wrong branch offsets — not a playable NSF
- **Severity**: HIGH
- **Dimension**: D7 (cross-exporter consistency) — also D2 (APU serialization)
- **Spec ref**: a valid NSF must contain 6502 code at `play_address`; `docs/NES_APU_REFERENCE.md` for the `$4000–$400F` register window the loop claims to fill.
- **Location**: `exporter/exporter_nsf.py:124-132` (`_serialize_compressed_data` → `json.dumps(...).encode('utf-8')`), `:134-153` (`_generate_play_routine`).
- **Status**: NEW
- **Description**: Two independent defects make the NSF output non-functional:
  1. Channel "data" is serialized as a UTF-8 **JSON string** embedded in the NSF binary (`json.dumps(compressed_data)`), which is not 6502-executable or APU-loadable; the `NSFMacroPacker` docstring (`:242-245`) admits this is draft and "will eventually replace the JSON-based serialization".
  2. The hand-assembled `_generate_play_routine` branch offsets are wrong. `BEQ done` (`$F0,$0A`) targets routine offset 30, but `RTS` is at offset 28 — the branch lands one byte past the routine, into frame data executed as code. `BNE loop` (`$D0,$E7`) targets offset 3 (mid-instruction), not the `LDA ($00),Y` load loop at offset 14.
- **Evidence** (offset arithmetic over the `:137-152` byte list): `BEQ` operand `$0A` from next-PC 20 → 30 (past `RTS@28`); `BNE` operand `$E7` (−25) from next-PC 28 → 3 (not the loop label at 14).
- **Impact**: Any NSF produced is not a playable NSF (would crash or play garbage in an NSF player). Per SKILL D7 this is HIGH. Practical blast radius is currently limited because EXP-03 makes the NSF branch unreachable from the CLI, but `NSFExporter.export()` is public and called directly by tests/other tools.
- **Related**: EXP-03 (unreachable dispatch). Duplication with CA65 serialization is `/audit-tech-debt` territory; reported here for behavioral non-playability.
- **Suggested Fix**: Either replace the JSON serializer with the `NSFMacroPacker` binary path and a correctly-assembled (or `ca65`-assembled) play routine, or mark NSF export explicitly unsupported and remove it from the CLI until implemented.

### EXP-06: FamiTracker text export declares 5 channels but writes a single note column; negative octaves on low notes
- **Severity**: MEDIUM
- **Dimension**: D7 (cross-exporter consistency)
- **Spec ref**: consistency with the CA65 macro path (`pulse1/pulse2/triangle/noise/dpcm`, `exporter/exporter_ca65.py:914`).
- **Location**: `exporter/exporter.py:26` (`COLUMNS 1 1 1 1 1`), `:33-43` (one `note_str`/`vol` per row), `:9-12` (`midi_note_to_ft`).
- **Status**: NEW
- **Description**: `generate_famitracker_txt_with_patterns` declares five channels (`COLUMNS 1 1 1 1 1`) but each row emits exactly one `note vol` cell (`f"{row:02X} | {note_str} 00 {vol}"`), not five channel cells — the CA65 path's other four channels are silently dropped from the FamiTracker view of the same song. Separately, `midi_note_to_ft` computes `octave = (note // 12) - 1`, producing negative octaves (e.g. MIDI 0–11 → octave −1) that FamiTracker does not accept.
- **Evidence**: `:40` builds a single-column row; `COLUMNS 1 1 1 1 1` at `:26` promises five. `:10-11` `octave = (note // 12) - 1` with no floor at 0.
- **Impact**: FamiTracker export describes a different (mono, possibly negatively-octaved) song than the ROM. FamiTracker export is a secondary format and is not wired into `run_export` (only imported at `main.py:24`), so blast radius is contained — MEDIUM. (`midi_note_to_famistudio` in `exporter/exporter_famistudio.py:158-163` has the identical negative-octave issue.)
- **Related**: EXP-05 (NSF stub); `exporter/exporter_famistudio.py:104` (`event['sample_id']` KeyError risk on the dpcm branch — the CA65 path uses `note`, not `sample_id`).
- **Suggested Fix**: Emit one cell per declared channel per row (or set `COLUMNS` to match the single column written), and clamp/offset octaves into FamiTracker's valid 0–7 range. Align the dpcm field name with the frames dict the rest of the pipeline produces.

### EXP-07: `docs/AUDIO_BYTECODE_SPEC.md` §3 contradicts the shipped engine/exporter on `$FE`, `$87`, and DPCM opcode
- **Severity**: LOW
- **Dimension**: D5 (bytecode-spec conformance) — doc-rot
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` §2.3 / §3 vs `nes/audio_engine.asm:209-276` and `exporter/exporter_ca65.py:1102, 1112, 1118`.
- **Location**: `docs/AUDIO_BYTECODE_SPEC.md` §3 command table (lines 65-73) and §2.3.
- **Status**: NEW
- **Description**: The exporter and the shipped engine **agree** with each other but **disagree with the spec doc**: the exporter emits `$FE`+bank+ptr_lo+ptr_hi as `CMD_BANK_JUMP` (`:1102`) and the engine decodes exactly that (`audio_engine.asm:259-276`); the exporter emits `$87`+level as `CMD_DMC_LEVEL` (`:1112`) and the engine decodes it (`:252-257`). But §2.3 defines `$FE` as the **macro-loop** control byte (which is true *inside macros*, a different namespace) and §3 lists **no** `$87` and no bank-jump opcode, while listing `$85 CMD_DPCM_PLAY` and `$84 CMD_JUMP` that the exporter never emits in this path. The doc is stale relative to the implemented sequencer commands.
- **Evidence**: §3 table has `$80,$81,$82,$83,$84,$85,$86` and no `$87`/`$FE`-sequence-command rows; engine `@is_command` dispatch (`:208-217`) handles `$FE`,`$85`,`$87`,`$80`.
- **Impact**: Documentation-only. Anyone implementing a second engine or tooling from the spec would mis-decode `$FE`/`$87`. No runtime effect because the exporter and engine match. LOW (doc-rot).
- **Related**: EXP-01 (the `$FE`/`$FF` macro-control collision is the *real* runtime issue in the macro namespace).
- **Suggested Fix**: Update §3 to document `$87 CMD_DMC_LEVEL` and the `$FE` four-byte sequence-level bank-jump (distinct from the in-macro `$FE` loop), and remove/realign the `$84`/`$85` rows that the implemented path does not use.

---

## Deduped against open issues / prior audits (not re-counted)

- **`references` argument ignored / `patterns` used only as a boolean switch** —
  **Existing: #4** (and prior `AUDIT_PIPELINE_2026-06-28.md` F-01). Confirmed still
  present: `export_tables_with_patterns` early-returns to `export_direct_frames` when
  `not patterns` (`exporter/exporter_ca65.py:843`) and never reads `references`. The
  in-code comment at `:832-841` documents this as intended. No new finding filed (D3).
- **`export` appends DPCM block in `'a'` mode (re-run clobber/duplicate-symbol risk)** —
  **Existing: #23** (F-10). `main.py:266-267` `open(args.output, 'a')`. No new finding (D1).

## Methodology notes (disproved candidates)

- **D5 "$FE/$87 contradict the engine → HIGH/CRITICAL"**: disproved. Read
  `nes/audio_engine.asm` — the engine decodes `$FE`/`$87`/`$85` exactly as the exporter
  emits them. The contradiction is doc-vs-code only (EXP-07, LOW), not engine-vs-exporter.
- **D2 triangle `0x80 | (volume*7)` in `export_direct_frames`**: re-read `:160-168` —
  it targets `$4008` (linear-counter load), bit 7 = control flag, bits 6-0 = counter;
  `volume*7` (max 105) stays in 7 bits and is gated to `0x00` when volume is 0. Correct,
  not a finding.
- **D1 segment/label cross-check**: the macro path's `.export`ed labels
  (`pulse1_sequence`…`instrument_table`, `ntsc_period_*`, `triangle_period_*`) are all
  `.import`ed by `nes/audio_engine.asm:4-10`; `dpcm_*_table` are stubbed/exported by
  `nes/project_builder.py:447-457`; `.importzp ptr1,temp1,temp2,frame_counter` resolve via
  `audio_engine.asm:16` `.exportzp`. `BANK_{NN}` forward labels are defined in the next
  segment in-file (`:1101-1108`). No new D1 finding.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-06-29.md
```
