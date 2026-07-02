# NH-18: Bytecode engine rewrites `$4003`/`$4007` every frame of a held note — phase-reset click

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
