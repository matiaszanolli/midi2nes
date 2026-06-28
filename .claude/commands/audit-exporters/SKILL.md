---
description: "Audit output exporters — CA65/NSF/FamiTracker assembly and bytecode correctness"
argument-hint: "[--focus <dims>]"
---

# Exporters Audit

Audit the output-format generators in `exporter/` — the stage that turns the
`frames` dict into something a build toolchain or external tracker consumes. The
default `python main.py input.mid output.nes` run goes through the CA65 path
(`exporter/exporter_ca65.py` → `music.asm` → `nes/project_builder.py` → CC65), so
that path carries the most weight; NSF and FamiTracker are secondary outputs that
must stay consistent with it for the same input.

Shared protocol: `.claude/commands/_audit-common.md` — read the **export contract**
(`export → CA65Exporter.export_tables_with_patterns(frames, patterns, references, output_path)`
writes `music.asm`), the inter-stage data contracts, and the dedup/finding format
there. The bytecode this stage must emit is specified in `docs/AUDIO_BYTECODE_SPEC.md`
and the macro semantics in `docs/MACRO_USAGE_GUIDE.md` — treat both as the target the
6502 engine plays back. Severity rubric: `.claude/commands/_audit-severity.md`. Do not
restate either file; apply them.

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
  referenced from `instrument_table` `.word` rows all exist.
- Segments emitted (`CODE_8000`, `BANK_{NN}`, `DPCM`, and in `export_direct_frames`
  `HEADER`/`ZEROPAGE`/`BSS`/`RODATA`/`CODE`/`VECTORS`) are all declared in the linker
  config `nes/project_builder.py` writes — a segment the exporter emits but `nes.cfg`
  has no MEMORY/SEGMENT for is a link failure. Cross-check `docs/MAPPER_MMC3_REFERENCE.md`.
- `.importzp ptr1, temp1, temp2, frame_counter` (pattern path) vs
  `.importzp frame_counter, temp_ptr` (direct path): confirm the importing names are
  exported/`.global`'d by `nes/project_builder.py`'s `main.asm`. A mismatched zeropage
  symbol is a link failure.
- The `non-standalone` branch emits `.import audio_init, audio_update` and jumps to
  them — confirm those exist in the engine the builder ships.
- `.byte $FE, ${next_bank:02X}, <{label}, >{label}` bank-jump lines: the forward label
  is defined in the next `BANK_{NN}` segment in the same file — verify it always is.

A label/segment that fails to assemble or link = HIGH (wrong output on every ROM
through this path).

### Dimension 2: APU Register Serialization Correctness
`export_direct_frames` writes literal APU stores (`sta $4000`/`$4002`/`$4003` for
pulse1, `$4004`–`$4007` pulse2, `$4008`/`$400A`/`$400B` triangle). The named
constants `APU_PULSE1_CTRL`…`APU_STATUS` at the top of `exporter/exporter_ca65.py`
define $4000–$4015. Check:
- Each channel writes its own register block, not another channel's (off-by-$4 bugs).
- The triangle path never writes a duty/volume-shaped control byte — triangle has no
  volume or duty (`docs/APU_TRIANGLE_REFERENCE.md`). Note `export_direct_frames` builds
  triangle `control` as `0x80 | (volume * 7)`; confirm that targets the linear-counter
  semantics ($4008) and is not treated as a pulse volume nibble.
- `ora #$08` before the timer-hi store sets the length-counter reload bit — confirm
  that is the intended $4003/$4007/$400B bit per `docs/APU_LENGTH_COUNTER_REFERENCE.md`.
- `$4015` channel-enable and `$4017` frame-counter init in the standalone reset and the
  `init_music` block match `docs/NES_APU_REFERENCE.md` / `docs/APU_FRAME_COUNTER_REFERENCE.md`.
- The `NSFExporter` `add_init_routine` / `_generate_play_routine` in
  `exporter/exporter_nsf.py` hand-assemble opcodes — verify the `STA $4000,X` / `CPX #$0F`
  loop actually targets $4000–$400F and the `BNE`/`BEQ` branch offsets are correct (a
  wrong relative offset is silently broken machine code).

Wrong register address or triangle driven with volume/duty = HIGH.

### Dimension 3: Pattern-vs-Empty Export Paths
`run_export` in `main.py` calls `export_tables_with_patterns` with `patterns={}` when
no `--patterns` file is given, and `export_tables_with_patterns` early-returns to
`export_direct_frames` when `not patterns`. So there are **two completely different
emitters** (literal frame tables vs macro bytecode) selected by truthiness of
`patterns`. Check:
- Both paths produce assembly the same `nes/project_builder.py` can build — they emit
  *different* segments and *different* exported symbols (the direct path has no
  `*_sequence`/`instrument_table`; the macro path has no `*_note`/`*_control` tables).
  If the builder/engine expects one shape, the other path is silently broken. This is at
  least HIGH; if the builder accepts it but the song is wrong, CRITICAL.
- `export_tables_with_patterns` ignores its `references` argument entirely after the
  early return (grep: `references` is a parameter but the macro path re-derives events
  from `frames`). Confirm whether pattern/reference compression is actually applied or
  whether "pattern mode" silently expands everything — a mismatch with the
  `compression_ratio` reported upstream is misleading (MEDIUM) or, if it changes the
  song vs the detected patterns, CRITICAL.
- The empty-patterns path is the default `python main.py input.mid out.nes` run — a
  regression there hits every user.

### Dimension 4: Byte-Range Safety (no value >255 or negative emitted)
Every `.byte ${val:02X}` must receive 0–255; `.word` rows must receive valid 16-bit
labels. Hunt for values that can exceed a byte without clamping in
`exporter/exporter_ca65.py`:
- `f'    .byte $80, ${inst_id:02X} ; CMD_INSTRUMENT'` — `inst_id` is `len(instrument_defs)`
  growth; a song with >255 unique instruments emits `${256:02X}` = `$100` (3 hex digits),
  which `ca65` rejects or truncates. Same risk for the macro-pool indices in
  `instrument_table` `.word` rows if a macro id is used as a raw byte anywhere.
- `_compress_macro` emits `[0xFE, loop_start]` where `loop_start` is a raw frame index —
  a macro longer than 255 frames emits an out-of-range loop byte. Same for the sustain/
  loop control bytes colliding with real data values (a legitimate volume/pitch value of
  `0xFF`/`0xFE` would be read as End/Loop — confirm the value domains can't reach the
  control bytes).
- `dmc_level` in `.byte $87, ${event["dmc_level"]:02X}` — confirm `dmc_level` is range-
  checked to a DMC load value (`docs/APU_DMC_REFERENCE.md`, $4011 is 7-bit, 0–127).
- `pitch_offset` is masked `& 0xFF` after clamping to ±127 — verify the engine reads it
  as signed (a `& 0xFF` of a negative is fine only if the 6502 side treats it as two's
  complement; `docs/AUDIO_BYTECODE_SPEC.md` §2.3 says pitch macros are offsets).
- `note` clamped to `note > 95 → 95`; spec note range is `$00–$5F` (0–95). 95 = `$5F`,
  in range — but confirm the clamp is silent (a dropped/retuned high note changes the
  song; a *silent* clamp on common input could be CRITICAL, a logged one is MEDIUM).

Any out-of-range `.byte` = HIGH (won't assemble or wraps to a wrong value).

### Dimension 5: Bytecode-Spec Conformance
Cross-check the bytes `export_tables_with_patterns` emits against
`docs/AUDIO_BYTECODE_SPEC.md` §3 (the command table) and §2 (data structures):
- Length+note encoding: code emits `${(write_dur - 1) + 0x60:02X}, ${note:02X}` with
  `write_dur = min(rem_dur, 32)`. Spec §3 Length Commands are `$60–$7F` = length
  `value-$60+1` (1–32 frames) — verify the cap of 32 and the `-1` bias match, and that
  notes still fall in the `$00–$5F` note range so the engine doesn't read a note as a
  length/command.
- Command opcodes: code emits `$80` (CMD_INSTRUMENT — matches spec), `$87` for DMC
  level, and `$FE`+bank+ptr for a **bank jump**. But spec §3 defines DPCM as `$85`
  (`CMD_DPCM_PLAY`) and song jump as `$84` (`CMD_JUMP`); `$FE` in spec §2.3 is the
  **macro loop** control byte, and there is no `$87` or bank-jump opcode documented.
  Flag every emitted opcode that has no spec entry or contradicts one — the engine and
  the doc must agree on what `$FE`/`$87` mean, or playback is wrong (HIGH; CRITICAL if
  it silently changes the song). Confirm by reading the actual engine source the builder
  ships before asserting.
- Channel order and the `$FF` (end-of-stream) terminator per channel match the song-
  header pointer order in spec §2.1 (`pulse1, pulse2, triangle, noise, dpcm`).

### Dimension 6: Macro Emission
Per `docs/MACRO_USAGE_GUIDE.md` and `docs/AUDIO_BYTECODE_SPEC.md` §2.3, the four macro
kinds and the instrument-pointer table must be emitted correctly:
- `instrument_table` rows are `.word macro_vol_{v}, macro_arp_{a}, macro_pitch_{p}, macro_duty_{d}`
  — order must be Vol, Arp, Pitch, Duty (spec §2.2). Note `export_tables_with_patterns`
  builds the instrument tuple as `(vol, arp, pitch, duty)` but indexes `inst` as
  `(vol_macros[v_seq], arp_macros[a_seq], pitch_macros[p_seq], duty_macros[d_seq])` and
  unpacks `v_id, a_id, p_id, d_id` — verify the macro-def list it appends to and the
  index it stores stay in the same order (a transposed pair points an instrument at the
  wrong macro kind = wrong timbre, HIGH).
- Macro value domains (spec §2.3): Volume macros absolute 0–15; Arpeggio macros
  semitone offsets; Pitch macros timer offsets; all terminated by `$FF` (sustain) or
  `$FE,<offset>` (loop). Confirm `_compress_macro`'s `$FF`/`$FE` insertion matches and
  that the index-0 `macro_*_0 = ($FF,)` null/sustain macro exists (spec §2.2 `macro_null`).
- Macro dedup: the `vol_macros`/`duty_macros`/`arp_macros`/`pitch_macros` dicts dedupe by
  tuple — verify identical shapes collapse to one def (the guide's stated ROM-saving
  property) and that a `_compress_macro` round-trip can't change the played values
  (lossy macro compression that changes volume/pitch = CRITICAL per the severity rubric).

### Dimension 7: Cross-Exporter Consistency
For the same `frames` input, NSF (`exporter/exporter_nsf.py`), FamiTracker
(`exporter/exporter.py` `generate_famitracker_txt_with_patterns` +
`exporter/pattern_exporter.py`), and FamiStudio (`exporter/exporter_famistudio.py`)
should describe the same song the CA65 path produces. Check:
- `NSFExporter._serialize_compressed_data` serializes channel data as **JSON text**
  embedded in the NSF binary (`json.dumps(...).encode('utf-8')`) — that is not 6502-
  executable data; flag whether the NSF output is actually a playable NSF or a stub
  (the `NSFMacroPacker` docstring calls itself "Draft logic … will eventually replace
  the JSON-based serialization"). A format that claims to be NSF but can't play = HIGH.
- Channel-set agreement: CA65 macro path handles `pulse1/pulse2/triangle/noise/dpcm`;
  FamiTracker path (`exporter/exporter.py`) only emits note+vol with `COLUMNS 1 1 1 1 1`
  — confirm it doesn't silently drop channels the CA65 path keeps.
- Note/volume conversion: `midi_note_to_famistudio` / `midi_note_to_ft` octave math vs
  `CA65Exporter.midi_note_to_timer_value` valid range (24–119). A note in range for one
  exporter and silently dropped/mis-octaved in another is an inconsistency (MEDIUM,
  HIGH if a common note is dropped).
- This dimension overlaps `/audit-tech-debt` Dimension 1 (the four exporters duplicating
  serialization). Report duplication there; report *behavioral divergence* here.

### Dimension 8: Format-String / CLI-Choices Mismatch
`main.py` `run_export` branches on `args.format`. The argparse parser declares
`p_export.add_argument('--format', choices=['nsf', 'ca65'], default='ca65')`, but
`run_export` checks `if args.format == "nsftxt":` for the NSF branch. Since `"nsftxt"`
is **not** an allowed choice, the NSF branch is **unreachable** and `--format nsf`
falls through to the `elif args.format == "ca65":` — verify this and trace what
`--format nsf` actually does (likely nothing, or the ca65 branch). A format the CLI
advertises that silently does the wrong thing (or nothing) is HIGH. Also confirm no
other dispatch site (`config` defaults at `main.py` line ~721 references
`export.nsf.load_address`) assumes NSF export works. Re-read both the argparse
definition and `run_export` before reporting — confirm the exact string mismatch.

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
