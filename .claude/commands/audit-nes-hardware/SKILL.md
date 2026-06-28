---
description: "Audit NES APU hardware correctness — channels, pitch tables, envelopes, ranges"
argument-hint: "[--focus <dims>]"
---

# NES Hardware Correctness Audit

Audit the boundary where Python numbers become APU register writes: the four tone
channels (Pulse1, Pulse2, Triangle, Noise) plus DPCM must be driven per their *real*
register semantics. A value that is wrong here is wrong on every ROM the compiler
produces, so this subsystem carries HIGH/CRITICAL severity floors.

Shared protocol: `.claude/commands/_audit-common.md` — read **NES Hardware Constraints**
and **Key Reference Docs** before starting; do not restate them here.
Severity: `.claude/commands/_audit-severity.md` — apply the **NES-hardware rows** of the
Special Rules table (out-of-range value = HIGH, Triangle volume/duty = HIGH, bad
vectors / no APU init = CRITICAL).

**Cite, do not assert.** For every hardware claim, point at the section of the relevant
`docs/APU_*.md` that backs the expected behavior — never assert NES semantics from memory.
The docs under `docs/` are the hardware-verified baseline; the code must match them, and
where the code contradicts a doc the *code* is the suspect (unless the doc itself is rot,
which is a separate LOW finding).

The hot files for this audit:
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_constants.py`, and the serializer `exporter/exporter_ca65.py`.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 1,5,9`). Default: all.

## Extra Per-Finding Field
- **Hardware ref**: `docs/APU_*.md` section backing the expected behavior (e.g.
  `docs/APU_TRIANGLE_REFERENCE.md` §1 Hardware Architecture). A finding with no
  hardware-doc citation is not done.

## Dimensions

### Dimension 1: Pulse1 / Pulse2 — duty, volume, timer, sweep
Pulse channels live at `$4000–$4007` (`exporter/exporter_ca65.py` defines
`APU_PULSE1_CTRL` … `APU_PULSE2_TIMER_HI`). Verify:
- Duty is 2 bits in the control byte (bits 6–7). In
  `nes/envelope_processor.py:get_envelope_control_byte` the duty is masked
  `(duty_cycle & 0x03) << 6` and the constant-volume flag `0x10` (bit 4) is set —
  confirm both, and that the 4-bit volume occupies bits 0–3 (`volume & 0x0F`).
- The duty *values* in `PULSE_DUTY_CYCLES` (`nes/audio_constants.py`) are the four
  legal NES duties (12.5/25/50/75%). Cross-check against `docs/APU_PULSE_REFERENCE.md`
  §4 Duty Cycles — flag any divergence or an unused/contradictory mapping.
- Timer write order in the play_pulse routine (`exporter/exporter_ca65.py`, around the
  `sta $4002`/`sta $4003` and `sta $4006`/`sta $4007` writes): note the phase-reset
  click quirk in `docs/APU_PULSE_REFERENCE.md` §3 / `docs/NES_APU_REFERENCE.md` §2.1 —
  rewriting Timer High (`$4003`/`$4007`) every frame on a held note is a MEDIUM
  (audible popping), not just cosmetic.
- Sweep ($4001/$4005): if the engine never writes sweep, confirm it is disabled/zeroed
  at init (`docs/APU_PULSE_REFERENCE.md` §2). A stale sweep left enabled silently bends
  pitch — HIGH.

### Dimension 2: Triangle — the no-volume / no-duty invariant + linear counter
This is the highest-yield dimension. The Triangle channel (`$4008–$400B`) has **no
volume and no duty** (`docs/APU_TRIANGLE_REFERENCE.md` §1; `docs/NES_APU_REFERENCE.md`
§2.2). Verify, skeptically:
- `nes/emulator_core.py:process_all_tracks` routes `triangle` through
  `compile_channel_to_frames` with `default_duty=None` (the `'pulse' in channel_name`
  test). Confirm the non-pulse branch is taken and **no `control`/duty byte** is emitted
  for triangle. Any path that writes a duty or 4-bit volume into a triangle register
  ($4008/$400B) is **HIGH** per the Special Rules table.
- In `exporter/exporter_ca65.py` the `play_triangle` proc writes `$4008` (linear
  counter), `$400A`, `$400B`. Check what value is stored to `$4008`: it must be a linear
  counter / control value (`docs/APU_TRIANGLE_REFERENCE.md` §4 The Linear Counter), not
  a borrowed pulse "volume/duty" control byte. Grep for a `$30`-style "zero volume,
  duty" constant leaking into the triangle path — that is meaningless for triangle and a
  finding.
- Note-off: the doc-recommended halt is linear-counter halt or ultrasonic pitch
  (`docs/APU_TRIANGLE_REFERENCE.md` §5). If silencing instead writes a volume, flag it.

### Dimension 3: Noise — period table & mode flag
Noise is at `$400C–$400F`; frequency is a **4-bit index** into a 16-entry table, mode is
bit 7 of `$400E` (`docs/APU_NOISE_REFERENCE.md` §3–§4; `docs/NES_APU_REFERENCE.md` §2.3).
Verify:
- `NOISE_PERIOD_TABLE` in `nes/pitch_table.py` has exactly 16 entries (indices 0–15) and
  `get_noise_period` / `PitchProcessor._get_noise_period` clamp the index to `0..15`.
  Note the two implementations disagree (module `get_noise_period` does **not** invert;
  `PitchProcessor._get_noise_period` returns `15 - scaled`) — reconcile which one the
  pipeline actually uses and whether higher MIDI note → higher pitch is preserved
  (`docs/APU_NOISE_REFERENCE.md` §3, lower period = higher frequency).
- `process_all_tracks` hardcodes `"noise_mode": 0` (white noise). Confirm bit-7 mode is
  reachable at all, and that the period index is actually carried into the noise frame —
  grep whether `process_all_tracks`'s noise branch even computes a period (it appears to
  emit only `noise_mode`/`volume`, dropping pitch). A dropped period is wrong output =
  HIGH if it makes every drum the same pitch.

### Dimension 4: DPCM / DMC — level handling
DMC is at `$4010–$4013`; direct level load is `$4011` (7-bit, `docs/APU_DMC_REFERENCE.md`
§2–§3). Verify:
- `process_all_tracks`'s `dpcm` branch carries `sample_id` and a `volume` of 15/0. DMC
  has no 4-bit volume register — a "volume" of 15 must map to a real DMC action (enable
  via `$4015` bit 4, or a `$4011` level load), not a pulse-style volume. Check how the
  exporter / `exporter/exporter_ca65.py` translates the dpcm frame; a `volume` that goes
  nowhere is a silent drop (the recent `DMC level handling` commits touched this — verify
  the level value stays in 0–127 / 7-bit, `docs/APU_DMC_REFERENCE.md` §3).
- Sample address/length alignment ($4012/$4013) and the `$C000–$FFFF` residency
  constraint (`docs/APU_DMC_REFERENCE.md` §4; `docs/NES_APU_REFERENCE.md` §2.4) — if the
  generated project can place samples outside that window, note it (cross-refs the mapper
  audit).

### Dimension 5: Per-channel pitch-table correctness + 11-bit clamp
The pulse and triangle channels do **not** share a period table — for the same 11-bit
period the pulse sounds one octave above the triangle (`docs/APU_PITCH_TABLE_REFERENCE.md`
§1; `docs/NES_APU_REFERENCE.md` §2.2 "Triangle … one octave lower"). Verify:
- `nes/pitch_table.py` actually provides **distinct** tables and selects by channel.
  `PitchProcessor.get_channel_pitch` currently indexes a single `self.note_table` for
  both pulse and triangle (only `noise` branches off). If triangle reuses the pulse
  timer with no octave compensation, triangle plays an octave wrong — HIGH (wrong pitch
  on every triangle note). State this against `docs/APU_PITCH_TABLE_REFERENCE.md` §1.
- Every timer is clamped to 11-bit `$0–$7FF`: `generate_note_table` /
  `_generate_note_table` do `max(0, min(timer, 0x07FF))`, and `apply_pitch_bend` clamps
  the bent result. Hunt for any pitch path (vibrato in
  `EnvelopeProcessor.get_pitch_modification` added to `pitch` in
  `compile_channel_to_frames`) that can push the value **above $7FF or below 0 without
  re-clamping** — an unclamped timer is HIGH per the Special Rules table.
- The `t < 8` silence quirk (`docs/APU_PULSE_REFERENCE.md` §3 / `docs/NES_APU_REFERENCE.md`
  §2.1): timers under 8 silence the channel. Flag if low notes silently mute.

### Dimension 6: Velocity → 4-bit volume mapping
APU volume is 4-bit (0–15) on pulse/noise (`docs/APU_PULSE_REFERENCE.md` §1;
`docs/APU_NOISE_REFERENCE.md` §2); MIDI velocity is 0–127. Verify the mapping in
`nes/envelope_processor.py:get_envelope_control_byte` and the non-pulse branch of
`nes/emulator_core.py:compile_channel_to_frames`:
- Output is clamped to `0..15` (`min(15, …)` / `max(0, min(15, base_volume))`).
- The `pow(velocity/127, 1.5)` curve (logarithmic-to-linear) keeps non-zero velocities
  audible: `max(1, …)` so a quiet-but-present note never collapses to 0. A curve that
  under/overshoots but stays in range is MEDIUM; emitting >15 is HIGH.
- Check the dead/contradictory expression in `compile_channel_to_frames`'s pulse branch
  (`min(15, velocity // 8) if velocity == 0 else …` — the `velocity == 0` case is
  unreachable because the loop `continue`s on velocity 0). Flag as LOW dead code, MEDIUM
  if it masks a real volume bug.

### Dimension 7: Envelope / ADSR behavior
The engine bypasses the hardware envelope and drives constant volume per frame
(`docs/APU_ENVELOPE_REFERENCE.md` §4 Constant Volume Output, §5 Engine Implementation).
Verify in `nes/envelope_processor.py`:
- The constant-volume flag (bit 4, `0x10`) is set whenever a per-frame volume is written
  (`get_envelope_control_byte`) — otherwise the hardware envelope decays the note
  unexpectedly (`docs/APU_ENVELOPE_REFERENCE.md` §4). Missing flag = HIGH (wrong output).
- `get_envelope_value` ADSR phases (attack/decay/sustain/release) stay in `0..15` and the
  percussion special-case (`sustain == 0 and release == 0`) reaches exactly 0 at note end
  without dividing by zero (note the `note_duration - 1 - attack_end` denominator —
  check the 1-frame-note edge case).
- ADSR values in `self.envelope_definitions` are 4-bit-representable and consistent with
  the engine-driven model in `docs/APU_ENVELOPE_REFERENCE.md` §5.

### Dimension 8: 60Hz frame timing & frame counter init
Playback is one frame entry per 1/60s NMI tick; the frame counter `$4017` must be
initialized to disable the hardware sequencer interfering with the NMI engine
(`docs/APU_FRAME_COUNTER_REFERENCE.md` §3–§4; `docs/NES_APU_REFERENCE.md` §3.2). Verify:
- `exporter/exporter_ca65.py` init writes `lda #$40` / `sta $4017` (5-step, IRQ
  disabled). Confirm the value matches the doc's recommended init and that it runs before
  playback. A missing/zero `$4017` init lets the frame IRQ fire — HIGH (timing
  interference), CRITICAL if it can crash the engine.
- The frame model is one-entry-per-tick (`compile_channel_to_frames` iterates integer
  frames). Flag any float tempo→frame accumulation that drifts off the 60Hz grid over a
  song (HIGH; cross-refs the tempo audit, but the *engine* must consume integer frames).

### Dimension 9: Register addresses & $4015 enable correctness
All APU writes must land in `$4000–$4017`; channel enables are `$4015` (`---D NT21`),
frame counter `$4017` (`docs/NES_APU_REFERENCE.md` §3; `docs/APU_LENGTH_COUNTER_REFERENCE.md`
for `$4015` length-counter side effects). Verify in `exporter/exporter_ca65.py`:
- The `APU_*` constants (`APU_PULSE1_CTRL=0x4000` … `APU_STATUS=0x4015`) all fall in the
  window and map to the correct channel/function. Grep every `sta $40xx` in the emitted
  proc bodies and confirm none writes outside `$4000–$4017` or to the wrong channel's
  register.
- The init sequence enables the channels it plays via `$4015` (the `sta $4015` writes
  around the `$4017` init). Writing 0 to a channel's `$4015` bit silences it immediately
  (`docs/NES_APU_REFERENCE.md` §3.1); a channel the song uses but never enabled in
  `$4015` is silent — HIGH.

### Dimension 10: Value-range clamping across the board
A sweep for *every* numeric value that reaches a register, independent of the dimension
that produces it. For each of {note, timer, volume, duty, noise index, dmc level},
confirm a clamp exists on the path from Python value to emitted byte:
- timers → `$0–$7FF` (Dim 5), volumes/duty → 4-bit / 2-bit masks (Dim 1/6), noise index
  → `0–15` (Dim 3), dmc level → 7-bit (Dim 4).
- Pay special attention to *additive* modifications applied after the clamp (vibrato
  pitch_mod added to an already-clamped `pitch`; tremolo added to `base_volume` before
  the final `max(0,min(15,…))`). An additive step downstream of the clamp re-opens the
  range — HIGH if it can exceed hardware range, per the Special Rules table.

## Cross-Dimension Dedup
One root cause (e.g. the shared `note_table` used for both pulse and triangle) may surface
under several dimensions (pitch-table correctness *and* the triangle invariant). Report it
once, in the most actionable dimension, and cross-reference. Note that
`nes/envelope_processor.py` also defines a second, near-duplicate `NESEmulatorCore` — if a
finding lives in the dead copy vs. the live `nes/emulator_core.py`, say which is on the
pipeline path (`process_all_tracks` is the live entry per `_audit-common.md`).

## Output
Write to: **`docs/audits/AUDIT_NES_HARDWARE_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — counts per severity, the highest-risk hardware divergences (anything that
   is wrong on *every* ROM).
2. **Findings** — base format from `_audit-common.md` + `Dimension` + `Hardware ref`.

Then suggest:
```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_<TODAY>.md
```
