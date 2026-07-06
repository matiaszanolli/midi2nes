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
`nes/audio_engine.asm` (the live bytecode playback engine), and the serializer
`exporter/exporter_ca65.py`.

> **Note on recent history**: this repo just closed ~100 issues in a bug-fixing sprint.
> Most hardware bugs previously tracked here (NH-01..NH-11, NH-15..NH-24) are now
> **fixed** — the bullets below describe the current (fixed) behavior and ask you to
> verify the fix is complete/holds under edge cases, rather than hunt for the original
> bug. A smaller set (NH-14, NH-25) is still **open** — keep hunting those at full
> strength. Don't assume either list is exhaustive; re-derive from the code.

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
- The duty ID reaching `get_envelope_control_byte` is one of the four legal NES
  duties (0–3 → 12.5/25/50/75%). The old `PULSE_DUTY_CYCLES` 8-bit constant that
  contradicted the 2-bit field is confirmed **removed** (#108/NH-15 — `grep -rn
  PULSE_DUTY_CYCLES` across the repo returns nothing outside history). Verify no
  new duty producer reintroduces an out-of-0–3 value.
- Timer write order / phase-reset click (`docs/APU_PULSE_REFERENCE.md` §3 "Critical
  Side Effects" / `docs/NES_APU_REFERENCE.md` §2.1): rewriting Timer High
  (`$4003`/`$4007`) restarts the pulse sequencer's phase regardless of the value
  written. This is **fixed in the live bytecode engine** — `nes/audio_engine.asm`
  caches the last-written high byte per pulse channel (`last_written_hi`, `.res 5`)
  and only issues `sta $4003`/`sta $4007` when the value changed (`@p1_write_hi`/
  `@p2_write_hi`, #161/NH-18), forcing a rewrite at genuine note onset via the
  cmp-then-branch guard. The direct-export path (`exporter/exporter_ca65.py`'s
  `play_pulse1`/`play_pulse2` procs) never had this bug — its `@sustain` label is a
  bare `rts` that touches no registers when the note is unchanged. Verify the
  bytecode engine's guard holds across bank switches / instrument changes.
- Sweep (`$4001`/`$4005`): confirmed disabled at **both** init sites — the standalone
  `reset` proc and the project-builder `init_music` routine
  (`exporter/exporter_ca65.py`, `lda #$08` / `sta $4001` / `sta $4005`). `$08` =
  `EPPP.NSSS` with `E` (enable, bit 7) clear, which disables the unit per
  `docs/APU_PULSE_REFERENCE.md` §2 regardless of the stray negate bit — confirm this
  reading and that no other code path re-enables sweep afterward (a stale sweep left
  enabled silently bends pitch — HIGH per Special Rules).
- **Open (NH-25, #167)**: the direct-export `play_pulse1`/`play_pulse2` "new note"
  path writes the control byte straight from `pulse1_control`/`pulse2_control`
  (`sta $4000`/`sta $4004`), which is `duty_bits | 0x10 | volume` from
  `get_envelope_control_byte` — **bit 5 (length-counter halt) is never set**.
  `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 "Engine Implementation Notes" mandates
  the halt flag always be set so the 60Hz software model isn't undercut by the
  hardware length counter. The same routine's timer-hi write (`ora #$08` before
  `sta $4003`/`sta $4007`) reloads a real (short) length-counter value on every new
  note. Now that NH-20 (#160) is fixed and real note durations flow through instead
  of a 4-frame cap, a direct-export note held longer than the reloaded length-counter
  value **will** be cut off mid-note by hardware, independent of continued frame
  writes — this is no longer a purely latent/masked bug. Verify whether this
  actually reproduces with a long sustained note through `--no-patterns` export.

### Dimension 2: Triangle — the no-volume / no-duty invariant + linear counter
This is the highest-yield dimension. The Triangle channel (`$4008–$400B`) has **no
volume and no duty** (`docs/APU_TRIANGLE_REFERENCE.md` §1; `docs/NES_APU_REFERENCE.md`
§2.2). Verify, skeptically:
- `nes/emulator_core.py:process_all_tracks` routes `triangle` through
  `compile_channel_to_frames` with `default_duty=None` (the `'pulse' in channel_name`
  test). Confirm the non-pulse branch is taken — the emitted frame dict for triangle
  carries only `pitch`/`volume`/`arpeggio`/`note`, **no `control`/duty key at all**.
  Any path that writes a duty or 4-bit volume into a triangle register ($4008/$400B)
  is **HIGH** per the Special Rules table.
- In `exporter/exporter_ca65.py`'s `export_direct_frames`, the triangle control byte
  is derived independently from `volume` (`0x80 | (volume * 7)` when nonzero, `0x00`
  when silent) — this is a real linear-counter reload
  (`docs/APU_TRIANGLE_REFERENCE.md` §4), not a borrowed pulse control byte. Confirm
  no `$30`-style "duty + constant volume" constant leaks into the triangle path.
- Note-off: `nes/audio_engine.asm`'s `@silence_tri` writes `$80` (halt bit set, zero
  reload — "Linear Counter Halt", per `docs/APU_TRIANGLE_REFERENCE.md` §5) and the
  direct-export `@silence` label writes `$00` to `$4008`; the "new note" fallthrough
  (relevant to NH-14 below) also writes `$00` at true rest frames. Confirm none of
  these paths writes a pulse-style volume into `$4008`.

### Dimension 3: Noise — period table & mode flag
Noise is at `$400C–$400F`; frequency is a **4-bit index** into a 16-entry table, mode is
bit 7 of `$400E` (`docs/APU_NOISE_REFERENCE.md` §3–§4; `docs/NES_APU_REFERENCE.md` §2.3).
NH-04 (#20) — the module/instance disagreement and the dropped period — is **fixed**;
verify it holds:
- `get_noise_period` in `nes/pitch_table.py` is now the single source of truth: it
  clamps the note to `CHANNEL_RANGES["noise"]` (24–60), scales to 0–15, and inverts
  (`15 - scaled`) so a higher MIDI note maps to a *lower* index → higher frequency
  (`docs/APU_NOISE_REFERENCE.md` §3). `PitchProcessor._get_noise_period` now delegates
  to this same function instead of carrying a divergent second implementation —
  confirm both call sites still agree.
- `nes/emulator_core.py:process_all_tracks`'s `noise` branch now computes a real
  period via `self.midi_to_nes_pitch(e['note'], 'noise')` (floored at 1, since 0 is
  the bytecode rest sentinel) and reads `noise_mode` from the event
  (`e.get('noise_mode', 0) & 1`) instead of hardcoding mode 0 — confirm the mode bit
  is still reachable end-to-end (does any producer ever set `noise_mode: 1`, or is
  it dead-but-correct plumbing?).
- NH-19 (#162, noise decay) is fixed: `process_all_tracks` now bakes a
  `NOISE_DECAY_FRAMES = 6` software volume ramp per hit (`peak_volume * (span -
  offset) / span`, floored at 1), cut short by a re-trigger. Verify the ramp still
  reaches audible decay (not all frames rounding to the same value) and that a
  rapid re-trigger correctly truncates the previous hit's tail rather than
  overlapping it.

### Dimension 4: DPCM / DMC — level handling
DMC is at `$4010–$4013`; direct level load is `$4011` (7-bit, `docs/APU_DMC_REFERENCE.md`
§2–§3). NH-05 (#24) — "level has a consumer but no producer, not 7-bit clamped" — is
**fixed by removing the dead path** rather than wiring it up (#71/#72). Verify:
- `nes/emulator_core.py:process_all_tracks`'s `dpcm` branch emits `volume: 15` as a
  boolean-ish trigger gate (consumed only to decide whether the sample fires that
  frame), not as a level to write to `$4011` — there is no "DMC volume" register on
  real hardware, so this is correct as long as nothing downstream reinterprets it as
  a level.
- `nes/audio_engine.asm` and `nes/mmc3_init.asm` both write `$4011` **only** to reset
  the DMC DAC to 0 at init (preventing the documented Triangle/Noise mixing-DC-offset
  quirk) — confirm this is the only live `$4011` write.
- The `@cmd_dmc_level` handler in `nes/audio_engine.asm` (reads a 7-bit level operand
  and writes it to `$4011`) still exists, but `exporter/exporter_ca65.py` never emits
  the `CMD_DMC_LEVEL`/`$87` opcode that would trigger it (confirmed by
  `tests/test_ca65_export.py::test_dmc_level_command_path_removed`). This consumer is
  now dead code with no producer — flag as LOW (dead code) unless you find a
  resurrected producer.
- Sample address/length alignment ($4012/$4013) and the `$C000–$FFFF` residency
  constraint (`docs/APU_DMC_REFERENCE.md` §4; `docs/NES_APU_REFERENCE.md` §2.4) — if
  the generated project can place samples outside that window, note it (cross-refs
  the mapper audit).

### Dimension 5: Per-channel pitch-table correctness + 11-bit clamp
The pulse and triangle channels do **not** share a period table — for the same 11-bit
period the pulse sounds one octave above the triangle (`docs/APU_PITCH_TABLE_REFERENCE.md`
§1; `docs/NES_APU_REFERENCE.md` §2.2 "Triangle … one octave lower"). NH-02/NH-03
(#12/#16) are **fixed**; verify:
- `nes/pitch_table.py` now builds both tables from one parameterized
  `generate_note_table(divider)` — `NES_NOTE_TABLE` (divider 16, pulse) and
  `NES_TRIANGLE_TABLE` (divider 32, triangle) — and `PitchProcessor.get_channel_pitch`
  branches on `channel_type == "triangle"` to index `self.triangle_table` instead of
  the shared pulse table. Confirm both the frame-generation path
  (`nes/emulator_core.py`) and the exporter's own base-timer lookup
  (`CA65Exporter.midi_note_to_timer_value`, which branches on `channel == 'triangle'`
  to pick `NES_TRIANGLE_TABLE`) stay on the same table so the pitch and the base
  timer it's differenced against don't scale-mismatch (#16).
- Every timer is clamped to 11-bit `$0–$7FF` **and floored at 8** (not 0):
  `generate_note_table` does `max(8, min(timer, 0x07FF))` — the floor-at-8 is
  deliberate, since `t < 8` silences pulse/triangle
  (`docs/APU_PULSE_REFERENCE.md` §3/§7); `apply_pitch_bend` re-applies the same
  `max(8, min(…, 0x07FF))` clamp after bending.
- NH-16 (#158, sub-C1 notes) is fixed: `CA65Exporter.midi_note_to_timer_value` now
  clamps the note to `24–119` instead of returning a bare `0` for out-of-range notes,
  so the `+127`-clamped pitch-offset macro can no longer wrap the 11-bit timer.
  Verify the clamp bounds (`24`, `119`) are still consistent with `CHANNEL_RANGES`
  elsewhere.
- **Open / re-verify**: the skill previously flagged an `EnvelopeProcessor.
  get_pitch_modification` vibrato path adding to an already-clamped pitch with no
  re-clamp — that entire method and its dead-copy `NESEmulatorCore` host were
  **removed** (#37/#38/NH-10; see Cross-Dimension Dedup note below), so this specific
  described path no longer exists. The *live* additive-pitch site is now
  `nes/audio_engine.asm`'s macro evaluator: `EVAL_MACRO 4, macro_steps_pitch, ...`
  produces `temp_pitch`/`temp_pitch_hi` (sign-extended), which is added via
  `adc temp_pitch` / `adc temp_pitch_hi` directly onto `ntsc_period_low`/`_high` (or
  the triangle table) before `sta $4002/$4003` etc., with **no re-clamp to `$7FF`**
  afterward. This is currently inert — no pipeline stage ever emits a nonzero pitch
  macro delta (see NH-24, Dimension 7) — but is a latent 11-bit-overflow trap
  structurally identical to the one already fixed in the dead duplicate core. Flag as
  a verify-only item unless you can show a live producer of nonzero `pitch_seq`.
- The `t < 8` silence quirk (`docs/APU_PULSE_REFERENCE.md` §3 / `docs/NES_APU_REFERENCE.md`
  §2.1): timers under 8 silence the channel; confirmed floored at 8 (above). Flag if
  any new code path can still push a nonzero pitch below 8.

### Dimension 6: Velocity → 4-bit volume mapping
APU volume is 4-bit (0–15) on pulse/noise (`docs/APU_PULSE_REFERENCE.md` §1;
`docs/APU_NOISE_REFERENCE.md` §2); MIDI velocity is 0–127. NH-08 (#34, dead/contradictory
pulse-volume expression) is **fixed** — `nes/emulator_core.py:compile_channel_to_frames`'s
pulse branch and non-pulse branch both now use a single clean expression,
`max(1, int(15 * math.pow(velocity / 127.0, 1.5)))` (velocity 0 is filtered out earlier
by the `continue` on note-off, so the old unreachable `velocity == 0` ternary arm is
gone). Verify:
- Output stays clamped to `0..15` in all three computation sites: `emulator_core.py`'s
  two branches and `envelope_processor.py:get_envelope_control_byte`'s
  `min(15, round((envelope_volume * midi_volume) / 15.0))` combination step (both
  factors are already ≤15, so the product/15 can't exceed 15, but confirm the
  `round()` can't tip it to 16 at the boundary).
- The `pow(velocity/127, 1.5)` curve keeps non-zero velocities audible via
  `max(1, …)` — a curve that under/overshoots but stays in range is MEDIUM; emitting
  outside `0..15` is HIGH.

### Dimension 7: Envelope / ADSR behavior
The engine bypasses the hardware envelope and drives constant volume per frame
(`docs/APU_ENVELOPE_REFERENCE.md` §4 Constant Volume Output, §5 Engine Implementation).
**Closed as documented (NH-24, #166)**: the ADSR/effects/arpeggio plumbing is
intentionally inert scaffolding (kept for a future GM-based producer), not a bug to
fix — but the behavior below still holds, so verify it hasn't silently changed. Check in
`nes/envelope_processor.py` and its only caller (`nes/emulator_core.py`):
- `compile_channel_to_frames` calls `get_envelope_control_byte(envelope_type,
  frame_offset, ..., default_duty, None, velocity)` with the `effects` argument
  **hardcoded to `None`** — tremolo and `duty_sequence` are therefore unreachable
  from any real pipeline run (only tests exercise them directly). `envelope_type`
  defaults to `event.get('envelope_type', 'default')`, and `grep -rn
  "envelope_type" --include=*.py .` outside `tests/` shows **no producer** (parser,
  track_mapper, or arranger) ever sets this key — every real note plays the flat
  `"default"` envelope `(attack=0, decay=0, sustain=15, release=0)`. Confirm this is
  still true after any arranger/instrument work and flag as a real (if inert-for-now)
  missing-feature finding, not just dead code — the whole `piano`/`pad`/`pluck`/
  `percussion` envelope catalog and the vibrato/duty-sequence effects table are
  unreachable production code.
- The constant-volume flag (bit 4, `0x10`) is still set unconditionally in
  `get_envelope_control_byte` — confirm this remains true (missing it would be HIGH,
  wrong output).
- The percussion-envelope division `(frame_offset - attack_end) / (note_duration - 1
  - attack_end)` in `get_envelope_value` has a real divide-by-zero shape for a
  1-frame note, but since no producer ever selects `envelope_type="percussion"` (per
  the point above) this path is currently unreachable in production — confirm that
  remains true, or it becomes a live crash risk the moment an envelope producer is
  wired up.
- Cross-ref Dimension 1 (NH-25): the length-counter halt bit is a related "constant
  output, no hardware decay" concern but lives on the pulse *control byte* path, not
  here.

### Dimension 8: 60Hz frame timing & frame counter init
Playback is one frame entry per 1/60s NMI tick; the frame counter `$4017` must be
initialized to disable the hardware sequencer interfering with the NMI engine
(`docs/APU_FRAME_COUNTER_REFERENCE.md` §2–§3; `docs/NES_APU_REFERENCE.md` §3.2). Verify:
- Both init sites (`exporter/exporter_ca65.py`'s standalone `reset` proc and the
  project-builder `init_music`) write `lda #$40` / `sta $4017` before playback starts
  — `$40` = `%01000000`, i.e. Mode bit (bit 7) clear = **4-step mode**, Interrupt
  Inhibit (bit 6) set = frame IRQ disabled (`docs/APU_FRAME_COUNTER_REFERENCE.md` §2
  Register Map, §3 Sequencer Modes). This is the correct value.
- **Fixed (NH-22, #164)**: `init_music`'s comment on that line previously read `; Frame
  counter mode 1, disable frame IRQ`, which was doc-rot — `$40` is **mode 0** (4-step),
  not mode 1 (5-step is `$C0`/`$80`). Both live init sites now read `4-step mode
  (mode 0)` (`exporter/exporter_ca65.py` init_music and `nes/audio_engine.asm`'s
  `$4017` write). Confirm the comment still matches the byte and no new init path
  reintroduces the wrong "mode 1" description.
- The frame model is one-entry-per-tick (`compile_channel_to_frames` iterates integer
  frames `range(start_frame, end_frame)`). Flag any float tempo→frame accumulation
  that drifts off the 60Hz grid over a song (HIGH; cross-refs the tempo audit, but
  the *engine* must consume integer frames).

### Dimension 9: Register addresses & $4015 enable correctness
All APU writes must land in `$4000–$4017`; channel enables are `$4015` (`---D NT21`),
frame counter `$4017` (`docs/NES_APU_REFERENCE.md` §3; `docs/APU_LENGTH_COUNTER_REFERENCE.md`
for `$4015` length-counter side effects). Verify in `exporter/exporter_ca65.py`:
- The `APU_*` constants (`APU_PULSE1_CTRL=0x4000` … `APU_STATUS=0x4015`) all fall in the
  window and map to the correct channel/function. Grep every `sta $40xx` in the emitted
  proc bodies and confirm none writes outside `$4000–$4017` or to the wrong channel's
  register.
- Both init sites enable channels via `$4015 = $0F` (Pulse1/Pulse2/Triangle/Noise) and
  leave DMC (bit 4) off until a sample actually triggers, at which point `@write_dpcm`
  (`nes/audio_engine.asm`) / `play_dpcm` (`exporter/exporter_ca65.py`) write `$1F`.
  Confirm every channel the song actually uses is covered by one of these two paths —
  a channel used but never enabled in `$4015` is silent (HIGH).

### Dimension 10: Value-range clamping across the board
A sweep for *every* numeric value that reaches a register, independent of the dimension
that produces it. For each of {note, timer, volume, duty, noise index, dmc level},
confirm a clamp exists on the path from Python value to emitted byte:
- timers → `$0–$7FF` floored at `8` (Dim 5), volumes/duty → 4-bit / 2-bit masks
  (Dim 1/6), noise index → `0–15` (Dim 3), dmc level → not applicable post-fix (Dim 4;
  the "level" is a trigger gate now, not a register value).
- **Live unclamped-add sites to re-verify** (both currently fed only zero deltas per
  NH-24, but structurally unguarded): `nes/audio_engine.asm`'s pitch macro add
  (`adc temp_pitch` / `adc temp_pitch_hi` onto the period tables, no post-add clamp to
  `$7FF`) and its arpeggio add (`clc; lda current_note, x; adc temp_arp; sta
  temp_note` — an 8-bit add with no range check before `temp_note` is used to index
  the 128-entry period tables via `ldy temp_note`). Both are additive steps
  *downstream* of the table's own clamp, matching the pattern already fixed once in
  the dead duplicate core (#38/NH-10) — HIGH if either ever receives a live nonzero
  input without a guard being added first.

## Cross-Dimension Dedup
One root cause (e.g. the shared triangle/pulse pitch table, now fixed) may surface
under several dimensions (pitch-table correctness *and* the triangle invariant). Report
it once, in the most actionable dimension, and cross-reference.

Historical note: `nes/envelope_processor.py` used to define a second, near-duplicate
`NESEmulatorCore` (with a vibrato path that added `pitch_mod` to an already-clamped
pitch, no re-clamp) plus the `get_pitch_modification` method that was its only caller.
Both were **removed** in #37/#38 (NH-10) — `nes/envelope_processor.py` now contains only
`EnvelopeProcessor`. `nes/emulator_core.py`'s `process_all_tracks` remains the single
live entry point per `_audit-common.md`; if you find any lingering reference to the old
dead copy (docs, tests, comments), it's stale and should be flagged LOW (doc-rot), not
re-litigated as a hardware bug.

## Output
Write to: **`docs/audits/AUDIT_NES_HARDWARE_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — counts per severity, the highest-risk hardware divergences (anything that
   is wrong on *every* ROM).
2. **Findings** — base format from `_audit-common.md` + `Dimension` + `Hardware ref`.

Then suggest:
```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_<TODAY>.md
```
