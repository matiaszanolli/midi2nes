---
description: "Audit output exporters — CA65/NSF/FamiTracker assembly and bytecode correctness"
argument-hint: "[--focus <dims>]"
---

# Exporters Audit

Audit the output-format generators in `exporter/` — the stage that turns the
`frames` dict into something a build toolchain or external tracker consumes. The
default `python main.py input.mid output.nes` run goes through the CA65 path
(`exporter/exporter_ca65.py` → `music.asm` → `nes/project_builder.py` → CC65), so
that path carries the most weight; NSF and FamiStudio are secondary outputs that
must stay consistent with it for the same input.

Shared protocol: `.claude/commands/_audit-common.md` — read the **export contract**
(`export → CA65Exporter.export_tables_with_patterns(frames, patterns, references, output_path)`
writes `music.asm`), the inter-stage data contracts, and the dedup/finding format
there. The bytecode this stage must emit is specified in `docs/AUDIO_BYTECODE_SPEC.md`
and the macro semantics in `docs/MACRO_USAGE_GUIDE.md` — treat both as the target the
6502 engine plays back. Severity rubric: `.claude/commands/_audit-severity.md`. Do not
restate either file; apply them.

A recent bug-fixing sprint closed most of the exporter findings from the prior audit
(`AUDIT_EXPORTERS_2026-06-29.md`). Several dimensions below have been reframed from
"here is a live bug" to "verify the fix holds / check edge cases" — don't re-report
a closed issue as new without re-confirming against current code first (see the
dedup protocol in `_audit-common.md`).

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 1,5`). Default: all.

## Extra Per-Finding Field
- **Dimension**: one of the 9 below.
- **Spec ref**: cite `docs/AUDIO_BYTECODE_SPEC.md` / `docs/MACRO_USAGE_GUIDE.md` section, or the consumer (`nes/project_builder.py`) for emitted-format claims.

## Dimensions

### Dimension 1: CA65 Assembly Well-Formedness & Builder Compatibility
The text `export_tables_with_patterns`, `export_direct_frames`, and
`export_song_bank_bytecode` write in `exporter/exporter_ca65.py` must assemble under
`ca65` and link under the config `nes/project_builder.py` generates. Note that the
first and third now share one serializer, `_build_song_bytecode`
(`exporter/exporter_ca65.py:1102`) — a well-formedness bug there lands in **both** the
single-song and jukebox outputs, so check it once and attribute to both. Skeptical
checklist:
- Every label referenced is defined: the `.export` line (`pulse1_sequence`,
  `pulse2_sequence`, `triangle_sequence`, `noise_sequence`, `dpcm_sequence`,
  `ntsc_period_low`, `ntsc_period_high`, `instrument_table`, the `dpcm_*_table`s)
  has a matching definition; `macro_vol_*`/`macro_arp_*`/`macro_pitch_*`/`macro_duty_*`
  referenced from `instrument_table` `.word` rows (`exporter_ca65.py:1332`) all exist.
  In a jukebox build every one of those symbols is `song{i}_`-prefixed (Dimension 9) —
  verify the prefix is applied to *definition and reference alike*, since a half-prefixed
  symbol assembles cleanly in one song and silently binds to another song's table.
- Segments emitted (`CODE_8000`, `BANK_{NN}`, `DPCM`, and in `export_direct_frames`
  `HEADER`/`ZEROPAGE`/`BSS`/`RODATA`/`CODE`/`VECTORS`) are all declared in the linker
  config `nes/project_builder.py` writes — a segment the exporter emits but `nes.cfg`
  has no MEMORY/SEGMENT for is a link failure. Cross-check `docs/MAPPER_MMC3_REFERENCE.md`.
- `.importzp ptr1, temp1, temp2, frame_counter` (pattern path, `:1466`; jukebox path,
  `:1579`) vs `.importzp frame_counter, temp_ptr` (direct path, `:656`): confirm the importing names
  are exported/`.global`'d by `nes/project_builder.py`'s `main.asm`. A mismatched zeropage
  symbol is a link failure.
- The `non-standalone` branch (`:1515-1523`) emits `.import audio_init, audio_update` and
  jumps to them — confirm those exist in the engine the builder ships. The jukebox path
  imports `audio_init_song` instead (`:1660`), which `nes/audio_engine.asm` only defines
  inside `.ifdef JUKEBOX_BUILD` — so the exporter and the builder's gate must agree or the
  link fails with unresolved externals (see Dimension 9).
- `.byte $FE, ${next_bank:02X}, <{label}, >{label}` bank-jump lines (`:1412`): the forward
  label is defined in the next `BANK_{NN}` segment in the same file (`:1417-1418`) — verify
  it always is, including when `MAX_SEQUENCE_BANK` is reached (the code now raises
  `ValueError` instead of silently overflowing the bank budget, `:1402-1410` — confirm this
  guard still fires for every over-budget path, not just this one call site). In a jukebox
  build this budget is shared across **all** songs (`start_bank` threads song-to-song), so
  the guard must fire on the cumulative total, not per song.

A label/segment that fails to assemble or link = HIGH (wrong output on every ROM
through this path).

### Dimension 2: APU Register Serialization Correctness
`export_direct_frames` writes literal APU stores (`sta $4000`/`$4002`/`$4003` for
pulse1, `$4004`–`$4007` pulse2, `$4008`/`$400A`/`$400B` triangle). The named
constants `APU_PULSE1_CTRL`…`APU_STATUS` at the top of `exporter/exporter_ca65.py`
(`:6-29`) define $4000–$4015. Check:
- Each channel writes its own register block, not another channel's (off-by-$4 bugs).
- The triangle path never writes a duty/volume-shaped control byte — triangle has no
  volume or duty (`docs/APU_TRIANGLE_REFERENCE.md`). `export_direct_frames` builds
  triangle `control` as `0x00` when silent, else the named `TRIANGLE_CONTROL_ON`
  constant (`0x80` control/halt flag `| 0x7F` max reload = `0xFF`, `:40-42`, `:373-377`)
  — confirm that targets the linear-counter semantics ($4008) and is not treated as a
  pulse volume nibble. The old `0x80 | (volume * 7)` loudness-scaled formula (inert but
  an opaque latent trap — see `/audit-nes-hardware` Dimension 2) is **fixed** (#364).
- `ora #$08` (`:625`) before the timer-hi store sets the length-counter reload bit —
  confirm that is the intended $4003/$4007/$400B bit per
  `docs/APU_LENGTH_COUNTER_REFERENCE.md`.
- `$4015` channel-enable and `$4017` frame-counter init (`:466`/`:848`) in the standalone reset
  and the `init_music` block match `docs/NES_APU_REFERENCE.md` /
  `docs/APU_FRAME_COUNTER_REFERENCE.md`.
- **Verify fix (#78, closed)**: continuation (sustain) frames must reuse the *same*
  per-channel pitch table as the frame that started the note. `midi_note_to_timer_value`
  is called with the `channel` argument on both the note-start path (`:1115`) and the
  continuation path (`:1134`, explicit regression comment citing
  #78) — omitting `channel` previously defaulted triangle to the pulse `/16` table and
  bent every sustained triangle note flat. Confirm no other call site (e.g. a future
  refactor) reintroduces a channel-less call inside the continuation branch.
- **Verify fix (#81, closed)**: the old `NSFExporter._generate_play_routine` /
  `_serialize_compressed_data` hand-assembled opcodes (with a `BEQ`/`BNE` offset bug and
  JSON-as-data) no longer exist in `exporter/exporter_nsf.py` — `export()`/`export_nsf()`
  (`:73-80`) now raise `NotImplementedError` immediately instead of emitting broken machine
  code. Confirm nothing still calls the deleted private methods, and that `NSFHeader`
  (`:7`)/`NSFMacroPacker` (`:83`, retained as scaffolding) are dead code with no live caller
  that would trip over their draft state.

Wrong register address or triangle driven with volume/duty = HIGH.

### Dimension 3: Pattern-vs-Empty Export Paths
`run_export` in `main.py` calls `export_tables_with_patterns` with `patterns={}` when
no `--patterns` file is given, and `export_tables_with_patterns` early-returns
(`exporter_ca65.py:973-974`) to `export_direct_frames` when `not patterns`. So there are
**two completely different emitters** (literal frame tables vs macro bytecode) selected
by truthiness of `patterns`. Check:
- Both paths produce assembly the same `nes/project_builder.py` can build — they emit
  *different* segments and *different* exported symbols (the direct path has no
  `*_sequence`/`instrument_table`; the macro path has no `*_note`/`*_control` tables).
  If the builder/engine expects one shape, the other path is silently broken. This is at
  least HIGH; if the builder accepts it but the song is wrong, CRITICAL.
- `export_tables_with_patterns` still ignores its `references` argument entirely — this is
  now explicitly documented in the method's own docstring (`:963-972`, citing #4) as
  intentional: the macro path re-derives events from `frames`, and pattern/reference
  compression is analysis/metrics only. Confirm the docstring's claim still matches
  behavior (grep `references` inside the method body — it should appear only in the
  signature/docstring) rather than re-reporting this as a new finding.
- The empty-patterns path is the default `python main.py input.mid out.nes` run — a
  regression there hits every user.

### Dimension 4: Byte-Range Safety (no value >255 or negative emitted)
Every `.byte ${val:02X}` must receive 0–255; `.word` rows must receive valid 16-bit
labels. Hunt for values that can exceed a byte without clamping in
`exporter/exporter_ca65.py`:
- **Verify fix (#80, closed; superseded by #425/NH-HW-2026-08-21-1) — EXP-04**: the
  `.byte $80, ${inst_id:02X} ; CMD_INSTRUMENT` operand can no longer widen past two hex
  digits. `inst_id` is assigned by the static helper `_register_instrument`, which now raises
  `ValueError` when `len(instrument_defs) > 0x1F` (32 instruments, not 256) — the real ceiling
  is the bytecode engine's 8-bit `current_inst * 8` row-offset math in `EVAL_MACRO`
  (`nes/audio_engine.asm`), which can only address ids 0-31; the old >256 single-byte-operand
  guard was honest about the assembly syntax but let ids 32-255 silently alias onto another
  instrument's macro pointers with no error on either side of the contract. The `loop_start`
  half of the original finding is now moot: loop compression was removed (#163/NH-21), so
  `_compress_macro` only ever appends `$FF` and never emits a raw `loop_start` operand into the
  macro byte stream. Confirm the instrument guard still fires at 32 (not 256) on every
  over-budget path and that no macro byte can exceed 255 without clamping.
- **Verify fix (#77, closed)**: a legitimate pitch/arp value of `0xFF`/`0xFE` can no longer
  collide with the End/Loop control bytes. `_encode_macro_offset` (`:71-84`) clamps every
  signed pitch/arp offset to `[-128, 127]` and then snaps the two colliding encodings away
  from the reserved bytes (`MACRO_CTRL_END = 0xFF`, `MACRO_CTRL_LOOP = 0xFE` at `:68-69`):
  `-1 (0xFF) -> 0x00`, `-2 (0xFE) -> 0xFD`. Confirm every pitch/arp encode site (note-start
  `:1117`/`:1121`, continuation `:1136`/`:1137`) routes through this helper rather than
  formatting a raw offset directly. #77 did NOT cover volume — see the next bullet.
- **Verify fix (#442/EXP-2026-08-21-7, closed)**: volume was the one macro value #77 left
  unguarded. Every in-pipeline producer clamps volume to 0-15, but the step-by-step `export`
  CLI accepts a user-editable frames JSON with no mask, and `vol_seq` bytes were emitted raw
  (unlike pitch/arp). A volume `>= 0xFE` as the FIRST byte of a macro collided with the
  reserved control bytes -- `0xFF` reads as end-at-step-0, silently playing the null default
  (15) instead of the value asked for; 16-253 emitted and were masked `& $0F` by the engine
  at write time (a different, silent-modulo failure mode). `vol` is now clamped to `[0, 15]`
  at collection time (matching `docs/AUDIO_BYTECODE_SPEC.md` §2.3's stated domain), so a
  `vol_seq` byte can never reach `0xFE`/`0xFF` in the first place -- no encode-time snap is
  needed the way pitch/arp's signed range requires one. Confirm the clamp still sits before
  `vol_seq` is appended (both the note-start and continuation sites) and that no future
  volume producer bypasses it.
- The `CMD_DMC_LEVEL` ($87) emitter was removed as a dead path (#72/D-09): no stage
  produces `dmc_level`, and grepping `exporter_ca65.py` for `$87`/`CMD_DMC_LEVEL` now
  turns up nothing. Note the engine (`nes/audio_engine.asm`) still contains an unreachable
  `@cmd_dmc_level` handler for it (and an unreachable `@cmd_dpcm_play` for `$85`) — that's
  dead-code tech debt on the engine side (see `/audit-tech-debt`), not an exporter bug; if
  DMC-level control is ever reintroduced here, confirm the emitted level is range-checked
  to the 7-bit $4011 domain (`docs/APU_DMC_REFERENCE.md`, 0–127).
- **Verify fix (nes-hardware #158, closed, touches this file)**: `note` is now clamped on
  *both* ends before it's baked into the bytecode stream and fed back into
  `midi_note_to_timer_value`: `elif note > 95: note = 95` (`:1082-1083`) and, for tone
  channels other than noise, `elif channel != 'noise' and 0 < note < 24: note = 24`
  (`:1084-1092`, added so the runtime base-period lookup and the pitch offset agree on the same note — a
  sub-C1 note previously produced `base_timer = 0` and a pitch offset that overflowed the
  11-bit timer). Confirm both clamps still hold.
- **Verify fix (#298, closed) — EXP-10**: the clamp is no longer silent. Tone-channel
  notes re-pitched by either clamp are counted (`:1099-1105`, keyed on the pre-clamp
  source note so a sustained note counts once and dpcm — whose "note" is a sample id — is
  excluded), tallied onto `self.notes_clamped = {'high':.., 'low':..}` (`:1308`), and
  reported with a one-line `⚠ N note(s) clamped to the NES tone range (24-95)…` summary at
  end of export (`:1310-1315`). Confirm the count still fires on both boundaries so an
  out-of-range song is surfaced rather than silently re-pitched — that counter is what
  moves this off the silent-clamp MEDIUM/CRITICAL boundary in the severity rubric.

Any out-of-range `.byte` = HIGH (won't assemble or wraps to a wrong value).

### Dimension 5: Bytecode-Spec Conformance
Cross-check the bytes `export_tables_with_patterns` emits against
`docs/AUDIO_BYTECODE_SPEC.md` §3 (the command table) and §2 (data structures):
- Length+note encoding: code emits `${(write_dur - 1) + 0x60:02X}, ${note:02X}`
  (`:1259`) with `write_dur = min(rem_dur, 32)` (`:1258`). Spec §3 Length Commands are
  `$60–$7F` = length `value-$60+1` (1–32 frames) — verify the cap of 32 and the `-1` bias
  match. **#369/EXP-2026-07-19-1 is CLOSED**: the "notes still fall in `$00–$5F`" half of
  this used to be unverified for DPCM specifically — DPCM's `note` (= `sample_id + 1`) was
  clamped only to the single-byte ceiling (255, citing #67's fix against the wrong
  tone-note collapse), not the `$00–$5F` dispatch range, so a DPCM `note` >= `$60`
  (`sample_id` >= 95) was misdispatched as a Length or Command byte by the engine's
  `@read_next`, desyncing the whole DPCM stream. `export_tables_with_patterns`
  (`exporter/exporter_ca65.py`, the DPCM branch of the per-frame clamp loop) now raises
  `ValueError` for `note >= 0x60` instead of emitting the out-of-range byte — the bytecode
  path supports at most 95 distinct DPCM samples per song (ids 0-94); `--no-patterns`
  (direct export) has no such ceiling. Verify-the-fix: confirm the guard still fires before
  any byte is written (not after), and that a legitimate DPCM note at the boundary
  (`sample_id` 94, `note` `$5F`) still exports cleanly rather than off-by-one rejecting it.
- **Verify fix (#83, closed) — EXP-07**: the doc/code gap on `$FE` is resolved. The
  exporter's *live* command set is `$80` (`CMD_INSTRUMENT`, matches spec §3), `$FE`+bank+
  ptr_lo+ptr_hi (a **sequence-level bank jump**, `:1239`), and the `$FF` end-of-stream
  terminator. `docs/AUDIO_BYTECODE_SPEC.md` §3 now carries an explicit `$FE CMD_BANK_JUMP`
  row documenting the sequence-level meaning and calling out that it is **distinct from**
  the in-macro `$FE, <offset>` loop control byte (§2.3, now marked reserved/not-
  implemented). Exporter (`:1239`) and engine (`nes/audio_engine.asm:416` `@cmd_bank_jump`)
  agree on the sequence-level meaning, so there is no runtime bug. The `$85 CMD_DPCM_PLAY`
  and `$87 CMD_DMC_LEVEL` rows still exist in §3, but each now notes the Python exporter
  does not emit them (DPCM triggers ride as note bytes; the `$87` emitter was removed, #72;
  see Dimension 4). Confirm the doc stays in sync rather than re-reporting the `$FE` gap.
- **Fixed (#163/NH-21, closed)**: NH-21 (nes-hardware audit) covered a macro-*runtime*
  `$FE` hazard — the old `_compress_macro` could emit loop-compressed macros (`$FE,
  loop_start`) that the shipped `EVAL_MACRO` routine (which only checks `$FF`) would
  misread as data. The fix removed loop compression entirely: `_compress_macro`
  (`:926-960`) now emits only `$FF`, so no `$FE` ever reaches a macro stream. This
  dimension's `$FE` concern is the sequence-level bank-jump command (now documented,
  above), which lives in a separate stream. No live `$FE` gap remains on either.
- Channel order and the `$FF` (end-of-stream) terminator per channel match the song-
  header pointer order in spec §2.1 (`pulse1, pulse2, triangle, noise, dpcm`).

### Dimension 6: Macro Emission
Per `docs/MACRO_USAGE_GUIDE.md` and `docs/AUDIO_BYTECODE_SPEC.md` §2.3, the four macro
kinds and the instrument-pointer table must be emitted correctly:
- `instrument_table` rows are `.word macro_vol_{v}, macro_arp_{a}, macro_pitch_{p},
  macro_duty_{d}` (`:1172`) — order must be Vol, Arp, Pitch, Duty (spec §2.2). Verified:
  the instrument tuple is built as `(vol_macros[v_seq], arp_macros[a_seq],
  pitch_macros[p_seq], duty_macros[d_seq])` (`:1108`/`:1163`) and unpacked as `v_id, a_id,
  p_id, d_id = inst` (`:1171`) in the same order — no transposition today. Re-check this on any
  future refactor of the instrument tuple; a transposed pair points an instrument at the
  wrong macro kind = wrong timbre (HIGH).
- Macro value domains (spec §2.3): Volume macros absolute 0–15; Arpeggio macros
  semitone offsets; Pitch macros timer offsets; all terminated by `$FF` (sustain).
  `_compress_macro` (`:926-960`) now performs sustain compression only — loop compression
  (`$FE,<offset>`) was removed (#163/NH-21), and §2.3 marks `$FE` reserved/not-implemented.
  The reserved-byte encoding from Dimension 4 (#77) still keeps data values out of
  `$FE`/`$FF`'s way. Confirm the index-0 `macro_*_0 = ($FF,)` null/sustain macro exists
  (the `{(0xFF,): 0}` dict seeds at `:1032-1039`, emitted at `:1178-1179`, spec §2.2
  `macro_null`).
- Macro dedup: the `vol_macros`/`duty_macros`/`arp_macros`/`pitch_macros` dicts dedupe by
  tuple — verify identical shapes collapse to one def (the guide's stated ROM-saving
  property) and that a `_compress_macro` round-trip can't change the played values
  (lossy macro compression that changes volume/pitch = CRITICAL per the severity rubric).
- **Fixed (#163/NH-21, closed)**: NH-21 found that the shipped `EVAL_MACRO` never decodes
  `$FE` inside a macro, so a loop-compressed macro would be misread as data. Rather than
  teach the engine to decode `$FE`, the fix removed loop compression from `_compress_macro`
  (`:926-960`) — every emitted macro is now sustain-encoded (`$FF`-terminated), which is a
  strict subset of what the engine decodes. This dimension only checks emission correctness
  against the spec's data-structure rules; don't re-report NH-21 as open.

### Dimension 7: Cross-Exporter Consistency
For the same `frames` input, NSF (`exporter/exporter_nsf.py`) and FamiStudio
(`exporter/exporter_famistudio.py`) should describe the same song the CA65 path
produces. (The old FamiTracker-text path — *exporter/exporter.py* +
*exporter/pattern_exporter.py* — was deleted as dead + frame-space-buggy, #101; neither
file exists in the repo anymore.) Check:
- **Verify fix (#81, closed)**: `NSFExporter.export()` and `export_nsf()`
  (`exporter/exporter_nsf.py:73-80`) now raise `NotImplementedError` with a message citing
  #81, instead of serializing channel data as JSON text embedded in the NSF binary. The
  `NSFHeader`/`NSFMacroPacker` classes remain as unused scaffolding for a future real
  implementation — confirm nothing calls them expecting working output, and that raising
  loudly (rather than writing a broken file) is preserved on any future change here.
- **Verify fix (#79, closed — see also Dimension 8)**: confirm no remaining call path
  reaches the NSF exporter from the CLI; `main.py`'s `export` subcommand only offers
  `--format ca65` today.
- Channel-set agreement: CA65 macro path handles `pulse1/pulse2/triangle/noise/dpcm`;
  `exporter_famistudio.py` iterates the identical five-channel list (`:150`) — confirmed
  consistent, no channel silently dropped.
- **Verify fix (#82, closed)**: `midi_note_to_famistudio` (`exporter_famistudio.py:164-
  170`) now clamps `octave = max(0, min(7, (note // 12) - 1))` (`:168`) into FamiStudio's
  valid 0–7 range (previously produced negative octaves for MIDI notes 0–11). The dpcm
  branch (`:102-111`) also now falls back to `max(0, event.get('note', 1) - 1)` when
  `event['sample_id']` is absent, instead of raising `KeyError` (the frames dict encodes
  DPCM triggers as `note = sample_id + 1`, not a `sample_id` key). Cross-check against
  `CA65Exporter.midi_note_to_timer_value`'s valid range (24–119, `exporter_ca65.py:46`) —
  confirm a note in range for one exporter is still in range (post-clamp) for the other,
  not silently re-pitched to a different octave than the ROM plays. **#370/
  EXP-2026-07-19-2 is CLOSED**: the tone-channel branch (`pulse1`/`pulse2`/`triangle`) had
  the same class of gap #82 fixed for dpcm but wasn't itself hardened — it read
  `event['note']`/`event['volume']` via direct subscript, raising `KeyError` on a frame
  dict missing either key, while the CA65 exporter tolerates it
  (`frame_data.get('note', 0)`/`.get('volume', 0)`). Now reads `event.get('note',
  0)`/`event.get('volume', 0)`, matching both the CA65 path and this file's own dpcm
  branch. Verify-the-fix: confirm no exporter still has a bare `event[...]`/`frame_data[...]`
  subscript for an optional frame field — grep is the fastest check.
- **Verify fix (#441/EXP-2026-08-21-3, closed)**: same divergence class as #370, one level
  up — key lookup instead of field lookup. `exporter_famistudio.py`'s per-frame loop now
  reads `events.get(str(frame), events.get(frame))`, mirroring `exporter_ca65.py`'s dual-key
  tolerance (`channel_frames.get(str(frame_idx), channel_frames.get(frame_idx))`,
  direct-export path). Both CA65 emitters have always accepted int OR str frame keys
  (in-memory frames carry int keys, JSON round-trips produce str keys); the FamiStudio path
  used to check only `str(frame) in events`, silently exporting nothing but `"... .."` rest
  rows for an int-keyed frames dict. Verify-the-fix: an int-keyed and a str-keyed frames
  dict for the same song produce byte-for-byte identical FamiStudio output.
- **Verify fix (#440/EXP-2026-08-21-2, closed)**: `generate_famistudio_txt`'s `PATTERN` keys
  and `SEQUENCE` references must agree on the same per-channel 0-based numbering for every
  channel, not just the first one processed. Full patterns are now keyed by a
  `channel_pattern_count` counter local to each channel's loop (incremented for both full and
  remainder patterns), replacing the old `len(patterns)` — a count across *every* channel's
  patterns emitted so far, which only coincided with the per-channel numbering `SEQUENCE`
  always uses for the first channel processed; every later channel's full-pattern keys landed
  on indices already claimed by earlier channels, so `SEQUENCE` referenced undefined (or
  wrong) `PATTERN`s for channel 2+. The remainder pattern's `LENGTH` is now the pattern's
  actual row count (`len(pattern_data)`) instead of a hardcoded `64`. Verify-the-fix: for a
  song with >=2 non-empty channels spanning >=64 frames, every `SEQUENCE` reference resolves
  to a defined `PATTERN` — `TestFamiStudioSequenceReferencesResolveToPatterns`
  (`tests/test_famistudio_export.py`) pins this structurally, since the file's prior tests
  only checked for `"PATTERNS"` presence (#339/REG-20), not internal consistency.
- This dimension overlaps `/audit-tech-debt` Dimension 1 (the exporters duplicating
  serialization). Report duplication there; report *behavioral divergence* here.

### Dimension 8: Format-String / CLI-Choices Mismatch
**Verify fix (#79, closed)**: `main.py`'s `export` subcommand now declares
`p_export.add_argument('--format', choices=['ca65'], default='ca65')` (`main.py:1296`),
with `nsf` intentionally absent (comment at `:1141` citing #79/#81) rather than
present-but-unreachable. `run_export` (`:499`) only branches on `if args.format ==
"ca65":` (`:519`) — the old `if args.format == "nsftxt":` dead branch (dispatching on a
string argparse never allowed) is gone (see comment at `:514-516`). Requesting
`--format nsf` now fails argparse validation up front with a clear CLI error instead of
silently no-op'ing. Check:
- No other dispatch site still assumes NSF export works. `run_config_validate`
  (`main.py:1510`) prints `f"NSF load address: 0x{config_manager.get('export.nsf.
  load_address'):04X}"` (`:1369`) under `--verbose` — this reads a `default_config.yaml` value with
  no live consumer (`NSFExporter` always raises `NotImplementedError`); confirm this is at
  worst cosmetic (LOW) and not advertised anywhere as a working feature.
- If NSF export is ever reintroduced, re-verify the new dispatch string exactly matches
  a value in `choices=[...]` — this is precisely the class of bug #79 was.

### Dimension 9: Multi-Song Jukebox Export (`export_song_bank_bytecode`)
New in #30/F-13 and the youngest exporter surface — audit it as new code, not as a
verify-the-fix pass. `CA65Exporter.export_song_bank_bytecode(songs, output_path)`
(`exporter/exporter_ca65.py:1548`) writes the `music.asm` for a `song build` ROM by
calling the shared `_build_song_bytecode` helper once per song. Its first audit pass
found a defect that corrupted every song after the first (EXP-2026-08-07-1, fixed in
`8ea7ac3`); assume more.

- **Segment discipline across songs (the closed bug — verify it holds).**
  `_build_song_bytecode` ends each song inside a dynamically-banked `BANK_NN` segment,
  so it must re-declare `.segment "CODE_8000"` before emitting the next song's
  instrument/macro tables — otherwise song N+1's tables land in a swapped-out window
  while `EVAL_MACRO` reads them from the fixed always-mapped bank. This **still links
  and still passes ROM structural diagnostics** (valid vectors, APU init present), which
  is exactly why it went undetected: the feature's own "verified with a real CC65 build"
  check never inspected per-song symbol placement. Verify-the-fix: any check for this
  class of bug must resolve actual symbol addresses (`ld65 --dbgfile`, confirming
  `song1_instrument_table` lands inside `CODE_8000`'s `$8000` window, not a `$C000`-range
  dynamic bank) — a build that merely succeeds proves nothing here. Treat a regression as
  CRITICAL (silent song corruption).
- **Symbol namespacing.** Every symbol a song defines is prefixed `song{i}_`
  (`:1593`). Grep the emitted output for any un-prefixed definition inside a per-song
  block — one collision silently merges two songs' tables at link time.
- **Shared vs per-song data.** Pulse/triangle period tables are emitted **once**
  (`_emit_period_tables`, `:1071`) because they are pure hardware constants; instrument
  and macro tables are per-song with **no cross-song dedup**. Verify nothing that
  legitimately varies per song got hoisted into the shared emission, and that the
  no-dedup choice is a size cost only, never a correctness one.
- **`song_table` indexing.** Three parallel byte arrays (`song_table_ptr_lo`/`_hi`/
  `song_table_bank`, `:1636-1641`) are indexed `song_index * 5 + channel` with channel
  order fixed by `SEQUENCE_CHANNELS` (`:1069`). The consumer is
  `load_song_streams_indexed` in `nes/audio_engine.asm`. Verify the stride constant, the
  channel order, and the `song_count` byte all match on both sides — a stride mismatch
  plays song A's pulse2 stream as song B's triangle, which sounds like corruption rather
  than an obvious failure. **#426 is CLOSED**: that index is 8-bit accumulator/Y-register
  math on the engine side, so `song_index*5+channel` silently wraps past index 255 — the
  highest valid `song_index` is `(255-4)//5 = 50`, i.e. 51 songs. `export_song_bank_bytecode`
  (`:1742-1759`) now computes that same `max_songs` bound and raises `ValueError` before
  emitting a 52nd+ song, rather than letting it wrap and play the wrong streams on the wrong
  channels with every downstream gate (bank pool, CC65, ROM validation) still passing.
  Verify-the-fix: the 51-song bound stays derived from `len(SEQUENCE_CHANNELS)` rather than
  a hardcoded `51`, so it can't silently drift if a channel is ever added or removed.
- **`song_instrument_ptr_*` is per-song, not per-channel** (`:1650-1653`) — one entry per
  song, unlike the `song_table_*` arrays. Confirm the engine indexes it with the song
  index alone (no `* 5`).
- **Bank pool exhaustion across N songs.** `next_bank` threads from song to song and each
  song starts in a fresh bank (never packing two songs into one `BANK_NN`, since
  `bytes_in_current_bank` accounting is per-call). Verify the `MAX_SEQUENCE_BANK` guard
  fires on the cumulative count, and that the per-song rounding waste is accounted for by
  the `check_mapper_capacity` pre-flight in `main.py:run_song_build`.
- **Empty input.** `songs == []` raises `ValueError` (`:1571-1572`) rather than emitting a
  degenerate `song_count: .byte $00`. Verify the caller surfaces it as a clean CLI error.

## Cross-Dimension Dedup
A single root cause can surface across dimensions (an out-of-range `.byte` is both a
byte-range bug (D4) and a spec-conformance bug (D5)). Report it once, in the most
actionable dimension, and cross-reference. Run the `_audit-common.md` dedup protocol
(`gh issue list` + scan `docs/audits/`) before filing each finding.

## Output
Write to: **`docs/audits/AUDIT_EXPORTERS_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — counts per severity and per dimension; the 3 highest-impact findings
   (default-pipeline CA65 path first).
2. **Findings** — base format from `.claude/commands/_audit-common.md` + the
   `Dimension` and `Spec ref` fields above.

Then suggest:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_<TODAY>.md
```
