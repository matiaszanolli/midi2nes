# NES Hardware Correctness Audit — 2026-07-05

Audit of the boundary where Python numeric values become APU register writes, across the
10 hardware dimensions in `.claude/commands/audit-nes-hardware/SKILL.md`, at HEAD `a7de0d4`.
Hot files: `nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`exporter/exporter_ca65.py`, `nes/audio_engine.asm`, plus the arranger front-end
(`arranger/pipeline_integration.py`, `arranger/voice_allocator.py`) as a second producer
of the same `frames` control bytes this audit gates.

**Purpose of this pass.** (a) Re-verify the two headline findings of the immediately
preceding pass (`AUDIT_NES-HARDWARE_2026-07-03.md`, HEAD `9cfa0e2`) — NH-26 (CRITICAL) and
NH-27 (HIGH) — which were reported but not yet published as issues; (b) confirm the still-open
NH set holds; (c) hunt the `--arranger` volume/duty→control path, which prior NES-hardware
passes only checked on the legacy `emulator_core` path.

**Dedup sources:** `/tmp/audit/issues.json` (33 open issues), all prior reports in
`docs/audits/` — especially `AUDIT_NES-HARDWARE_2026-07-03.md`, `AUDIT_NES_HARDWARE_2026-07-01.md`,
and `AUDIT_ARRANGER_2026-06-29.md` (which checked the arranger control byte but not the
`vel // 8` floor).

## Regression check — prior findings re-verified at HEAD

| Prior finding | Status at `a7de0d4` | Evidence |
|---|---|---|
| **NH-26 (CRITICAL, 2026-07-03)** — drum noise-fallback events lacked a `note` key, crashing `process_all_tracks` with `KeyError` on common percussion | **FIXED** (#195, commit `60522b5`) | `dpcm_sampler/enhanced_drum_mapper.py:336-340` and `:409-413` now append `{"frame", "note": midi_note, "velocity"}` on both the non-pattern and pattern noise-fallback paths; `nes/emulator_core.py:165`'s `e['note']` read is now satisfied |
| **NH-27 (HIGH, 2026-07-03)** — harmony/pulse2 arpeggio-fallback synthesized note-on-only events, capping every chord at the 4-frame default | **FIXED** (#197, commit `60522b5`) | `tracker/track_mapper.py:21-32` adds `_find_matching_note_off`; `apply_arpeggio_fallback` (`:56-97`) now emits a matching `velocity: 0` note-off at the source note's real end frame, so `compile_channel_to_frames`'s note-off search (`nes/emulator_core.py:80-86`) resolves real durations |
| #41/NH-11 (open, LOW) | **Holds** | `PitchProcessor.note_to_timer` (`nes/pitch_table.py:133-139`) still raises for `< 24 or >= 96`, contradicting `CHANNEL_RANGES["pulse1"]=(24,108)`; callers only in `tests/test_pitch_table_integration.py` |
| #107/NH-14 (open, MEDIUM) | **Holds, with a scope correction — see note below** | `sta`-clobbers-Z dead `beq @silence` confirmed on pulse1/pulse2/triangle (`exporter/exporter_ca65.py:456-459`, `:526-530`, `:596-599`) |
| #163/NH-21 (open, MEDIUM) | **Holds** | `EVAL_MACRO` (`nes/audio_engine.asm:58-88`) only tests `cmp #$FF` (`:72`); exporter still emits `$FE` loop control bytes (`exporter/exporter_ca65.py:895`) the engine cannot decode |
| #164/NH-22 (open, LOW) | **Holds** | `$4017=$40` still commented "mode 1" at `exporter/exporter_ca65.py:765`, `nes/audio_engine.asm:131`, `nes/mmc3_init.asm:63`; byte value ($40 = Mode 0/4-step) correct |
| #165/NH-23 (open, LOW) | **Holds** | `NOISE_PERIODS` (`exporter/exporter_ca65.py:40`) and `is_midi_velocity` (`:999`, computed never read) both still dead (grep-confirmed) |
| #166/NH-24 (open, LOW) | **Holds** | No producer of `envelope_type` in `tracker/`, `arranger/`, `dpcm_sampler/`; `get_envelope_control_byte` still called with `effects=None` hardcoded (`nes/emulator_core.py:105`) |
| #167/NH-25 (open, LOW) | **Holds** | `get_envelope_control_byte` (`nes/envelope_processor.py:124`) sets only `0x10`, no `$20` length-halt bit; direct-export `play_pulse1`/`play_pulse2` write that byte to `$4000`/`$4004` and `ora #$08` a length reload into `$4003`/`$4007` (`exporter/exporter_ca65.py:471,493`) |
| #203/NH-28 (open, LOW) | **Holds** | `nes/mmc3_init.asm` still never `.include`d by `nes/project_builder.py` (only a stale strip at `:92`) |
| #204/NH-29 (open, LOW) | **Holds** | `noise_mode` still read-only with no producer (`nes/emulator_core.py:166` sole reference) |

### Scope correction to #107/NH-14

The 2026-07-03 report stated the dead `@silence` branch is present on **all four** tone
procs. This is wrong for **noise**: `play_noise` has no `cmp last_note`/`sta last_note`
sequence — its `beq @silence` (`exporter/exporter_ca65.py:661`) immediately follows the
bare `lda (temp_ptr),y` note load (`:660`), so it tests the load's zero flag and **is
reachable and correct**. #107's fix scope should be narrowed to pulse1/pulse2/triangle
(3 procs), not 4. This is an accuracy note on the existing issue, not a new bug.

## Summary

| Severity | Count (NEW) |
|----------|------:|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 0 |
| **Total NEW** | **1** |

Plus 10 existing open findings re-verified unchanged (not re-counted): #41/NH-11,
#107/NH-14, #163/NH-21, #164/NH-22, #165/NH-23, #166/NH-24, #167/NH-25, #203/NH-28,
#204/NH-29, and the now-fixed NH-26/NH-27 (verified closed).

### Highest-risk hardware divergence

The two headline risks of the last pass (NH-26 CRITICAL, NH-27 HIGH) are **fixed and
verified**, so the subsystem carries no open CRITICAL/HIGH at HEAD. The one new finding is
a MEDIUM fidelity bug scoped to `--arranger` mode: the softest notes are rendered silent
on the pulse channels.

---

## Findings

### NH-30: Arranger pulse channels silence the softest notes — `vel // 8` floors to volume 0 with no `max(1, …)` guard
- **Severity**: MEDIUM
- **Dimension**: 6 (Velocity → 4-bit volume mapping)
- **Location**: `arranger/voice_allocator.py:362,370` (`"volume": vel // 8`), consumed at
  `arranger/pipeline_integration.py:256-257` (`'volume': data['volume']`,
  `'control': (data.get('duty', 2) << 6) | 0x30 | data['volume']`)
- **Status**: NEW
- **Description**: In `--arranger` mode the pulse1/pulse2 per-frame volume is derived as
  `vel // 8` from the MIDI velocity (0–127) with **no floor**. Any note with velocity
  1–7 integer-divides to `0`, so the 4-bit volume nibble is `0` in both the stored
  `volume` field and the control byte (`… | 0x30 | 0` → e.g. `0xB0`): the pitch and duty
  are written but the channel plays at **zero amplitude**, i.e. the note is inaudible.
  The legacy `emulator_core` front-end deliberately avoids exactly this with
  `max(1, int(15 * math.pow(velocity / 127.0, 1.5)))` (`nes/emulator_core.py:112,118`),
  which the SKILL Dimension 6 calls out as the mechanism that "keeps non-zero velocities
  audible via `max(1, …)`". The arranger applies neither the floor nor the power curve;
  the sibling arranger channels do floor (noise: `max(1, min(15, data['volume']))` at
  `pipeline_integration.py:276`; triangle: `15 if vel > 0 else 0` at
  `voice_allocator.py:378`), so only the pulse channels are exposed. The
  exporter's own velocity rescue (`is_midi_velocity` power curve) is dead code
  (#165/NH-23), so nothing downstream restores these notes.
- **Evidence**: `voice_allocator.py:362` `"volume": vel // 8` (127//8 = 15 max, 7//8 = 0);
  `pipeline_integration.py:256-257` copies `data['volume']` straight into both the
  `volume` field and the control byte's low nibble with no `max(1, …)`. Contrast the two
  floored siblings at `pipeline_integration.py:276` and `voice_allocator.py:378`. The
  2026-06-29 arranger audit checked this control byte (`(duty<<6)|0x30|volume`) and
  concluded "volume 0–15 stays in range" — correct as a *range* check, but it did not
  notice that the bottom of that range is reached for ordinary soft (ppp) notes and means
  silence.
- **Impact**: On `--arranger` arrangements, every pulse note softer than MIDI velocity 8
  (the bottom ~6% of the velocity scale — ppp phrasing, fade-ins/outs, ghost notes) is
  emitted silently. The note is not dropped from the data (pitch/duty are written), so it
  passes validation and consumes a frame, but nothing is heard. Blast radius: pulse1
  (melody/lead) and pulse2 (harmony) in arranger mode only; the legacy default pipeline
  and the triangle/noise arranger channels are unaffected. Secondary: because the arranger
  uses linear `vel // 8` while the legacy path uses a 1.5-power curve, the same MIDI plays
  at a different loudness through the two front-ends — a cosmetic inconsistency, not a
  range violation.
- **Related**: #165/NH-23 (the dead exporter velocity rescue that would otherwise have
  masked this), #166/NH-24 (same "arranger/legacy front-ends diverge on note shaping"
  theme), `AUDIT_ARRANGER_2026-06-29.md` §"Pulse control byte range" (checked range, not
  the floor).
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §1 (4-bit volume 0–15 in the control
  byte, `EPPP.VVVV`; volume 0 with the constant-volume flag = silent channel) —
  consistent with the SKILL Dimension 6 requirement that non-zero velocities stay
  audible.
- **Suggested Fix**: Floor the pulse volume at 1 for any active note, mirroring the
  legacy path — e.g. `"volume": max(1, vel // 8)` in `voice_allocator.py:362,370`, or
  apply `max(1, …)` in `pipeline_integration.py:257` where the noise path already does.
  For parity with the legacy loudness curve, consider reusing
  `max(1, int(15 * math.pow(vel / 127.0, 1.5)))` in both front-ends.

---

## Dimension coverage notes (verified clean at HEAD, no new findings)

- **Dim 1** (Pulse): duty `(d & 0x03) << 6`, constant-volume `0x10`, 4-bit volume mask all
  correct (`nes/envelope_processor.py:119-124`). Sweep disabled ($08) at both live init
  sites. NH-25 (halt bit) unchanged. Arranger pulse control byte
  `(duty<<6)|0x30|volume` sets both halt (`0x20`) and const-vol (`0x10`) — actually
  *more* complete than the direct-export byte; duty from `DutyCycle` enum is 0–3
  (`arranger/gm_instruments.py:48-51`), in range.
- **Dim 2** (Triangle): non-pulse core branch carries no duty/volume control byte
  (`nes/emulator_core.py:114-126`); direct-export derives `$4008` from `0x80 | vol*7`
  independently (`exporter/exporter_ca65.py:202`); arranger writes constant `0x81`
  (`pipeline_integration.py:266`). No pulse-style volume/duty leaks into `$4008`/`$400B`.
- **Dim 3** (Noise): `get_noise_period` clamp+invert (`nes/pitch_table.py:62-75`) and the
  `PitchProcessor._get_noise_period` delegation remain in lockstep. Software decay ramp
  (`NOISE_DECAY_FRAMES = 6`) produces audible steps for typical hits and truncates on
  re-trigger (`nes/emulator_core.py:158-186`). Mode bit reaches `$400E` bit 7 correctly
  but has no producer (#204/NH-29).
- **Dim 4** (DPCM): `$4011` zeroed only at the two live init sites; dense per-song
  `sample_id` remap (`nes/emulator_core.py:214-235`, #200) avoids the byte-ceiling
  aliasing; `@cmd_dmc_level` handler still has no producer.
- **Dim 5/10** (Pitch tables / clamping): pulse `/16` vs triangle `/32` tables distinct
  and single-sourced (`nes/pitch_table.py:51-52`), both `max(8, min(t, 0x7FF))`.
  `midi_note_to_timer_value` 24–119 clamp holds (#158). The engine's pitch-macro and
  arpeggio adds remain structurally unclamped but inert (no producer of nonzero
  `pitch_seq`/`arp`), consistent with prior passes.
- **Dim 6** (Velocity→volume): legacy path floored/power-curved and bound-checked
  (max product 225/15 = 15.0, cannot round to 16). Arranger pulse path is the NH-30
  gap above.
- **Dim 7** (Envelope): constant-volume bit unconditionally set; percussion
  divide-by-zero shape unreachable (no `envelope_type="percussion"` producer).
- **Dim 8/9** (Frame counter / register window / `$4015`): `$4017=$40` + `$4015=$0F`
  before playback on both live init paths; every emitted `sta $40xx` lands in
  `$4000–$4017` on the correct register. `nes/mmc3_init.asm`'s third copy is dead
  (#203/NH-28).

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_NES-HARDWARE_2026-07-05.md
```
