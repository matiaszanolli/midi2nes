# Issue #161: NH-18: Bytecode engine rewrites `$4003`/`$4007` every frame of a held note — phase-reset click

**Severity:** MEDIUM · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

## Description
`@process_macros` runs for every channel on every frame — including the `frame_wait > 0`
sustain frames of a note — and the pulse write path has no "timer unchanged, skip `$4003`"
guard. A 4-frame note therefore writes `$4003` four times; per the pulse reference, each
write "immediately restarts the sequencer at the first step … this phase reset is what
causes an audible 'click' or 'pop' if done continuously". It also reloads the length
counter and restarts the (bypassed) envelope each frame. The direct-export path gets this
right with its `@sustain` short-circuit. Triangle's per-frame `$400B` write is harmless (no
phase reset on the triangle sequencer), and noise events are single-frame.

## Location
`nes/audio_engine.asm:176-180` (wait-state frames jump to `@process_macros`), `:381-399`
(`@write_pulse1` — both the fast path and `@p1_pitch_mod` unconditionally `sta $4002` then
`ora #$08 / sta $4003` every frame), `:413-431` (pulse2 identical).

## Evidence
Code path above; every note on the default path is 1-4 frames (NH-20), so essentially all
pulse notes longer than 1 frame click at 60Hz during their sustain.

## Impact
Audible buzz/pop on sustained pulse notes in every default-mode ROM. The standard idiom (cache last timer-high, write `$4003` only when it changes or on note-on) is absent.

## Related
#107/NH-14 (direct-path variant of the same quirk class), NH-16 (same write path).

## Hardware ref
`docs/APU_PULSE_REFERENCE.md` §2 ⚠️ Critical Side Effects; `docs/APU_ENVELOPE_REFERENCE.md`
§2 ⚠️ Trigger Registers (`$4003`/`$4007` restart the envelope).

## Suggested Fix
Track the last written period (or last note) per pulse channel in the engine and skip the
`$4003`/`$4007` write when unchanged (write `$4002` freely — low-byte writes don't reset
phase); or only write timers on note-on / pitch-macro change.

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix

---

# Issue #162: NH-19: Noise percussion has no decay — every drum hit is a one-frame (16.7 ms) tick

**Severity:** MEDIUM · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

## Description
A noise drum hit produces exactly one frame of constant-volume noise. The in-code
justification — "the channel re-fires once, then decays via the length counter" — is
impossible as written: (a) both playback paths set the length-counter halt bit (`$30`),
which prevents any decrement; (b) the constant-volume flag bypasses the hardware envelope,
so there is no envelope decay either; and (c) in bytecode mode the following rest event
writes `$400C = $30` (volume 0) on the next frame anyway. The hardware-doc strategy for NES
percussion is a multi-frame software volume decay via volume macros, which no stage
generates — every `vol_seq` is a constant.

## Location
`nes/emulator_core.py:123-150` (one frame emitted per hit; comment at `:127-129` claims the
hit "decays via the length counter"); exporter direct `exporter/exporter_ca65.py:254`
(`$30 | vol` — halt bit set) and engine `nes/audio_engine.asm:466-469` (`ora #$30`),
`:529-533` (rest frame silences with `$30` on the very next event).

## Evidence
`noise_frames[e['frame']] = {…}` emits a single frame per hit; the bytecode stream for a
hit is `…, $60, period` (length 1) followed by a rest event; the engine's `@silence` fires
one frame later. In direct mode the intended `$30` silence is currently replaced by the
#107 fallthrough chirp.

## Impact
On every drummed song, noise snares/hi-hats are barely-audible clicks rather than percussion. Playable, musically degraded.

## Related
#107 (direct-path note-off artifact on the same channel), NH-20 (tone-side duration gap), #73/#74 (drum-mapping coverage).

## Hardware ref
`docs/APU_NOISE_REFERENCE.md` §6 (software envelopes / "rapid volume macro to simulate
percussion strikes"; also "writing to `$400F` does not reset the phase … we can safely
write to any Noise register on any frame"); `docs/APU_LENGTH_COUNTER_REFERENCE.md` §3
(halt => no decrement) and §5 (halt-always strategy).

## Suggested Fix
Emit a short decay for noise hits — either extend each hit across ~4-8 frames with a
decaying `volume` in `process_all_tracks` (the vol macro system will serialize it for
free), or attach a canned percussion volume macro in the exporter.

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
