# NES Hardware Correctness Audit — 2026-07-03

Audit of the boundary where Python numeric values become APU register writes, across the
10 hardware dimensions defined in `.claude/commands/audit-nes-hardware/SKILL.md`, at HEAD
`9cfa0e2`. Hot files: `nes/emulator_core.py`, `nes/pitch_table.py`,
`nes/envelope_processor.py`, `exporter/exporter_ca65.py`, `nes/audio_engine.asm`,
`nes/project_builder.py`, plus `tracker/track_mapper.py` and
`dpcm_sampler/enhanced_drum_mapper.py` (upstream producers whose output shape this audit's
hot files assume).

**Purpose of this pass.** Per the SKILL note, NH-01..NH-10 and NH-15..NH-20 were
previously fixed; this audit (a) re-verifies those fixes hold at HEAD, including under
edge cases the closing commits may not have covered, and (b) continues hunting the
still-open set (NH-11, NH-14, NH-21..NH-25) plus anything new.

**Dedup sources:** `gh issue list --repo matiaszanolli/midi2nes --limit 200` (`/tmp/audit/issues.json`,
179 issues), all prior reports in `docs/audits/`, especially
`AUDIT_NES_HARDWARE_2026-07-01.md` (the immediately preceding pass on this exact
dimension set), `AUDIT_DPCM_2026-06-29.md`, and `AUDIT_TECH_DEBT_2026-06-29.md`.

## Regression check — closed NH fixes re-verified at HEAD

| Issue | Fix | Verified |
|---|---|---|
| #158 NH-16 | `midi_note_to_timer_value` clamps `24–119` instead of returning 0 (`exporter/exporter_ca65.py:51`) | **Holds** |
| #159 NH-17 | `@end_of_stream` sets `current_note,x=0` and falls into `@silence` every frame (`nes/audio_engine.asm:570-576`) | **Holds** |
| #161 NH-18 | `last_written_hi` cache gates `$4003`/`$4007` writes; forced rewrite on genuine new note via `lda #$FF; sta last_written_hi,x` in `@is_note` (`nes/audio_engine.asm:298-303,412-421,451-460`) | **Holds** |
| #162 NH-19 | `NOISE_DECAY_FRAMES = 6` software volume ramp per hit, re-trigger truncates (`nes/emulator_core.py:158-186`) | **Holds** |
| #160 NH-20 | Note-off pairing added to `compile_channel_to_frames` (`nes/emulator_core.py:76-94`); `track_mapper.split_polyphonic_track`/multi-track pulse1+triangle passthrough keep note-offs | **Holds for pulse1/triangle direct-copy and the single-track split path — does NOT hold for pulse2/harmony in the multi-track path; see NH-27 below** |
| #38 NH-10 | Dead duplicate `NESEmulatorCore` + unclamped vibrato removed (`nes/envelope_processor.py` now only defines `EnvelopeProcessor`) | **Holds** (confirmed no `NESEmulatorCore` in this file) |
| #34 NH-08 | Single clean pulse-volume expression, `max(1, int(15*pow(v/127,1.5)))` | **Holds** (`nes/emulator_core.py:112,118`) |
| #108 NH-15 | `PULSE_DUTY_CYCLES` / `audio_constants.py` removed | **Holds** (no hits repo-wide) |

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 1 |
| HIGH     | 1 |
| MEDIUM   | 0 |
| LOW      | 2 |
| **Total NEW** | **4** |

Plus 7 existing open findings re-verified unchanged (not re-counted): #41/NH-11,
#107/NH-14, #163/NH-21, #164/NH-22, #165/NH-23, #166/NH-24, #167/NH-25.

### Highest-risk hardware divergence

**NH-26 (CRITICAL)** — Any drum hit that the DPCM sample resolver can't match a sample
name for (per `AUDIT_DPCM_2026-06-29.md` D-10, this is the *common* case with the default
`ADVANCED_MIDI_DRUM_MAPPING`) falls back to a `noise_events` entry that carries no
`'note'` key. `NESEmulatorCore.process_all_tracks`'s noise branch unconditionally reads
`e['note']`, so the `frames` pipeline stage crashes with an unhandled `KeyError` on any
MIDI file containing typical percussion. This is not a wrong-pitch or wrong-volume bug —
it stops ROM generation outright, with no workaround short of stripping drums from the
source MIDI.

---

## Findings

### NH-26: Drum noise-fallback events lack a `note` key — crashes `process_all_tracks` on common drum input
- **Severity**: CRITICAL
- **Dimension**: 3 (Noise period/mode) + 10 (inter-stage contract)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:307-311` (`noise_events.append({"frame": frame, "velocity": velocity})` — no `note` key), consumed at `nes/emulator_core.py:165` (`period = max(1, self.midi_to_nes_pitch(e['note'], 'noise'))`); reached via `tracker/track_mapper.py:243-249` (`nes_tracks['noise'] = noise_events`)
- **Status**: NEW
- **Description**: `EnhancedDrumMapper.map_drums` resolves each drum hit to a DPCM
  sample name via `_resolve_dpcm_sample_name`; when that returns falsy (no matching
  sample — per `AUDIT_DPCM_2026-06-29.md` D-10 this is the default-mapping norm for
  everything except kick/snare, and even those miss because the velocity-split sample
  names the advanced map requests aren't in the shipped `dpcm_index.json`), the hit is
  appended to `noise_events` as `{"frame": frame, "velocity": velocity}` — **no `note`
  field**. `assign_tracks_to_nes_channels` routes this list straight into
  `nes_tracks['noise']` (when the noise channel isn't already claimed by another track).
  `process_all_tracks`'s noise branch (added when NH-01/#9 was fixed) assumes every
  noise event carries a MIDI `note` to convert to a period index via
  `self.midi_to_nes_pitch(e['note'], 'noise')` — an assumption the drum-mapper fallback
  never satisfies. The dict access raises `KeyError: 'note'` with no guard anywhere on
  the path, so the exception propagates out of the `frames` pipeline stage (and the
  single-command `run_full_pipeline`), aborting the entire build.
- **Evidence**: Minimal reproduction against HEAD:
  ```python
  from nes.emulator_core import NESEmulatorCore
  core = NESEmulatorCore()
  nes_tracks = {
      'pulse1': [], 'pulse2': [], 'triangle': [],
      'noise': [{'frame': 10, 'velocity': 90}],  # exact shape enhanced_drum_mapper emits
      'dpcm': [],
  }
  core.process_all_tracks(nes_tracks)
  ```
  ```
  Traceback (most recent call last):
    File "nes/emulator_core.py", line 165, in process_all_tracks
      period = max(1, self.midi_to_nes_pitch(e['note'], 'noise'))
  KeyError: 'note'
  ```
  Also reproduces end-to-end through `tracker.track_mapper.assign_tracks_to_nes_channels`
  with a synthetic 2-track MIDI event dict containing a percussion-shaped track (the
  drum-fallback path fires and populates `nes_tracks['noise']` with note-less dicts,
  which then blow up at the `frames` step).
- **Impact**: Any MIDI file with a percussion track that the shipped DPCM index doesn't
  fully cover — i.e. essentially any real-world drummed song under the default
  `use_advanced=True` mapping, per D-10's finding that toms/cymbals and even velocity-split
  kick/snare miss the index — crashes `main.py` (both the full pipeline and the `frames`
  subcommand) before any ROM is produced. No workaround except manually stripping
  percussion from the source MIDI or supplying a DPCM index that happens to resolve every
  used drum note. Blast radius: every song with typical GM percussion, legacy (non
  `--arranger`) front-end — the arranger path uses a different voice-allocation flow and
  was not observed to hit this exact call site, but was not exhaustively re-audited here.
- **Related**: D-10/D-11 (`AUDIT_DPCM_2026-06-29.md` — established the fallback triggers
  on nearly all drums and can be silently dropped when noise is already claimed; neither
  finding noticed the missing `note` key crashes the *consumer*), closed #9/NH-01 (added
  the noise-branch consumer that introduced this assumption).
- **Hardware ref**: `docs/APU_NOISE_REFERENCE.md` §3 (`$400E` needs a period index derived
  from a note/pitch — there is no register-level concept of a "note-less noise hit"; the
  contract `process_all_tracks` was written against requires one).
- **Suggested Fix**: Either have `enhanced_drum_mapper.py`'s noise fallback carry a
  sensible default `note` (e.g. the GM drum's own MIDI note, which is already in scope at
  the append site as `midi_note`), or make `process_all_tracks`'s noise branch tolerate a
  missing `note` with `e.get('note')` and a documented default period/mode instead of a
  bare `e['note']`.

### NH-27: NH-20's duration fix does not cover the harmony (`pulse2`) channel on multi-track MIDI — every chord/harmony note is still capped at 4 frames
- **Severity**: HIGH
- **Dimension**: 8 (frame model / note duration)
- **Location**: `tracker/track_mapper.py:225-228` (`nes_tracks['pulse2'] = apply_arpeggio_fallback(midi_events[ch], style="default")`), `tracker/track_mapper.py:10-17` (`group_notes_by_frame` — `"""... ignoring note-offs (volume/velocity = 0)"""`), `tracker/track_mapper.py:21-51` (`apply_arpeggio_fallback` synthesizes new events with fixed `velocity` and no `note_off` counterparts at all); consumed by `nes/emulator_core.py:76-94`'s note-off search, which can never find a match for these synthetic events
- **Status**: NEW (partial-fix gap in #160/NH-20 — the fix covers the paths it touched, but one channel-assignment path was not updated)
- **Description**: `assign_tracks_to_nes_channels`'s "multiple tracks" branch (taken for
  any standard multi-track MIDI file — `tracker/parser_fast.py` keys `track_events` by
  track name, so any file with more than one MIDI track hits this branch, not the
  single-track split path) assigns the melody and bass tracks by direct list passthrough
  (`nes_tracks['pulse1'] = midi_events[ch]`, `nes_tracks['triangle'] = midi_events[ch]`)
  — these retain their original `note_off` events and correctly benefit from the NH-20
  fix in `compile_channel_to_frames`. The harmony track, however, is routed through
  `apply_arpeggio_fallback`, which calls `group_notes_by_frame` (explicitly documented as
  "ignoring note-offs") and emits brand-new synthetic events — one per note in each
  simultaneous chord, spread across consecutive frames, each with a fabricated
  `velocity` (`100 - i*5`) — with **no corresponding note-off events at all**. When these
  events reach `compile_channel_to_frames`, the note-off search added for NH-20
  (`for other in all_events_sorted: if ... other_velocity == 0 ...`) can never find a
  match (there is no velocity-0 event in the list), so `end_frame` always falls back to
  the default `start_frame + sustain_frames` (4 frames, ~67 ms) — exactly the pre-#160
  behavior NH-20 was filed against.
- **Evidence**: Reproduced against HEAD:
  ```python
  from tracker.track_mapper import assign_tracks_to_nes_channels
  midi_events = {
      'melody':  [{'frame': 0, 'note': 72, 'velocity': 100}, {'frame': 120, 'note': 72, 'velocity': 0}],
      'harmony': [{'frame': 0, 'note': 64, 'velocity': 90}, {'frame': 0, 'note': 67, 'velocity': 90},
                  {'frame': 120, 'note': 64, 'velocity': 0}, {'frame': 120, 'note': 67, 'velocity': 0}],
  }
  mapped = assign_tracks_to_nes_channels(midi_events, dpcm_index_path)
  print(mapped['pulse2'])
  ```
  ```
  [{'frame': 0, 'note': 64, 'velocity': 100, 'arpeggio': True, ...},
   {'frame': 1, 'note': 67, 'velocity': 95,  'arpeggio': True, ...}]
  ```
  No `velocity: 0` entries — the two-second-implied chord (note-offs at frame 120 in the
  source) never reaches `compile_channel_to_frames`, which therefore gives both notes the
  default 4-frame sustain.
- **Impact**: On any multi-track MIDI file (the common case) processed by the default
  (non-`--arranger`) pipeline, the harmony/pulse2 channel plays only ~67 ms blips
  regardless of the source chord's actual duration — musically indistinguishable from the
  pre-#160 bug, just scoped to one channel instead of three. Pulse1 (melody) and triangle
  (bass) are unaffected.
- **Related**: #160/NH-20 (this is the residual, not a new bug class), NH-26 (another gap
  in the same `assign_tracks_to_nes_channels` producer surface).
- **Hardware ref**: `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 ("To achieve precise,
  tracker-like note durations, our 60Hz Macro Sequencer will bypass the hardware length
  counter…") — the same engine-implementation-notes basis NH-20 was filed against; the
  NES itself has no durational limit, so this remains a pure front-end truncation.
- **Suggested Fix**: Either have `apply_arpeggio_fallback` emit matching note-off events
  at the original chord's end frame for each arpeggiated note (mirroring what
  `split_polyphonic_track`'s docstring promises for the single-track path), or route
  harmony through the same real-duration passthrough used for melody/bass and reserve
  arpeggiation for cases where the destination channel is already occupied.

### NH-28: `nes/mmc3_init.asm` is fully dead code — a duplicate reset/NMI/IRQ/APU-init implementation never included in any generated project
- **Severity**: LOW
- **Dimension**: 8/9 (frame-counter & register init) — dead code, cross-ref the
  "dead duplicate core" pattern from #37/#38/NH-10
- **Location**: `nes/mmc3_init.asm` (whole file: `.proc reset_handler`/`nmi_handler`/
  `irq_handler` + `.segment "VECTORS"`); the only reference anywhere in the codebase is
  `nes/project_builder.py:92` (`music_content.replace('.include "mmc3_init.asm"\n', '')`
  — stripping a *stale leftover include string*, never adding one)
- **Status**: NEW (previously miscategorized as live: `AUDIT_DPCM_2026-06-29.md`'s
  "Items checked and NOT reported" section cites `nes/mmc3_init.asm:68-69`'s `$4011`
  clear as a confirmed-correct *live* init site — it is correct in isolation but the
  file is never assembled into a ROM, so that check was auditing dead code without
  noticing)
- **Description**: `nes/mmc3_init.asm` defines a complete alternate reset/NMI/IRQ handler
  set with its own APU init sequence (`$4017=$40`, `$4015=$0F`, `$4011=$00`,
  `$4001=$4005=$08` — all individually correct) and its own `.segment "VECTORS"` pointing
  at its own labels. But `nes/project_builder.py` — the only code path that assembles a
  project — never copies this file into the output directory and never emits a real
  `.include "mmc3_init.asm"` (only strips a stale one, e.g. from a previous, since-removed
  code generation strategy). The actual reset/NMI/vectors/APU-init that ships is the
  inline template in `NESProjectBuilder._create_main_asm` (verified separately — same
  `$4017=$40`/`$4015=$0F`/sweep-disable sequence, no dependency on this file). Grepping
  the whole repo for `mmc3_init` outside this one string-strip line returns nothing —
  no test references it, no build script copies it, ca65 never sees it.
  Confirmed correct in isolation, and the frame-counter comment here has the identical
  "Mode 1" mislabel as NH-22/#164 (`$40` is Mode 0/4-step) — but since the file never
  reaches ca65, that doc-rot is moot rather than a live third instance of #164.
- **Evidence**: `grep -rn mmc3_init --include=*.py --include=*.asm .` → only
  `nes/project_builder.py:92`; `nes/project_builder.py:476-478` copies `audio_engine.asm`
  (not `mmc3_init.asm`) into the project; `nes/project_builder.py:539` `.include`s only
  `audio_engine.asm`; the generated `main.asm` template (same file, `_create_main_asm`)
  defines its own `reset:`/`nmi:`/`irq:` labels and `VECTORS` segment inline.
- **Impact**: None on shipped ROMs (dead code cannot be wrong on hardware). Maintenance
  hazard: a future contributor editing APU init "in `mmc3_init.asm`" (a plausible file to
  reach for, given the name) would have zero effect on real builds, and the file's stale
  "Mode 1" comment could get copy-pasted into a live site.
- **Related**: #164/NH-22 (same comment mislabel, live copies), #38/NH-10 (prior dead
  duplicate-implementation pattern).
- **Hardware ref**: `docs/APU_FRAME_COUNTER_REFERENCE.md` §2 (Mode 0 vs Mode 1, for the
  comment mislabel, moot here); `docs/MAPPER_MMC3_REFERENCE.md` (the PRG bank-mode setup
  this file also duplicates from the live mapper code).
- **Suggested Fix**: Delete `nes/mmc3_init.asm` (its logic is superseded by
  `NESProjectBuilder._create_main_asm`), or if it is meant as a future alternate code path,
  wire it in and fix the Mode-1 comment before it goes live.

### NH-29: `noise_mode` has no producer anywhere in the pipeline — the noise mode-bit plumbing is dead-but-correct
- **Severity**: LOW
- **Dimension**: 3 (Noise mode) — same class as NH-24 (inert instrument plumbing)
- **Location**: `nes/emulator_core.py:166` (`mode = e.get('noise_mode', 0) & 1`, always
  defaults to 0); no producer found in `tracker/`, `arranger/`, or `dpcm_sampler/`
- **Status**: NEW (adjacent to but distinct from NH-24, which covers `envelope_type`/
  `effects`/`arp`; this SKILL dimension explicitly asked to re-check whether
  `noise_mode` is "dead-but-correct plumbing, or is it reachable end-to-end" — it is not)
- **Description**: The engine and both exporter paths correctly thread a `noise_mode`
  bit from event → frame `control` (bit 6) → `$400E` bit 7
  (`nes/emulator_core.py:184`, `exporter/exporter_ca65.py:248-249`,
  `nes/audio_engine.asm:495-503`'s duty/mode-bit extraction) — the *consumer* side is
  fully wired and correct. But `grep -rn "noise_mode" --include=*.py .` (outside this one
  default-read site) finds no writer: `tracker/track_mapper.py`'s drum-fallback path
  (`dpcm_sampler/enhanced_drum_mapper.py`) never sets it, and no GM-drum-to-noise-mode
  mapping exists. Every noise hit in the current pipeline plays NES noise Mode 0 (the
  long/hiss sequence); Mode 1 (Metallic/short sequence — the more snare/hat-appropriate
  mode per the noise reference) is unreachable.
- **Evidence**: `nes/emulator_core.py:166` is the sole read of `'noise_mode'`
  repo-wide with a producer; no `.py` file outside `tests/` assigns the key.
- **Impact**: None wrong today — defaults to a valid, in-range mode bit (0). Missed
  opportunity: percussion timbre variety (metallic hats/snares via Mode 1) that the
  engine already supports end-to-end is unused because nothing selects it.
- **Related**: NH-24 (#166 — same "consumer ready, no producer" shape for
  envelope/effects/arp).
- **Hardware ref**: `docs/APU_NOISE_REFERENCE.md` §4 (Mode 0 vs Mode 1 — "Mode 1 ...
  produces a more metallic/tonal sound, commonly used for snares and hi-hats").
- **Suggested Fix**: Low priority — either have the drum mapper set `noise_mode: 1` for
  metallic-appropriate GM percussion (hi-hats/snares) using its existing note→sample
  classification, or leave as documented future work alongside NH-24.

---

## Existing findings re-verified at HEAD (not re-counted)

- **#41/NH-11 (OPEN, LOW)** — `PitchProcessor.note_to_timer` (`nes/pitch_table.py:133-139`)
  still raises for `midi_note < 24 or >= 96`, contradicting `CHANNEL_RANGES["pulse1"] =
  (24, 108)` it's meant to serve. Confirmed still dead: `grep -rn note_to_timer
  --include=*.py .` shows callers only in `tests/test_pitch_table_integration.py`; no
  production code path invokes it (`exporter_ca65.py` uses its own
  `midi_note_to_timer_value`, not this method).
- **#107/NH-14 (OPEN, MEDIUM per prior report)** — direct-export `play_pulse1`'s
  `@silence` branch is still unreachable: `cmp last_pulse1_note; beq @sustain; sta
  last_pulse1_note; beq @silence` (`exporter/exporter_ca65.py:445-452`) — `sta` does not
  affect the 6502 zero flag, so the second `beq` still tests the *first* `cmp`'s result,
  which is guaranteed clear at that point (we only reach here when the first `beq` did
  NOT take, i.e. Z=0). `@silence` is dead on all four tone-channel procs (verified
  pulse1/pulse2/triangle/noise all share this shape at `:445-452, :516-524, :585-593,
  :653-657`).
- **#163/NH-21 (OPEN, MEDIUM)** — `nes/audio_engine.asm`'s `EVAL_MACRO` macro
  (`:64-84`) still only tests `cmp #$FF`; no `$FE` loop handling exists in the live
  evaluator. `_compress_macro`'s loop-encoding path in `exporter/exporter_ca65.py`
  (verified still present) can still emit `$FE` control bytes the engine cannot decode.
- **#164/NH-22 (OPEN, LOW)** — `$4017=$40` comments still say "mode 1" in both
  `exporter/exporter_ca65.py:759` and `nes/audio_engine.asm:126-127`; the byte value ($40,
  4-step/Mode 0) remains correct.
- **#165/NH-23 (OPEN, LOW)** — `NOISE_PERIODS` (`exporter/exporter_ca65.py:40`) and
  `is_midi_velocity` (`:963`, computed, never read past that line — confirmed via grep)
  remain dead.
- **#166/NH-24 (OPEN, LOW)** — confirmed still true: no producer sets `envelope_type`,
  `effects`, or `arp` outside `nes/` defaults/tests (`grep -rn "'arp'"` /
  `envelope_type` across `tracker/`, `arranger/`, `dpcm_sampler/` — no hits outside this
  audit's hot files and tests). `get_envelope_control_byte` is called with `effects=None`
  hardcoded (`nes/emulator_core.py:105`).
- **#167/NH-25 (OPEN, LOW)** — `EnvelopeProcessor.get_envelope_control_byte`
  (`nes/envelope_processor.py:122`) still sets only `0x10` (constant volume), no halt bit;
  confirmed this is the exact byte `play_pulse1`/`play_pulse2` write to `$4000`/`$4004`
  on a new note (`exporter/exporter_ca65.py:463-464`).

## Dimension coverage notes (verified clean at HEAD, no new findings)

- **Dim 1**: Duty 2-bit masking, constant-volume bit, 4-bit volume mask all correct
  (`nes/envelope_processor.py:119-124`; engine `lsr/ror/ror`). Sweep disabled ($08) at
  both live init sites. NH-25 is the one open gap (halt bit), unchanged.
- **Dim 2**: Triangle carries no duty/volume control byte from the core
  (`compile_channel_to_frames`'s non-pulse branch, `nes/emulator_core.py:114-126`);
  direct-export derives `$4008` from `0x80 | vol*7` independently; engine uses `$FF`/`$80`
  for note-on/off. No pulse semantics leak into `$4008`/`$400B`.
- **Dim 3**: `get_noise_period` clamp/invert (`nes/pitch_table.py:62-75`) and
  `PitchProcessor._get_noise_period` delegation confirmed in lockstep. Mode bit reaches
  `$400E` bit 7 correctly end-to-end but has no producer (NH-29, new). The upstream
  contract break feeding this branch a `note`-less event is NH-26 (new, CRITICAL).
- **Dim 4**: DPCM `note = sample_id+1`, rest sentinel honored both paths; `$4011` zeroed
  at the two *live* init sites (exporter standalone `reset`, `audio_engine.asm`
  `audio_init`) — `nes/mmc3_init.asm`'s copy is dead (NH-28, new). Engine's `$87` handler
  still clamps `and #$7F`; still no producer of `CMD_DMC_LEVEL` (matches prior NH-23/D-09
  findings, not re-filed).
- **Dim 5/10**: Pulse `/16` vs triangle `/32` tables distinct, single-sourced
  (`nes/pitch_table.py:51-52`), both floored at 8 and clamped to `$7FF`.
  `midi_note_to_timer_value`'s NH-16 clamp holds. The engine's pitch-macro add
  (`adc temp_pitch`/`temp_pitch_hi` onto `ntsc_period_low/high`, no post-add `$7FF`
  re-clamp) and arpeggio add (`adc temp_arp` onto `current_note`, no range check before
  indexing the 128-entry period table via `ldy temp_note`) remain structurally unclamped
  but confirmed still inert — no producer emits nonzero `pitch_seq`/`arp` values
  (verified via the same grep that confirms NH-24); re-flag only if a producer appears.
- **Dim 6**: Velocity→volume curve (`max(1, int(15*pow(v/127,1.5)))`) used consistently
  in `emulator_core.py`'s two branches and `envelope_processor.py`'s combination step;
  `round((envelope_volume*midi_volume)/15.0)` bound-checked (max product 225/15=15.0
  exactly, cannot round to 16).
- **Dim 7**: Constant-volume bit unconditionally set; percussion divide-by-zero shape in
  `get_envelope_value` remains unreachable (no `envelope_type="percussion"` producer,
  same evidence as NH-24).
- **Dim 8/9**: `$4017=$40` + `$4015=$0F` before playback on both live init paths;
  `nes/mmc3_init.asm`'s third copy is dead (NH-28). Frame model remains strictly one
  entry per integer 60Hz frame. Every emitted `sta $40xx` across
  `exporter/exporter_ca65.py` and `nes/audio_engine.asm` lands in `$4000-$4017` on the
  correct channel register (`$8000/$8001` writes are MMC3 bank-switch, out of scope here
  per the mappers audit).

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_NES-HARDWARE_2026-07-03.md
```
