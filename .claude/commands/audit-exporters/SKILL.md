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
- **Dimension**: one of the 8 below.
- **Spec ref**: cite `docs/AUDIO_BYTECODE_SPEC.md` / `docs/MACRO_USAGE_GUIDE.md` section, or the consumer (`nes/project_builder.py`) for emitted-format claims.

## Dimensions

### Dimension 1: CA65 Assembly Well-Formedness & Builder Compatibility
The text `export_tables_with_patterns` and `export_direct_frames` write in
`exporter/exporter_ca65.py` must assemble under `ca65` and link under the config
`nes/project_builder.py` generates. Skeptical checklist:
- Every label referenced is defined: the `.export` line (`pulse1_sequence`,
  `pulse2_sequence`, `triangle_sequence`, `noise_sequence`, `dpcm_sequence`,
  `ntsc_period_low`, `ntsc_period_high`, `instrument_table`, the `dpcm_*_table`s)
  has a matching definition; `macro_vol_*`/`macro_arp_*`/`macro_pitch_*`/`macro_duty_*`
  referenced from `instrument_table` `.word` rows (`exporter_ca65.py:1172`) all exist.
- Segments emitted (`CODE_8000`, `BANK_{NN}`, `DPCM`, and in `export_direct_frames`
  `HEADER`/`ZEROPAGE`/`BSS`/`RODATA`/`CODE`/`VECTORS`) are all declared in the linker
  config `nes/project_builder.py` writes — a segment the exporter emits but `nes.cfg`
  has no MEMORY/SEGMENT for is a link failure. Cross-check `docs/MAPPER_MMC3_REFERENCE.md`.
- `.importzp ptr1, temp1, temp2, frame_counter` (pattern path, `:981`) vs
  `.importzp frame_counter, temp_ptr` (direct path, `:228`): confirm the importing names
  are exported/`.global`'d by `nes/project_builder.py`'s `main.asm`. A mismatched zeropage
  symbol is a link failure.
- The `non-standalone` branch (`:1270-1279`) emits `.import audio_init, audio_update` and
  jumps to them — confirm those exist in the engine the builder ships.
- `.byte $FE, ${next_bank:02X}, <{label}, >{label}` bank-jump lines (`:1239`): the forward
  label is defined in the next `BANK_{NN}` segment in the same file (`:1238`) — verify
  it always is, including when `MAX_SEQUENCE_BANK` is reached (the code now raises
  `ValueError` instead of silently overflowing the bank budget, `:1229-1237` — confirm this
  guard still fires for every over-budget path, not just this one call site).

A label/segment that fails to assemble or link = HIGH (wrong output on every ROM
through this path).

### Dimension 2: APU Register Serialization Correctness
`export_direct_frames` writes literal APU stores (`sta $4000`/`$4002`/`$4003` for
pulse1, `$4004`–`$4007` pulse2, `$4008`/`$400A`/`$400B` triangle). The named
constants `APU_PULSE1_CTRL`…`APU_STATUS` at the top of `exporter/exporter_ca65.py`
(`:6-29`) define $4000–$4015. Check:
- Each channel writes its own register block, not another channel's (off-by-$4 bugs).
- The triangle path never writes a duty/volume-shaped control byte — triangle has no
  volume or duty (`docs/APU_TRIANGLE_REFERENCE.md`). Note `export_direct_frames` builds
  triangle `control` as `0x80 | (volume * 7)` (`:346`); confirm that targets the
  linear-counter semantics ($4008) and is not treated as a pulse volume nibble.
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
- **Verify fix (#80, closed) — EXP-04**: the `.byte $80, ${inst_id:02X} ; CMD_INSTRUMENT`
  operand at `:1251` can no longer widen past two hex digits. `inst_id` is now assigned by
  the static helper `_register_instrument` (`:905-924`, called at `:1109`/`:1164`), which
  raises `ValueError` when `len(instrument_defs) > 0xFF` (guard at `:916`) instead of
  handing back a 3-hex-digit id for a song with >256 unique (vol,arp,pitch,duty) tuples.
  The `loop_start` half of the original finding is now moot: loop compression was removed
  (#163/NH-21), so `_compress_macro` (`:926-960`) only ever appends `$FF` and never emits a
  raw `loop_start` operand into the macro byte stream (formatted `${val:02X}` at `:1179`).
  Confirm the instrument guard still fires on every over-budget path and that no macro byte
  can exceed 255 without clamping.
- **Verify fix (#77, closed)**: a legitimate volume/pitch/arp value of `0xFF`/`0xFE` can no
  longer collide with the End/Loop control bytes. `_encode_macro_offset` (`:71-84`) clamps
  every signed pitch/arp offset to `[-128, 127]` and then snaps the two colliding
  encodings away from the reserved bytes (`MACRO_CTRL_END = 0xFF`, `MACRO_CTRL_LOOP =
  0xFE` at `:68-69`): `-1 (0xFF) -> 0x00`, `-2 (0xFE) -> 0xFD`. Confirm every pitch/arp
  encode site (note-start `:1117`/`:1121`, continuation `:1136`/`:1137`) routes through
  this helper rather than formatting a raw offset directly.
- The `CMD_DMC_LEVEL` ($87) emitter was removed as a dead path (#72/D-09): no stage
  produces `dmc_level`, and grepping `exporter_ca65.py` for `$87`/`CMD_DMC_LEVEL` now
  turns up nothing. Note the engine (`nes/audio_engine.asm`) still contains an unreachable
  `@cmd_dmc_level` handler for it (and an unreachable `@cmd_dpcm_play` for `$85`) — that's
  dead-code tech debt on the engine side (see `/audit-tech-debt`), not an exporter bug; if
  DMC-level control is ever reintroduced here, confirm the emitted level is range-checked
  to the 7-bit $4011 domain (`docs/APU_DMC_REFERENCE.md`, 0–127).
- **Verify fix (nes-hardware #158, closed, touches this file)**: `note` is now clamped on
  *both* ends before it's baked into the bytecode stream and fed back into
  `midi_note_to_timer_value`: `elif note > 95: note = 95` (`:1075-1076`) and, for tone
  channels other than noise, `elif channel != 'noise' and 0 < note < 24: note = 24`
  (`:1077-1085`, added so the runtime base-period lookup and the pitch offset agree on the same note — a
  sub-C1 note previously produced `base_timer = 0` and a pitch offset that overflowed the
  11-bit timer). Confirm both clamps still hold and that a clamped note is at least
  logged/counted somewhere upstream — a silent clamp on common input is the boundary
  between MEDIUM and CRITICAL per the severity rubric.

Any out-of-range `.byte` = HIGH (won't assemble or wraps to a wrong value).

### Dimension 5: Bytecode-Spec Conformance
Cross-check the bytes `export_tables_with_patterns` emits against
`docs/AUDIO_BYTECODE_SPEC.md` §3 (the command table) and §2 (data structures):
- Length+note encoding: code emits `${(write_dur - 1) + 0x60:02X}, ${note:02X}`
  (`:1259`) with `write_dur = min(rem_dur, 32)` (`:1258`). Spec §3 Length Commands are
  `$60–$7F` = length `value-$60+1` (1–32 frames) — verify the cap of 32 and the `-1` bias
  match, and that notes still fall in the `$00–$5F` note range so the engine doesn't read
  a note as a length/command.
- **Verify fix (#83, closed) — EXP-07**: the doc/code gap on `$FE` is resolved. The
  exporter's *live* command set is `$80` (`CMD_INSTRUMENT`, matches spec §3), `$FE`+bank+
  ptr_lo+ptr_hi (a **sequence-level bank jump**, `:1239`), and the `$FF` end-of-stream
  terminator. `docs/AUDIO_BYTECODE_SPEC.md` §3 now carries an explicit `$FE CMD_BANK_JUMP`
  row documenting the sequence-level meaning and calling out that it is **distinct from**
  the in-macro `$FE, <offset>` loop control byte (§2.3, now marked reserved/not-
  implemented). Exporter (`:1239`) and engine (`nes/audio_engine.asm:266` `@cmd_bank_jump`)
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
  not silently re-pitched to a different octave than the ROM plays.
- This dimension overlaps `/audit-tech-debt` Dimension 1 (the exporters duplicating
  serialization). Report duplication there; report *behavioral divergence* here.

### Dimension 8: Format-String / CLI-Choices Mismatch
**Verify fix (#79, closed)**: `main.py`'s `export` subcommand now declares
`p_export.add_argument('--format', choices=['ca65'], default='ca65')` (`main.py:1143`),
with `nsf` intentionally absent (comment at `:1141` citing #79/#81) rather than
present-but-unreachable. `run_export` (`:499`) only branches on `if args.format ==
"ca65":` (`:519`) — the old `if args.format == "nsftxt":` dead branch (dispatching on a
string argparse never allowed) is gone (see comment at `:514-516`). Requesting
`--format nsf` now fails argparse validation up front with a clear CLI error instead of
silently no-op'ing. Check:
- No other dispatch site still assumes NSF export works. `run_config_validate`
  (`main.py:1357`) prints `f"NSF load address: 0x{config_manager.get('export.nsf.
  load_address'):04X}"` (`:1369`) under `--verbose` — this reads a `default_config.yaml` value with
  no live consumer (`NSFExporter` always raises `NotImplementedError`); confirm this is at
  worst cosmetic (LOW) and not advertised anywhere as a working feature.
- If NSF export is ever reintroduced, re-verify the new dispatch string exactly matches
  a value in `choices=[...]` — this is precisely the class of bug #79 was.

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
