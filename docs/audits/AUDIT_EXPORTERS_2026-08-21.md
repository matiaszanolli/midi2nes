# Exporters Audit — 2026-08-21

Scope: `exporter/exporter_ca65.py` (direct `export_direct_frames`, MMC3 macro-bytecode
`export_tables_with_patterns`, jukebox `export_song_bank_bytecode` + shared
`_build_song_bytecode`), `exporter/exporter_nsf.py`, `exporter/exporter_famistudio.py`,
and their consumers (`nes/project_builder.py`, `nes/audio_engine.asm`, `main.py`
export/song-build dispatch). Cross-checked against `docs/AUDIO_BYTECODE_SPEC.md` and
`docs/MACRO_USAGE_GUIDE.md`. Dedup ran against `gh issue list` (200 issues, **0 open**,
snapshot in `/tmp/audit/issues.json`), all prior `docs/audits/AUDIT_EXPORTERS_*` reports,
and — since three sibling audits ran earlier today — `AUDIT_NES_HARDWARE_2026-08-21.md`,
`AUDIT_PIPELINE_2026-08-21.md`, and `AUDIT_PATTERNS_2026-08-21.md`.

No commit has touched `exporter/` since `8ea7ac3` (2026-08-07, the JUKEBOX_BUILD-gate /
per-song CODE_8000 fix); today's `949f0c6` touched only audit skill docs.

## Summary

### Counts by severity
| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 3 |
| LOW      | 6 |
| **Total**| **9** |

(Four additional defects that surface in exporter-adjacent code were independently
found and filed **today** by sibling audits and are cross-referenced, not re-counted —
see "Cross-audit dedup" below. Two of those are CRITICAL/HIGH in their home reports.)

### Counts by dimension
| Dimension | Count |
|-----------|-------|
| D1 CA65 well-formedness / builder compat | 1 |
| D2 APU register serialization | 0 |
| D3 Pattern-vs-empty paths | 1 |
| D4 Byte-range safety | 1 |
| D5 Bytecode-spec conformance | 2 |
| D6 Macro emission | 0 |
| D7 Cross-exporter consistency | 2 |
| D8 Format-string / CLI choices | 0 |
| D9 Multi-song jukebox export | 2 |

### Three highest-impact findings
1. **EXP-2026-08-21-1 (MEDIUM, D5)** — the default bytecode path splits any note
   longer than 32 frames into repeated Length+Note pairs, and the engine treats every
   note byte as a fresh onset: macro steps reset and a `$4003`/`$4007` rewrite is
   forced, so every held pulse note re-clicks (duty-phase reset) at each 32-frame
   boundary. The `--no-patterns` direct path sustains the same note cleanly — the two
   paths audibly diverge on the same input.
2. **EXP-2026-08-21-2 (MEDIUM, D7)** — FamiStudio export numbers full patterns with a
   *global* counter but remainder patterns with a *per-channel* counter, so for every
   channel after the first the SONG `SEQUENCE` references pattern names that were never
   defined (repro included) — the exported text is not importable for any ≥2-channel
   song longer than 64 frames.
3. **EXP-2026-08-21-4 (MEDIUM, D9, carried from 2026-08-07)** — the jukebox exporter
   still has no self-contained DPCM rejection; the v1 "no DPCM in `song build`"
   invariant is enforced only by `main.py`, unlike every other invariant this file
   raises `ValueError` for itself. Unfixed and never filed as a GitHub issue.

## Verification of prior fixes (all hold)

- **EXP-2026-08-07-1 / `8ea7ac3` (D1/D9)** — verified with a **real CC65 build and
  `ld65 --dbgfile` symbol resolution**, not just link success: a 2-song jukebox build
  places `song0_instrument_table` ($8200), `song1_instrument_table` ($822A), all
  `song{i}_macro_*`, `song_table_ptr_lo` ($8254) and `song_count` ($8272) inside the
  fixed `CODE_8000` window ($8000–$9FFF); each song's `pulse1_sequence` resolves at
  $C000 in its own `BANK_NN` (song0 bank 0, song1 bank 1 — fresh bank per song). A
  **1-song bank** also assembles and links cleanly (`JUKEBOX_BUILD` gate is
  `song_count is not None` at `nes/project_builder.py:311` and `:354`).
  Note: this had to be driven through `CA65Exporter`/`NESProjectBuilder` directly —
  the `song build` *CLI* is currently broken upstream of the exporter by the
  phantom-DPCM rejection (PIPE-2026-08-21-1, see Cross-audit dedup).
- **#78 (D2)** — both the note-start (`exporter_ca65.py:1263`) and continuation
  (`:1282`, with regression comment) calls pass `channel` into
  `midi_note_to_timer_value`; no channel-less call exists in the method.
- **#81/#79 (D2/D7/D8)** — `NSFExporter.export()`/`export_nsf()` raise
  `NotImplementedError` (`exporter_nsf.py:73-80`); the deleted private methods have no
  remaining references; `NSFHeader`/`NSFMacroPacker` have **no caller outside
  `exporter_nsf.py` and tests** (grep). `--format` offers only `ca65`
  (`main.py:1528`); the only NSF remnant is the cosmetic `--verbose` config print
  (`main.py:1767`), confirmed at-worst-cosmetic.
- **#80/EXP-04 (D4)** — `_register_instrument` (`:1010-1028`) guards `inst_id > 0xFF`
  at **both** call sites (`:1257`, `:1312`). (But see NH-HW-2026-08-21-1 in Cross-audit
  dedup: the engine's real addressing ceiling is 32, far below this guard.)
- **#77 (D4)** — `_encode_macro_offset` is the only encoder for pitch/arp at all four
  sites (`:1265`,`:1269`,`:1284`,`:1285`). Volume is *not* routed through it — see
  EXP-2026-08-21-7.
- **#369/EXP-2026-07-19-1 (D5)** — DPCM `note >= 0x60` raises `ValueError` during
  event collection, **before any output exists** (atomic write means no partial file —
  verified: `note=$60` raises and leaves no file; boundary `note=$5F` / sample_id 94
  exports cleanly).
- **#298/EXP-10 (D4)** — both clamp branches feed the tally (`:1227-1233`), keyed on
  pre-clamp source note, dpcm excluded; reported by both single-song (`:1537-1543`)
  and jukebox (`:1675-1681`) exporters.
- **#163/NH-21 + #83/EXP-07 (D5/D6)** — `_compress_macro` (`:1030-1064`) emits only
  `$FF` sustain (round-trip verified lossless: the engine re-reads the byte before
  `$FF`, which is exactly the trimmed repeated value; empty macro → `[$FF]` → engine
  null-default path). Spec §2.3 marks `$FE` reserved/not-implemented; §3 documents
  `$FE CMD_BANK_JUMP` as sequence-level. (But the §3 `$87` row has regressed —
  cross-ref NH-HW-2026-08-21-7.)
- **#4 (D3)** — `references` appears only in `export_tables_with_patterns`'s signature
  and docstring, never in the body.
- **#82 + #370/EXP-2026-07-19-2 (D7)** — FamiStudio octave clamp (`:181`) and
  defensive `.get()` reads on tone (`:109-110`) and dpcm (`:121-123`) branches all in
  place; no bare `event[...]` subscript for an optional frame field remains in any
  exporter (grep).
- **D2 register map** — re-read in full: pulse1 `$4000/$4002/$4003`, pulse2
  `$4004/$4006/$4007`, triangle `$4008/$400A/$400B`, noise `$400C/$400E/$400F`, dpcm
  `$4010-$4013`; no off-by-$4. Triangle control is `$00`/`TRIANGLE_CONTROL_ON` (`0xFF`)
  only (#364 holds — no volume/duty semantics). `ora #$08` targets the
  length-load field of `$4003/$4007/$400B` per `docs/APU_LENGTH_COUNTER_REFERENCE.md`.
  Standalone reset and `init_music` both do `$4011=0`, `$4017=$40`, `$4015=$0F`,
  sweep-disable `$4001/$4005=$08`.
- **D3 both paths build** — real end-to-end CC65 builds of the same MIDI through the
  default bytecode path *and* `--no-patterns` both produced valid ROMs today.

## Findings

### EXP-2026-08-21-1: Bytecode path retriggers held notes at every 32-frame boundary (forced `$4003/$4007` phase-reset + macro restart); direct path sustains cleanly
- **Severity**: MEDIUM
- **Dimension**: 5 (Bytecode-Spec Conformance; also D2/D7 divergence)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` §3 Length Commands ($60–$7F cap at 32 frames; no tie/continuation opcode exists) and §3 Note Range ("Triggers the current instrument and resets all macro pointers"); consumer `nes/audio_engine.asm:445-465` (`@is_note`)
- **Location**: `exporter/exporter_ca65.py:1428-1434` (the `while rem_dur > 0: write_dur = min(rem_dur, 32)` split re-emits the same note byte per chunk); `nes/audio_engine.asm:445-465` (`@is_note` unconditionally resets `macro_steps_*` and forces `last_written_hi = $FF`, defeating the #161/NH-18 same-value write suppression at each chunk boundary)
- **Status**: NEW (no matching issue in `/tmp/audit/issues.json` — searched retrigger/click/phase/$4003/sustain; no prior audit covers it)
- **Description**: An event with `dur > 32` cannot be expressed as one note in the
  bytecode format, so the exporter emits repeated `($6X, note)` pairs. The engine has
  no concept of "same note continued": every note byte is a full onset — macro step
  indices reset to 0 and `last_written_hi` is set to `$FF` so the next `$4003/$4007`
  write always happens. Writing `$4003/$4007` restarts the pulse duty-sequencer phase
  (the engine's own #161/NH-18 comment: "otherwise a held note re-clicks every
  frame"), so a held pulse note gets an audible re-click every 32 frames (~533 ms).
  The macro restart additionally replays each macro's first entries: inaudible today
  only because every live producer emits per-event-constant volume/pitch (the
  `envelope_type` scaffolding is inert, #166), but it silently corrupts the exact
  per-frame vibrato/slide/envelope feature `docs/MACRO_USAGE_GUIDE.md` §1/§3
  advertises the moment any producer emits one — frames 33+ of a bent note would
  replay offsets 0-27 instead of 32-59. The direct path (`--no-patterns`) compares
  against `last_pulseN_note` and sustains without any register rewrite, so the two
  export paths audibly differ for the same frames input.
- **Evidence**: `exporter_ca65.py:1432` emits `.byte ${(write_dur-1)+0x60:02X},
  ${note:02X}` once per 32-frame chunk of a single `current_event`;
  `audio_engine.asm:459-460` (`lda #$FF / sta last_written_hi, x`) then
  `:569-572` (`cmp last_written_hi+0 / beq @p1_skip_hi / sta $4003`) — with the
  sentinel, the `beq` never takes on the chunk-boundary frame, so `$4003` is written
  with an *unchanged* period, purely resetting phase.
- **Impact**: Default pipeline (`python main.py song.mid`) — every pulse1/pulse2 note
  held longer than 32 frames clicks periodically mid-note. Triangle/noise unaffected
  (no phase-reset semantics on their register writes). Workaround exists
  (`--no-patterns`), which keeps this MEDIUM rather than HIGH.
- **Related**: #161/NH-18 (the sustain-suppression this defeats at boundaries); #166
  (inert envelope scaffolding is why macro-restart is currently inaudible);
  EXP-2026-08-21-5 (spec gap: no continuation opcode documented or implemented).
- **Suggested Fix**: Add a "tie/continue" encoding (e.g. emit only a Length command
  for continuation chunks, or a dedicated `CMD_TIE`) implemented on both sides
  simultaneously; short of a format change, `@is_note` could skip macro-reset and the
  `last_written_hi` sentinel when the incoming note equals `current_note, x` (making
  same-note bytes idempotent — semantically exactly what the exporter's split means).

### EXP-2026-08-21-2: FamiStudio pattern keys mix a global and a per-channel counter — `SEQUENCE` references patterns that don't exist for every channel after the first
- **Severity**: MEDIUM
- **Dimension**: 7 (Cross-Exporter Consistency)
- **Spec ref**: FamiStudio text format (self-consistency of `PATTERN "name"` definitions vs `SEQUENCE "name"` references within the emitted file)
- **Location**: `exporter/exporter_famistudio.py:129` (full patterns: `pattern_key = f"{channel}_{len(patterns)}"` — `len(patterns)` counts **all** channels' patterns emitted so far), `:135` (remainder pattern: keyed by the **per-channel** count), `:167` (`SEQUENCE` emits `"{channel}_{i}" for i in range(pattern_count)` — per-channel 0-based)
- **Status**: NEW (no prior issue/report; `#82`, `#313/EXP-11`, `#370` covered other defects in this file; the two structural tests flagged by #339/REG-20 only assert `"PATTERNS" in output`, which is why this never failed)
- **Description**: The first channel happens to work because the global and
  per-channel counts coincide. For every subsequent channel, full 64-row patterns get
  globally-numbered names while the final partial pattern gets a per-channel-numbered
  name, and the `SONG` section references per-channel 0-based names throughout.
  Verified by direct execution (2 channels × 130 frames):
  ```
  defined patterns: ['pulse1_0', 'pulse1_1', 'pulse1_2', 'pulse2_3', 'pulse2_4', 'pulse2_2']
  sequences:        ['"pulse1_0" "pulse1_1" "pulse1_2"', '"pulse2_0" "pulse2_1" "pulse2_2"']
  SEQUENCE refs with no matching PATTERN: ['pulse2_0', 'pulse2_1']
  ```
  `pulse2`'s sequence references two undefined patterns, and the one name that *does*
  resolve (`pulse2_2`) is the 2-row remainder placed where the first full pattern
  should play — so even a lenient importer plays the channel scrambled. Related
  cosmetic defect in the same emitter: the remainder pattern is declared
  `LENGTH 64` (`:145`) regardless of its actual row count.
- **Impact**: The FamiStudio text export is structurally self-inconsistent for any
  frames input with ≥2 non-empty channels spanning ≥64 frames — i.e. essentially
  every real song. Blast radius is contained: `generate_famistudio_txt` is not wired
  to any CLI path (`--format` offers only `ca65`), so only library/test consumers hit
  it — which is what keeps this MEDIUM rather than HIGH.
- **Related**: #339/REG-20 (the weak structural tests that mask this); EXP-2026-08-21-3.
- **Suggested Fix**: Key full patterns with the per-channel count (the same
  `len([k for k in patterns if k.startswith(channel)])` expression the remainder
  branch already uses, or a simple per-channel counter), and emit the remainder's real
  `LENGTH`. Strengthen `tests/test_famistudio_export.py` to assert every `SEQUENCE`
  reference resolves to a defined `PATTERN`.

### EXP-2026-08-21-3: FamiStudio export recognizes only string frame keys — an int-keyed frames dict (valid for the CA65 exporter) silently exports all rests
- **Severity**: LOW
- **Dimension**: 7 (Cross-Exporter Consistency)
- **Spec ref**: CA65 exporter's dual-key tolerance (`exporter_ca65.py:230-233` direct path, `:1169` bytecode path: `channel_frames.get(str(frame_idx), channel_frames.get(frame_idx))`)
- **Location**: `exporter/exporter_famistudio.py:101` (`if str(frame) in events:` — no int-key fallback)
- **Status**: NEW
- **Description**: Both CA65 emitters deliberately accept int **or** str frame keys
  (frames built in-memory carry int keys; JSON round-trips produce str keys). The
  FamiStudio path checks only `str(frame)`, so an in-memory frames dict exports a
  file of nothing but `... ..` rest rows with zero warning. Verified: 10 int-keyed
  frames → 10 rows, 0 non-rest. This is precisely the divergence class #370 fixed for
  `.get()` defaults, one level up (key lookup instead of field lookup).
- **Impact**: Library-only (not CLI-reachable); the JSON-mediated path is unaffected.
  Silent empty output rather than a crash, on an input shape the sibling exporter
  documents as valid.
- **Related**: #370/EXP-2026-07-19-2 (same file, same divergence class); EXP-2026-08-21-2.
- **Suggested Fix**: Mirror the CA65 lookup: `event = events.get(str(frame), events.get(frame))`.

### EXP-2026-08-21-4: `export_song_bank_bytecode` still has no self-contained DPCM guard — enforcement lives entirely in the CLI caller (carried from 2026-08-07, unfixed, never filed)
- **Severity**: MEDIUM
- **Dimension**: 9 (Multi-Song Jukebox Export)
- **Spec ref**: `nes/project_builder.py:210-220` (1-byte DPCM stub tables); `docs/ROADMAP.md` ("song build" v1 rejects DPCM)
- **Location**: `exporter/exporter_ca65.py:1548-1685` (no song-level DPCM check; the only DPCM guard in `_build_song_bytecode` is the per-note `>= 0x60` range check at `:1199-1209`); the sole enforcement is `main.py:910-924` (`_song_has_dpcm_events`) called at `:980`
- **Status**: Existing — reported as EXP-2026-08-07-2 in `docs/audits/AUDIT_EXPORTERS_2026-08-07.md`; re-verified today against unchanged code (no commit has touched `exporter/` since `8ea7ac3`); **no GitHub issue was ever filed** (0 open issues; no closed match)
- **Description**: Unchanged from the 08-07 report: calling the public
  `export_song_bank_bytecode` with DPCM-bearing frames silently emits a real
  `song{i}_dpcm_sequence` with trigger bytes, while no `DpcmPacker` runs in the
  `song build` flow — so the engine indexes the builder's 1-byte stub
  `dpcm_*_table`s past their end and feeds garbage bank/addr/len into a live DMC DMA
  trigger. Every other hard invariant in this file (instrument count, DPCM note
  range, bank budget, empty `songs`) raises `ValueError` from inside the exporter;
  this one doesn't.
- **Impact**: Confined today to non-`main.py` callers (tests, library consumers,
  future CLI paths), but it is the one jukebox invariant a direct API consumer can
  violate silently, and the failure mode is out-of-bounds table reads driving
  `$4012/$4013/$4015`.
- **Related**: #30/F-13; EXP-2026-08-07-2 (original report); PIPE-2026-08-21-1 (the
  *caller-side* check this relies on is currently also misfiring in the opposite
  direction — false rejections).
- **Suggested Fix**: Raise `ValueError` from `export_song_bank_bytecode` (or
  `_build_song_bytecode`) for a non-silent `dpcm` channel, mirroring
  `_song_has_dpcm_events`.

### EXP-2026-08-21-5: `docs/AUDIO_BYTECODE_SPEC.md` still doesn't document the jukebox `song_table` format (carried from 2026-08-07, unfixed, never filed)
- **Severity**: LOW
- **Dimension**: 5 (Bytecode-Spec Conformance)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` (grep confirms zero mentions of `song_table`, `song_count`, `song_instrument_ptr`, or jukebox)
- **Location**: `exporter/exporter_ca65.py:1623-1654` (emits `song_table_ptr_lo/hi`, `song_table_bank`, `song_count`, `song_instrument_ptr_lo/hi`) vs the unchanged spec doc
- **Status**: Existing — reported as EXP-2026-08-07-3 in `AUDIT_EXPORTERS_2026-08-07.md`; still true today; no GitHub issue filed
- **Description**: The `song_index*5 + channel` parallel-array layout and the
  per-song instrument-pointer table remain documented only in code
  docstrings/comments. The spec §2.1 additionally still shows an aspirational
  `song_00_header` `.word`-row + `INITIAL_TEMPO` shape that no exporter has ever
  emitted, so the one authoritative doc describes neither of the two real stream-
  lookup mechanisms fully.
- **Impact**: Doc-rot / drift risk only — exporter and engine were re-verified
  consistent today (stride 5, `SEQUENCE_CHANNELS` order, per-song instrument pointer
  indexed by song alone at `audio_engine.asm:259-286`).
- **Related**: EXP-2026-08-07-3; #83/EXP-07 (prior reconciliation of the same doc);
  NH-HW-2026-08-21-7 (a second, separate gap in the same doc's §3).
- **Suggested Fix**: Add a §2 subsection documenting the five jukebox symbols, the
  `*5` stride, and channel order; fix or remove the §2.1 `song_00_header` example.

### EXP-2026-08-21-6: Multi-song bank-overflow error still loses which song failed (carried from 2026-08-07, unfixed, never filed)
- **Severity**: LOW
- **Dimension**: 9 (Multi-Song Jukebox Export)
- **Spec ref**: N/A (error-message quality)
- **Location**: `exporter/exporter_ca65.py:1400-1410` (the `ValueError` names channel and bank but no song), `:1612-1615` (the per-song loop has `prefix` in scope and doesn't catch/re-raise with it)
- **Status**: Existing — reported as EXP-2026-08-07-4 in `AUDIT_EXPORTERS_2026-08-07.md`; code unchanged; no GitHub issue filed
- **Description / Impact**: Unchanged from the 08-07 report — a multi-song bank
  hitting the shared 60-bank budget fails loudly and correctly, but the message names
  only the channel, forcing the user to bisect the bank to find the oversized song.
- **Suggested Fix**: Wrap the `_build_song_bytecode` call in the loop, re-raise with
  the song index/prefix prepended.

### EXP-2026-08-21-7: Volume macro bytes bypass the reserved-byte encoding — an out-of-contract volume ≥ `$FE` silently becomes an end-of-macro control byte
- **Severity**: LOW
- **Dimension**: 4 (Byte-Range Safety)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` §2.3 ("Volume Macros: absolute values (0-15)"; `$FF`/`$FE` reserved as control bytes)
- **Location**: `exporter/exporter_ca65.py:1171` (`vol = frame_data.get('volume', 0)` — raw), `:1270`/`:1286` (`vol_seq` appended unencoded, unlike `pitch`/`arp` which route through `_encode_macro_offset`), `:1343` (`.byte` emission with no mask/clamp)
- **Status**: NEW (defense-in-depth; #77 deliberately covered only pitch/arp)
- **Description**: Every in-pipeline producer clamps volume to 0–15
  (`velocity_to_volume`), but the step-by-step CLI (`main.py export frames.json …`)
  accepts a user-editable frames JSON, and the exporter applies no mask. Verified: a
  frame with `volume: 255` exports `macro_vol_1: .byte $FF, $FF` — the first data
  byte *is* the end-of-macro control byte, so `EVAL_MACRO` reads end-at-step-0 and
  plays the null default (15) instead; values 16–253 emit and are masked to `& $0F`
  by the engine at write time (silent modulo). No crash, but macro semantics silently
  change for malformed input the exporter elsewhere rejects loudly.
- **Impact**: Requires out-of-contract input; wrong volume, never a broken ROM.
- **Related**: #77 (same reserved-byte hazard, fixed for pitch/arp only).
- **Suggested Fix**: Clamp/mask `vol` to 0–15 at collection time (matching the spec's
  stated domain), or raise like the DPCM range guard does.

### EXP-2026-08-21-8: `fetch_sequence_byte` comment claims the sequence bank is swapped into `$8000-$9FFF`; the code maps it via R7 into `$A000-$BFFF`
- **Severity**: LOW
- **Dimension**: 1 (CA65 Well-Formedness & Builder Compatibility — consumer-side doc-rot)
- **Spec ref**: `docs/MAPPER_MMC3_REFERENCE.md` (R7 maps `$A000-$BFFF` in both PRG modes)
- **Location**: `nes/project_builder.py:171` ("Swaps the sequence bank into $8000-$9FFF, reads 1 byte") vs `:176-187` (`lda #$47` selects R7; pointer high byte `and #$1F / ora #$A0` — the `$A000` window)
- **Status**: NEW
- **Description**: The routine's header comment describes the wrong 8KB window. The
  code is correct (and today's `--dbgfile` verification confirms sequence labels link
  at `$C000`-based `BANK_NN` addresses that the `& $1F | $A0` translation maps into
  `$A000-$BFFF`), but the comment invites exactly the kind of misread that produced
  past bank-window bugs (#388-class), and contradicts the correct "fixed `$8000`
  bank" comments 40 lines away in the same generated file.
- **Impact**: None at runtime; maintainer-facing only.
- **Suggested Fix**: s/$8000-$9FFF/$A000-$BFFF (R7)/ in the template comment.

### EXP-2026-08-21-9: `export_direct_frames`' "Data size" summary counts 4 tables for every channel, contradicting its own estimator (noise has 3, DPCM has 1)
- **Severity**: LOW
- **Dimension**: 3 (Pattern-vs-Empty Export Paths — default-path reporting)
- **Spec ref**: `exporter/exporter_ca65.py:112-123` (`estimate_direct_export_size`'s own per-channel accounting: pulse/triangle 4, noise 3, dpcm 1)
- **Location**: `exporter/exporter_ca65.py:1002` (`total_bytes = (max_frame + 1) * 4 * len(all_channels)`)
- **Status**: NEW (no prior audit/issue match; distinct from #361's capacity-estimate defect, which was about the *pre-flight* path and is fixed)
- **Description**: The end-of-export summary multiplies frames × 4 × channel-count,
  overstating the emitted RODATA whenever noise (3 tables) or dpcm (1 table) is
  active — for a 5-channel song it reports 20 bytes/frame where 16 are emitted
  (+25%). The same file already contains the correct per-channel accounting in
  `estimate_direct_export_size`, added precisely so capacity decisions wouldn't rely
  on this kind of drift; only the human-facing print still uses the old math. Nothing
  downstream consumes the printed number (capacity pre-flight sizes the real file).
- **Impact**: Cosmetic/misleading console output only, on the `--no-patterns` path.
- **Suggested Fix**: Reuse `estimate_direct_export_size(frames)` (or its
  `bytes_per_frame` map) for the summary.

## Cross-audit dedup (found today by sibling audits — verified here, not re-counted)

Per the shared protocol ("report once, in the most actionable dimension, and
cross-reference"), these defects sit on the exporter↔engine contract but are already
fully documented in today's sibling reports; this audit independently re-verified each
and adds the exporter-side evidence noted below. **One GitHub issue each, not two.**

1. **32-instrument engine ceiling vs 256-instrument exporter guard** —
   `AUDIT_NES_HARDWARE_2026-08-21.md` **NH-HW-2026-08-21-1 (HIGH)**. Re-confirmed from
   the exporter side: `_register_instrument` (`exporter_ca65.py:1019-1027`) accepts ids
   up to 255 while `EVAL_MACRO`'s `current_inst * 8` (three `asl`s,
   `audio_engine.asm:487-491`) and 8-bit `Y` indexing wrap at id 32 — ids ≥ 32 alias
   mod 32 silently. The exporter-side fix point is exactly this guard (`> 0x1F` until
   the engine grows 16-bit indexing).
2. **8-bit `current_song*5` jukebox indexing (banks of 52+ songs)** —
   `AUDIT_PIPELINE_2026-08-21.md` **PIPE-2026-08-21-3 (CRITICAL)** /
   `AUDIT_NES_HARDWARE_2026-08-21.md` NH-HW-2026-08-21-3. New exporter-side evidence
   from this audit: a **55-song** `export_song_bank_bytecode` output (longest line
   6,778 chars) **assembles cleanly under the system ca65** — so no accidental
   line-length or assembler backstop exists; the exporter is the natural place for a
   `len(songs) <= 51` guard alongside its existing `ValueError` invariants.
3. **Spec §3 still lists `$87 CMD_DMC_LEVEL` as a working opcode** —
   `AUDIT_NES_HARDWARE_2026-08-21.md` NH-HW-2026-08-21-7 (LOW). Re-confirmed: grep
   finds no `$87`/`dmc_level` handler anywhere in `nes/audio_engine.asm` (the
   dispatcher decodes only `$FE`/`$85`/`$80`; `$87` falls to `@unknown_command`, which
   halts the stream), and no `$87` emitter in the exporter (#72 fix holds).
4. **`song build` CLI falsely rejects drumless songs (phantom DPCM triggers)** —
   `AUDIT_PIPELINE_2026-08-21.md` **PIPE-2026-08-21-1 (CRITICAL)**. Hit live during
   this audit: `song build` on a 2-song bank of melodic-only test MIDIs aborts with
   "contains DPCM drum samples" before the exporter ever runs. Upstream of the
   exporter (frames producer); noted here because it currently blocks all CLI-level
   jukebox verification — today's D9 checks had to drive
   `CA65Exporter`/`NESProjectBuilder` directly.

## Suggested next step

```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-08-21.md
```
