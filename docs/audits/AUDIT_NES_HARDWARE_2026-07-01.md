# NES Hardware Correctness Audit — 2026-07-01

Audit of the boundary where Python numeric values become APU register writes, across all
10 hardware dimensions, at HEAD `2bcb780`. Hot files: `nes/emulator_core.py`,
`nes/pitch_table.py`, `nes/envelope_processor.py`, `exporter/exporter_ca65.py`, plus the
live bytecode engine `nes/audio_engine.asm` and its host `nes/project_builder.py`.

**Pipeline note.** Frame generation goes through the **live**
`nes/emulator_core.py:NESEmulatorCore.process_all_tracks`; the near-duplicate
`NESEmulatorCore` in `nes/envelope_processor.py` is dead (#38). Export enters via
`CA65Exporter.export_tables_with_patterns`: with non-empty `patterns` (the **default**
pipeline) it emits MMC3 macro bytecode consumed by `nes/audio_engine.asm`; with empty
patterns (`--no-patterns`) it falls back to `export_direct_frames`, which carries its own
playback procs. Both paths were audited.

**Regression check (closed hardware issues re-verified at HEAD — all fixes still in
place, no regressions):** #7 (`$4017`/`$4015` init, both paths), #12/#16 (distinct
`/16` pulse and `/32` triangle tables, single source of truth), #20 (noise period
inversion), #24/#72 (DMC level path removed from exporter; engine `and #$7F` clamp kept,
`nes/audio_engine.asm:255`), #27 (`t >= 8` floors in `nes/pitch_table.py:45,131` and
`exporter/exporter_ca65.py:203-204`), #31 (sweep `$08` disable at init,
`exporter/exporter_ca65.py:317-319,758-760`; `nes/audio_engine.asm:138-140`), #36
(mapper-derived iNES header), #66 (`play_dpcm` `cmp #0` re-test present,
`exporter/exporter_ca65.py:708-709`), #67 (DPCM byte ceiling,
`exporter/exporter_ca65.py:980-984`), #77 (`_encode_macro_offset` snaps `-1`/`-2`,
`exporter/exporter_ca65.py:69-84`, spec updated), #78 (continuation frames pass
`channel`, `exporter/exporter_ca65.py:1032`), #108 (`PULSE_DUTY_CYCLES` /
`nes/audio_constants.py` removed).

**Dedup sources:** corrected `/tmp/audit/issues.json` (125 midi2nes issues, open+closed;
the initially cached file contained a different repository's issues and was discarded),
plus all prior reports in `docs/audits/` (notably `AUDIT_NES_HARDWARE_2026-06-28.md`,
`AUDIT_NES_HARDWARE_2026-06-29.md`, `AUDIT_EXPORTERS_2026-06-29.md`).

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 0 |
| HIGH     | 3 |
| MEDIUM   | 3 |
| LOW      | 4 |
| **Total**| **10** |

### Highest-risk hardware divergences (wrong on every ROM the affected path produces)

1. **NH-20 (HIGH)** — The default (legacy) front-end discards all MIDI note durations:
   `note_off` events are dropped and every note is hard-capped at `sustain_frames=4`
   (~67 ms). Every song on the default path plays as staccato blips regardless of the
   source durations. The `--arranger` front-end honors durations (workaround).
2. **NH-17 (HIGH)** — The bytecode engine never silences a channel at end-of-stream:
   after a channel's last event, its final note/hit **drones forever** (halt flags +
   constant volume keep pulse/triangle/noise sounding). Any channel that finishes before
   the others drones through the rest of the song; at song end the final chord + noise
   hiss sustain indefinitely. Every default-mode ROM.
3. **NH-16 (HIGH)** — MIDI notes below 24 (C1) — e.g. the bottom three piano keys
   A0–B0 — get a `base_timer` of 0 from `midi_note_to_timer_value`'s range guard, so the
   bytecode path emits a spurious `+127` pitch macro that overflows the 11-bit timer in
   the engine's 16-bit add; sub-C1 notes play ~4–5 octaves too high in default mode.

---

## Findings

### NH-16: Sub-C1 notes get `base_timer = 0`, emitting a +127 pitch macro that wraps the 11-bit timer
- **Severity**: HIGH
- **Dimension**: 5 (per-channel pitch correctness + 11-bit clamp) + 10 (clamp re-opened downstream)
- **Location**: `exporter/exporter_ca65.py:47-49` (`midi_note_to_timer_value` guard
  `return 0`), `:983-984` (only an *upper* note clamp — no lower clamp to 24),
  `:1016-1018`/`:1032-1034` (offset = `pitch_val - base_timer`); consumer
  `nes/audio_engine.asm:390-399,422-431,449-457` (16-bit add, high byte `ora #$08` →
  `$4003/$4007/$400B`)
- **Status**: NEW (distinct from #41, which is the *unused* `PitchProcessor.note_to_timer`
  guard, and from closed #78, which was the missing `channel` arg on continuation frames)
- **Description**: `midi_note_to_timer_value` returns **0** for `midi_note < 24` instead
  of a clamped table value. The live core clamps the frame's `pitch` to the channel range
  (`nes/pitch_table.py:100`, note < 24 → `pitch = table[24]`), but the frame's `note`
  field stays the raw MIDI note (`nes/emulator_core.py:93,107`) and neither
  `tracker/track_mapper.py` nor the exporter clamps it upward. In bytecode mode the pitch
  macro is `pitch_val - base_timer = table[24] - 0`, clamped by `_encode_macro_offset` to
  `+127`. At runtime the engine indexes the full 0–127 period table with the raw note
  (whose sub-24 entries are clamped to `$7FF`/near-`$7FF`) and **adds +127**: the 11-bit
  timer overflows into bit 3 of the high byte, which is part of the length-load field of
  `$4003`/`$4007`/`$400B`, so the written timer-high bits are 0 and the period wraps to a
  tiny value.
- **Evidence**: Reproduced numerically against HEAD code:
  ```
  pulse1  note 21: frame_pitch=2047 base_timer=0 offset=+127 table[21]=2047 sum=0x87E (>0x7FF)
  triangle note 21: frame_pitch=1709 base_timer=0 offset=+127 table[21]=2032 sum=0x86F (>0x7FF)
  ```
  `0x87E` writes `$4002=$7E`, `$4003=$08` → effective timer `126` → ~875 Hz for a note
  that should be ~27.5 Hz (A0). The direct-export path is unaffected (it re-clamps the
  frame `pitch` at `exporter/exporter_ca65.py:203-204` and never uses `base_timer`).
- **Impact**: Any melodic content below C1 (piano A0–B0, 5-string bass low B, octave-down
  synth bass) plays 4–5 octaves too high on pulse/triangle in the **default** (patterns)
  pipeline. Noise/DPCM are unaffected (noise skips pitch macros,
  `nes/audio_engine.asm:345-347`; DPCM frames have no `pitch` key so the offset is 0).
- **Related**: #41 (same anti-pattern in a dead method), closed #78/#16 (previous
  base-timer scale mismatches in this exact expression), NH-18 (same engine add path).
- **Hardware ref**: `docs/APU_PITCH_TABLE_REFERENCE.md` §1/§3 (timers are 11-bit and the
  full 0–127 table is clamp-generated — a base of 0 is not a legal period source);
  `docs/APU_PULSE_REFERENCE.md` §2 (`$4003` = `llll.lHHH` — only 3 timer-high bits, the
  rest is the length-counter load field).
- **Suggested Fix**: Make `midi_note_to_timer_value` clamp instead of returning 0
  (`midi_note = max(24, min(midi_note, 119))` then index the per-channel table), and/or
  clamp `note` to ≥ 24 for tone channels next to the existing `note > 95` clamp at
  `exporter/exporter_ca65.py:983-984` so note and pitch stay on the same scale.

### NH-17: Bytecode engine never silences at end-of-stream — every channel's last note drones forever
- **Severity**: HIGH
- **Dimension**: 9 (register/enable correctness) + 8 (frame model)
- **Location**: `nes/audio_engine.asm:193-195,540-543` (`$FF` → `@end_of_stream` →
  `@next_channel`, no register write, `frame_wait` left 0); serializer
  `exporter/exporter_ca65.py:964,1041-1066,1163` (per-channel loop ends at the channel's
  own last data frame; final flushed event is always a note; stream ends `note … $FF`)
- **Status**: NEW (checked all prior reports and #83 — EXP-07 covers the spec's unused
  `$84 CMD_JUMP` row as doc-rot, not this runtime behavior; #3 "Output seems silent" is a
  vague user report, possibly a symptom of NH-20, not this)
- **Description**: Each channel's bytecode stream ends with the last *note* event followed
  by the `$FF` terminator: `max_frame` is computed per channel from its own frames
  (`:951`), all emitted tone/noise frames have `volume ≥ 1`, and no trailing rest event is
  emitted. When the engine fetches `$FF` it jumps to `@end_of_stream`, which performs **no
  hardware write** and leaves `frame_wait = 0`, so every subsequent frame re-fetches the
  same `$FF`. The channel's registers keep their last state: pulse `$4000 = duty|$30|vol`
  (length halted, constant volume > 0), triangle `$4008 = $FF` (linear halt, continuous
  reload), noise `$400C = $30|vol`. Per the length-counter doc, the halt flag means the
  hardware will never silence them — the engine's own `@silence` blocks
  (`nes/audio_engine.asm:513-538`) are the only silencer and they are never reached again.
- **Evidence**: Trace: last note event → `@is_note` sets `frame_wait = len-1` → after it
  expires, `@fetch_byte` reads `$FF` → `@end_of_stream` → `@next_channel`. No path writes
  `$30`/`$80` to the channel. Direct-export mode is unaffected — it loops the whole song
  via the `frame_counter` compare/reset (`exporter/exporter_ca65.py:351-363,776-788`).
- **Impact**: Default-mode ROMs: (a) any channel whose part ends before the others (e.g.
  an intro-only melody line) drones its final note under the rest of the song; (b) at
  song end, the final chord plus a constant noise hiss sustain indefinitely. Also the
  bytecode path never loops the song (the spec's `$84 CMD_JUMP` "looping the song" is
  neither emitted nor implemented — cross-ref #83), so the drone is permanent. Workaround:
  `--no-patterns`.
- **Related**: #83 (EXP-07: spec lists `$84 CMD_JUMP` the exporter never emits), NH-20.
- **Hardware ref**: `docs/APU_LENGTH_COUNTER_REFERENCE.md` §3 (halt flag set → length
  counter never decrements → no hardware auto-silence) and §5 ("Software Note-Off: … the
  sequencer will manually write a volume of 0 to the channel's control register (or `$80`
  to `$4008` for the Triangle)" — exactly the write that is missing here);
  `docs/APU_PULSE_REFERENCE.md` §5 (a pulse with nonzero constant volume, nonzero length,
  valid timer keeps outputting).
- **Suggested Fix**: On first `$FF` per channel, execute the channel's `@silence` write
  once (e.g. set `current_note = 0` and fall into `@process_macros`, or emit an explicit
  trailing rest event per channel in the serializer). Optionally implement/emit a song
  loop instead of halting.

### NH-20: Default front-end discards MIDI note durations — every note is capped at 4 frames (~67 ms)
- **Severity**: HIGH
- **Dimension**: 8 (frame model) — frame generation in a hot file; cross-refs the
  pipeline audit
- **Location**: `nes/emulator_core.py:63-76` (`velocity == 0: continue` — "We simulate
  note-off via time"; `end_frame = start_frame + sustain_frames` with `sustain_frames=4`;
  lookahead only truncates at the *next note-on*), `nes/emulator_core.py:112-122`
  (`process_all_tracks` never passes a different `sustain_frames`);
  `tracker/track_mapper.py:11,159-161` (note-offs dropped before the core:
  "ignoring note-offs")
- **Status**: NEW (no prior issue or audit finding covers duration handling; #96/TEMPO-04
  was same-frame collapse; #3 "Output seems silent" is plausibly a user-visible symptom —
  cross-reference when triaging)
- **Description**: `tracker/parser_fast.py:100-116` faithfully emits `note_off` events
  (velocity 0) at their correct frames, so durations survive parsing. The legacy mapper
  then drops them (`track_mapper.py:159-161`), and `compile_channel_to_frames` skips any
  velocity-0 event and substitutes a **fixed 4-frame sustain** for every note. At 120 BPM
  a quarter note is 30 frames: it sounds for 4 and is silent for 26. A held whole note
  (2 s) becomes a 67 ms blip. The engine-side machinery for real durations exists and is
  unused: the bytecode length commands support arbitrary durations via chaining
  (`docs/AUDIO_BYTECODE_SPEC.md` §3, `exporter/exporter_ca65.py:1155-1161`), and the
  documented note-off strategy assumes the sequencer counts *actual* note lengths. The
  `--arranger` front-end, by contrast, pairs note-on/note-off into `NoteInfo` with real
  `start_frame`/`end_frame` and emits frames for the full duration
  (`arranger/pipeline_integration.py:118-160`, `arranger/voice_allocator.py:327-370`) —
  confirming durations are available and representable end-to-end.
- **Evidence**: The three code sites above; no caller overrides `sustain_frames`; no
  warning is printed. This silently changes every song on the default path
  (per `_audit-severity.md`, a dropped MIDI event class that changes the song is a
  CRITICAL floor *without* workaround; the arranger front-end is the workaround that
  holds this at HIGH).
- **Impact**: All melodic/sustained material on the default `python main.py in.mid out.nes`
  path plays staccato: pads, held basses, legato melodies are truncated to ≤ 67 ms.
  Blast radius: every ROM built without `--arranger`, both export paths (the frames are
  already truncated before export).
- **Related**: NH-17 (the one place a note *does* sustain — forever), NH-19 (the drum
  variant of the same duration gap), #3.
- **Hardware ref**: `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 ("To achieve precise,
  tracker-like note durations, our 60Hz Macro Sequencer will bypass the hardware length
  counter … the 6502 sequencer will count frames in software based on our custom Length
  Commands (`$60-$7F`)"); `docs/AUDIO_BYTECODE_SPEC.md` §3 Length Commands. The NES has no
  4-frame limit — the truncation is purely the Python front-end.
- **Suggested Fix**: In the legacy path, compute each note's end frame from its matching
  note-off (fall back to `sustain_frames` only for missing note-offs, as the arranger
  does), or route the default pipeline through the arranger's duration pairing. Keep the
  next-note truncation.

### NH-18: Bytecode engine rewrites `$4003`/`$4007` every frame of a held note — phase-reset click
- **Severity**: MEDIUM (per SKILL Dimension 1: per-frame Timer-High rewrite on a held note)
- **Dimension**: 1 (Pulse timer write order)
- **Location**: `nes/audio_engine.asm:176-180` (wait-state frames jump to
  `@process_macros`), `:381-399` (`@write_pulse1` — both the fast path and
  `@p1_pitch_mod` unconditionally `sta $4002` then `ora #$08 / sta $4003` every frame),
  `:413-431` (pulse2 identical)
- **Status**: NEW (NH-14/#107 is the *direct-export* note-off retrigger; no prior finding
  covers the bytecode engine's per-frame rewrite on sustained frames)
- **Description**: `@process_macros` runs for every channel on every frame — including
  the `frame_wait > 0` sustain frames of a note — and the pulse write path has no
  "timer unchanged, skip `$4003`" guard. A 4-frame note therefore writes `$4003` four
  times; per the pulse reference, each write "**immediately restarts the sequencer** at
  the first step … this phase reset is what causes an audible 'click' or 'pop' if done
  continuously". It also reloads the length counter and restarts the (bypassed) envelope
  each frame. The direct-export path gets this right with its `@sustain` short-circuit
  (`exporter/exporter_ca65.py:447-448,497-498`). Triangle's per-frame `$400B` write is
  harmless (no phase reset on the triangle sequencer; the linear counter is already in
  continuous-reload mode), and noise events are single-frame.
- **Evidence**: Code path above; every note on the default path is 1–4 frames (NH-20), so
  essentially all pulse notes longer than 1 frame click at 60 Hz during their sustain.
- **Impact**: Audible buzz/pop on sustained pulse notes in every default-mode ROM. The
  standard idiom (cache last timer-high, write `$4003` only when it changes or on note-on)
  is absent.
- **Related**: #107/NH-14 (direct-path variant of the same quirk class), NH-16 (same write
  path).
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §2 ⚠️ Critical Side Effects (quoted
  above); `docs/APU_ENVELOPE_REFERENCE.md` §2 ⚠️ Trigger Registers (`$4003`/`$4007`
  restart the envelope).
- **Suggested Fix**: Track the last written period (or last note) per pulse channel in the
  engine and skip the `$4003`/`$4007` write when unchanged (write `$4002` freely —
  low-byte writes don't reset phase); or only write timers on note-on / pitch-macro
  change.

### NH-19: Noise percussion has no decay — every drum hit is a one-frame (16.7 ms) tick
- **Severity**: MEDIUM
- **Dimension**: 3 (Noise) + 6 (volume mapping)
- **Location**: `nes/emulator_core.py:123-150` (one frame emitted per hit; comment at
  `:127-129` claims the hit "decays via the length counter"); exporter direct
  `exporter/exporter_ca65.py:254` (`$30 | vol` — halt bit set) and engine
  `nes/audio_engine.asm:466-469` (`ora #$30`), `:529-533` (rest frame silences with `$30`
  on the very next event)
- **Status**: NEW (related to but distinct from #107: this is about the *generated data*,
  not the dead `beq`; #73/#74 cover drum *mapping*, not decay)
- **Description**: A noise drum hit produces exactly one frame of constant-volume noise.
  The in-code justification — "the channel re-fires once, then decays via the length
  counter" — is impossible as written: (a) both playback paths set the length-counter
  **halt** bit (`$30`), which per the length-counter doc prevents any decrement; (b) the
  constant-volume flag bypasses the hardware envelope, so there is no envelope decay
  either; and (c) in bytecode mode the following rest event writes `$400C = $30`
  (volume 0) on the next frame anyway. The hardware-doc strategy for NES percussion is a
  multi-frame *software volume decay* ("Snare drums and hi-hats rely heavily on very
  sharp, exponential volume decays" via volume macros), which no stage generates — every
  `vol_seq` is a constant.
- **Evidence**: `noise_frames[e['frame']] = {…}` emits a single frame per hit; the
  bytecode stream for a hit is `…, $60, period` (length 1) followed by a rest event; the
  engine's `@silence` fires one frame later. In direct mode the intended `$30` silence is
  currently replaced by the #107 fallthrough chirp (see Existing findings below).
- **Impact**: On every drummed song, noise snares/hi-hats are barely-audible clicks rather
  than percussion. Playable, musically degraded — MEDIUM.
- **Related**: #107 (direct-path note-off artifact on the same channel), NH-20 (tone-side
  duration gap), #73/#74 (drum-mapping coverage).
- **Hardware ref**: `docs/APU_NOISE_REFERENCE.md` §6 (software envelopes / "rapid volume
  macro to simulate percussion strikes"; also "writing to `$400F` does not reset the
  phase … we can safely write to any Noise register on any frame");
  `docs/APU_LENGTH_COUNTER_REFERENCE.md` §3 (halt ⇒ no decrement) and §5 (halt-always
  strategy).
- **Suggested Fix**: Emit a short decay for noise hits — either extend each hit across
  ~4–8 frames with a decaying `volume` in `process_all_tracks` (the vol macro system will
  serialize it for free), or attach a canned percussion volume macro in the exporter.

### NH-21: Serializer emits `$FE` macro-loop control that the live engine cannot decode
- **Severity**: MEDIUM (latent contract divergence; rare-but-real trigger)
- **Dimension**: 7 (envelope/macro behavior) + bytecode contract
- **Location**: `exporter/exporter_ca65.py:836-860` (`_compress_macro` loop compression
  emits `[..., 0xFE, loop_start]`); consumer `nes/audio_engine.asm:53-83` (`EVAL_MACRO`
  handles **only** `$FF`); the `$FE`-capable macro runtime exists only in the *unused*
  `process_channel_macros` copy (`nes/project_builder.py:274-330`, `.global` with zero
  callers)
- **Status**: NEW (corrects `AUDIT_EXPORTERS_2026-06-29.md` EXP-01/EXP-07's statement that
  the engine reads in-macro `$FE` as loop — only the dead `project_builder` copy does;
  #83 covers the *spec* command-table rot, #77 covered *data-byte* collisions, both
  different defects)
- **Description**: The macro bytecode contract (`docs/AUDIO_BYTECODE_SPEC.md` §2.3)
  defines `$FF` (end/sustain) and `$FE, <offset>` (loop). `_compress_macro` implements
  both and picks whichever encoding is shorter. The shipped evaluator implements only
  `$FF`: on reading `$FE` it treats it as a *data value* (`@not_end`), writes it to the
  channel parameter, consumes the `loop_start` operand as the next frame's value, then
  walks the step index past the macro's end into the adjacent macro's bytes until some
  `$FF` appears. Today all generated macro sequences are constant per note (volume, duty,
  pitch offset, arp are frame-invariant), and for a constant sequence sustain
  (`[v, $FF]`, 2 bytes) always beats loop (`[v, $FE, 0]`, 3 bytes) — so `$FE` is not
  emitted on typical input. But it is *reachable*: a merged run of same-note frames with
  alternating volumes (e.g. a 60 Hz drum-roll/tremolo re-strike pattern, where two
  adjacent same-note events fuse into one event with `vol_seq = [a,b,a,b,…]`) makes loop
  compression win and emits `$FE` into `macro_vol_*`, desyncing that channel's volume
  stream at runtime.
- **Evidence**: `_compress_macro` comparison logic (`best_len`); `EVAL_MACRO`'s single
  `cmp #$FF`; `_encode_macro_offset`'s own docstring treats `$FE` as reserved *because it
  is a live control byte* — yet the engine can't honor it.
- **Impact**: None on typical songs today; wrong volumes/pitches on the affected channel
  when the alternating-value case is hit, and a guaranteed break for the first future
  producer of non-constant macros (vibrato, ADSR wiring — exactly what
  `docs/AUDIO_BYTECODE_SPEC.md` §5 Step 2 plans). Also every bytecode ROM ships the dead
  `process_channel_macros` runtime whose behavior diverges from the live one.
- **Related**: #77 (closed — data-byte side), #83 (spec doc-rot), #38 (dead duplicate
  core pattern).
- **Hardware ref**: `docs/AUDIO_BYTECODE_SPEC.md` §2.3 Macros (control bytes `$FF`,
  `$FE, <offset>`).
- **Suggested Fix**: Either implement `$FE` in `EVAL_MACRO` (mirror the dead copy's
  `@loop_vol` logic) or delete loop compression from `_compress_macro` (and the dead
  `process_channel_macros`) so the emitted format matches the engine exactly.

### NH-22: `$4017` init comments claim "mode 1" but `$40` is 4-step (mode 0)
- **Severity**: LOW (doc-rot in code comments; the written value is correct and safe)
- **Dimension**: 8 (frame counter init)
- **Location**: `exporter/exporter_ca65.py:755` ("Frame counter mode 1, disable frame
  IRQ"); `nes/audio_engine.asm:126-127` ("$4017 = $40: frame counter mode 1 …")
- **Status**: NEW
- **Description**: Both init paths write `$40` to `$4017`, which per the frame-counter
  reference is **Mode 0 (4-step)** with the IRQ-inhibit bit set — the doc's explicitly
  recommended value ("Writing `$40` (`%01000000`) sets 4-step mode, IRQ disabled"). The
  accompanying comments call it "mode 1" (which would be `$C0`/`$80`, the 5-step
  sequence). Functionally fine — IRQ is inhibited either way and the engine bypasses the
  sequencer — but the comment misstates the hardware mode bit in two places and will
  mislead the next person touching init.
- **Evidence**: `docs/APU_FRAME_COUNTER_REFERENCE.md` §2 (`MI--.----`, M=0 ⇒ 4-step) and
  §4 (recommended `$40` vs `$C0` values); code comments above.
- **Impact**: None at runtime; comment/doc divergence only.
- **Related**: #43 (previous doc-rot class).
- **Hardware ref**: `docs/APU_FRAME_COUNTER_REFERENCE.md` §2 Register Map, §3 Sequencer
  Modes, §4 Engine Implementation Notes.
- **Suggested Fix**: s/mode 1/4-step mode (mode 0)/ in both comments.

### NH-23: Dead hardware-adjacent code in the exporter: `NOISE_PERIODS` table and `is_midi_velocity`
- **Severity**: LOW
- **Dimension**: 3 (noise) / 6 (volume) — dead code
- **Location**: `exporter/exporter_ca65.py:40` (`NOISE_PERIODS`), `:953-959`
  (`is_midi_velocity` computed, never read)
- **Status**: NEW (not covered by the tech-debt audit or TD issues #130-#137)
- **Description**: (a) `NOISE_PERIODS` duplicates the NTSC noise period lookup from
  `docs/APU_NOISE_REFERENCE.md` §3 but has zero references — the engine correctly writes
  the 4-bit *index*, never these CPU-cycle values. (b) The bytecode path computes
  `is_midi_velocity = max_vol > 15` per channel and never uses it — a vestige of an
  unimplemented 0–127→0–15 rescale. If a producer ever did hand this path raw MIDI
  velocities, `vol_seq` bytes up to 127 would be emitted into `macro_vol_*` unscaled
  (the engine masks `and #$0F`, so 127 → 15, 100 → 4 — wrong but in-range), and values
  `$FE`/`$FF` are impossible only because 127 is the max. The dead flag suggests the
  normalization was intended and lost.
- **Evidence**: `grep -rn NOISE_PERIODS` / `is_midi_velocity` — definitions only. Live
  volume producers all clamp to 0–15 (`nes/emulator_core.py:94,100,144`), so both are
  inert today.
- **Impact**: None today; maintenance noise and a mild trap (same class as removed #108).
- **Related**: #108 (closed — `PULSE_DUTY_CYCLES`, same pattern), #34.
- **Hardware ref**: `docs/APU_NOISE_REFERENCE.md` §3 (the table it shadows) and §2
  (`$400E` takes the 4-bit index `P`, not the period value).
- **Suggested Fix**: Delete both; if velocity-domain detection is wanted, implement the
  rescale it implies (or assert `max_vol <= 15`).

### NH-24: Envelope/effects/arpeggio plumbing is inert — no producer, every note plays the flat default envelope
- **Severity**: LOW
- **Dimension**: 7 (ADSR behavior) + 1 (duty sequences)
- **Location**: `nes/emulator_core.py:80-81,87` (`envelope_type` read from events, never
  set upstream; `effects=None` hardcoded; `arpeggio` flag emitted at `:92,106`);
  `nes/envelope_processor.py:7-28` (`piano`/`pad`/`pluck`/`percussion` envelopes and the
  vibrato/tremolo/duty-sequence `effect_definitions`); `exporter/exporter_ca65.py:1019,1035`
  (`frame_data.get('arp', 0)` — no stage produces an `'arp'` key)
- **Status**: NEW (adjacent to open #34/#38 but a different fact: the *live* feature
  surface is unreachable, not just the dead expressions/core)
- **Description**: No pipeline stage (parser, track mapper, arranger, drum mapper) ever
  sets `envelope_type`, `effects`, or `arp` on an event/frame, and nothing consumes the
  `arpeggio` boolean the core emits. Consequences on the live path: `get_envelope_value`
  always evaluates the `default` `(0,0,15,0)` envelope (flat), the tremolo/vibrato/duty
  sequences are unreachable (the only caller passing `effects` is the dead core, #38),
  and every generated `macro_arp_*`/`macro_pitch_*` beyond the note<24 artifact (NH-16)
  is `[0, $FF]`. The ADSR/effects engine that Dimension 7 audits is, in effect, test-only
  code; the doc-stated goal of macro-driven instruments
  (`docs/APU_ENVELOPE_REFERENCE.md` §5, `docs/AUDIO_BYTECODE_SPEC.md` §1) is unrealized.
- **Evidence**: Repo-wide greps: `envelope_type` producers — none outside `nes/` defaults
  and tests; `'arp'` producers — none; `arpeggio` consumers — none.
- **Impact**: No wrong bytes today (the flat path is correct and clamped); the cost is
  dead-but-live-looking machinery and zero timbre variety. Becomes NH-21's trigger the
  day it is wired up.
- **Related**: #34, #38, NH-21, NH-19 (drum decay would be the first real macro user).
- **Hardware ref**: `docs/APU_ENVELOPE_REFERENCE.md` §4/§5 (constant-volume engine-driven
  model these definitions exist to feed).
- **Suggested Fix**: Either wire a producer (instrument/GM-based `envelope_type`
  selection; the arranger's GM table is the natural place) or prune the unused
  definitions and the `arpeggio` flag until they have one.

### NH-25: Direct-path pulse control bytes omit the length-counter halt flag the docs mandate
- **Severity**: LOW (latent; fully masked today, becomes audible if NH-20 is fixed)
- **Dimension**: 1 (pulse control byte) + 7
- **Location**: `nes/envelope_processor.py:123-126` (`envelope_bits = 0x10` — bit 5
  never set), consumed as the direct-export `$4000`/`$4004` byte
  (`exporter/exporter_ca65.py:198,463-464,534-535`)
- **Status**: NEW
- **Description**: The documented engine strategy is "Halt Flags Always Set … when
  writing to `$4000`, `$4004`, `$4008`, and `$400C`", so the hardware length counter can
  never cut a note the 60 Hz engine is holding. The bytecode engine complies
  (`ora #$30`, `nes/audio_engine.asm:374,406,468`), but `get_envelope_control_byte`
  builds `duty<<6 | 0x10 | vol` — constant volume yes, halt **no** — and that byte is
  what direct-export mode writes to `$4000`/`$4004`. Masked today because every new note
  reloads the length counter with index 1 (= 254 half-frame ticks ≈ 2.1 s via the
  `ora #$08` on `$4003`) and NH-20 caps notes at 4 frames. If durations are ever honored
  (NH-20's fix), any direct-mode pulse note held past ~2.1 s goes silent mid-note.
- **Evidence**: Bitfield `DDlc.vvvv`: emitted byte has `l = 0`. Direct-mode sustain never
  rewrites `$4003` (correctly, see NH-18), so the counter is not re-armed during a hold.
- **Impact**: None at HEAD; a time-bomb coupled to the NH-20 fix. Triangle and noise
  paths already set their halt bits (`0x80 |`, `$30 |`).
- **Related**: NH-20, NH-18, #107.
- **Hardware ref**: `docs/APU_LENGTH_COUNTER_REFERENCE.md` §2 (halt = bit 5 of
  `$4000`/`$4004`), §3 (halt ⇒ no decrement), §5 "Halt Flags Always Set";
  `docs/APU_PULSE_REFERENCE.md` §2 (`DDlc.vvvv`).
- **Suggested Fix**: Set `0x30` (halt + constant volume) in `get_envelope_control_byte`,
  matching the bytecode engine and the doc strategy.

---

## Existing findings re-verified at HEAD (not re-counted)

- **#107 / NH-14 (OPEN, MEDIUM)** — all four direct-export `@silence` branches still dead
  (`sta` then `beq` on stale flags): `exporter/exporter_ca65.py:449-452` (pulse1),
  `:519-523` (pulse2), `:588-592` (triangle), `:656-657` (noise). The `play_dpcm` sibling
  got the `cmp #0` fix (#66); the four tone procs did not. **Impact correction worth
  noting on the issue:** for *noise*, the fallthrough is worse than previously described —
  the silent-frame data writes `$400C = $00` (envelope mode, halt clear, constant-volume
  clear) followed by `$400F = $08`, which per `docs/APU_ENVELOPE_REFERENCE.md` §2/§3
  restarts the hardware envelope at decay level 15: every noise note-off in direct mode
  emits an audible ~60 ms period-0 noise chirp, not silence. Recommend re-triage of #107
  with that in mind (drummed songs + `--no-patterns`).
- **#34 / NH-08 (OPEN, LOW)** — dead contradictory pulse-volume expression still at
  `nes/emulator_core.py:94`.
- **#38 / NH-10 (OPEN, LOW)** — dead duplicate `NESEmulatorCore` with unclamped additive
  vibrato still at `nes/envelope_processor.py:162-237`.
- **#41 / NH-11 (OPEN, LOW)** — `note_to_timer` guard still contradicts channel ranges
  (`nes/pitch_table.py:133-139`); see NH-16 for the same anti-pattern on a *live* path.
- **#137 / TD-08 (OPEN)** — stale DPCM `.incbin` TODO still emitted
  (`exporter/exporter_ca65.py:888`).
- **#83 / EXP-07 (OPEN, LOW)** — spec §3 command table still stale; NH-21 above adds a
  runtime-relevant corollary in the macro namespace.

## Dimension coverage notes (verified clean at HEAD)

- **Dim 1**: duty is 2-bit everywhere (`(duty & 0x03) << 6`,
  `nes/envelope_processor.py:121`; engine `lsr/ror/ror`), constant-volume bit set, 4-bit
  volume masked. Sweeps disabled at init on all paths.
- **Dim 2**: triangle carries no duty/volume control byte from the core; direct mode
  derives `$4008` from `0x80 | vol*7` (≤127) with `0x00` silence; engine uses `$FF`/`$80`
  per `docs/APU_TRIANGLE_REFERENCE.md` §4-§5. No pulse semantics leak into
  `$4008`/`$400B` (except the halted-forever case, NH-17).
- **Dim 3**: `NOISE_PERIOD` index clamped 0-15 and inverted once
  (`nes/pitch_table.py:62-75`); mode bit reaches `$400E` bit 7 in both paths.
- **Dim 4**: DPCM `note = sample_id+1 ≤ 255`, rest sentinel honored in both paths (#66
  fix present); `$4011` zeroed at bytecode init; engine `$87` handler clamps `and #$7F`.
- **Dim 5/10**: pulse//16 vs triangle//32 tables distinct and single-sourced; all direct
  timers re-clamped `[8, 0x7FF]` pre-split; the one unclamped additive path found is
  NH-16.
- **Dim 6**: velocity → volume uses the 1.5-power curve with `max(1, …)`/`min(15, …)`
  everywhere live.
- **Dim 8/9**: `$4017 = $40` + `$4015 = $0F` before playback on all paths; every emitted
  `sta $40xx` lands in `$4000-$4017` and on the right channel (the `$8000/$8001` writes
  are MMC3 bank-switching, per `docs/MAPPER_MMC3_REFERENCE.md`, verified in the mappers
  audit); frame model is strictly one entry per integer 60 Hz frame.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-07-01.md
```
