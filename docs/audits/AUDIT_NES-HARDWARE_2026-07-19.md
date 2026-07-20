# NES Hardware Correctness Audit — 2026-07-19

Scope: the boundary where Python numbers become APU register writes — the four
tone channels (Pulse1/Pulse2/Triangle/Noise) + DPCM. Hot files:
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_engine.asm`, `exporter/exporter_ca65.py`.

Dedup source: `/tmp/audit/issues.json` (18 open issues) + `docs/audits/`.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 3 |
| **Total**| **4** |

New: 1 · Existing: 3

**Headline: the NES-hardware subsystem is clean.** No divergence that is wrong
on every ROM was found. All ~10 dimensions were re-derived from the current code
and every previously-tracked hardware bug that the skill flagged as fixed
(NH-01..NH-11, NH-15..NH-24) was verified to hold. Notably:

- **NH-25 (#167) is fixed in code and can be closed.** The length-counter halt
  bit is now set unconditionally on the pulse control byte
  (`envelope_processor.py:153`, `envelope_bits = 0x30`), so the direct-export
  path no longer risks a hardware length-counter cutting a sustained note. Issue
  #167 is stale-open — the fix is present and covered by tests. See NH-HW-02.
- Every emitted `sta $40xx` lands in `$4000–$4017`; no write to a wrong or
  reserved register. Sweep (`$4001`/`$4005`) is written only at the two init
  sites with `$08` (disabled) and never re-enabled.
- Pulse and Triangle use distinct period tables (`/16` vs `/32`), both floored at
  8 and clamped to `$7FF`; the bytecode engine's unclamped runtime pitch-add was
  re-verified to stay ≤ `$7FF` (the max period 2047 occurs only at low notes
  where the pitch offset is always 0).
- Triangle never receives a pulse-style volume/duty byte on any path.
- Noise mode bit is live end-to-end (a real producer sets `noise_mode: 1`).

The single MEDIUM is a pre-existing defense-in-depth gap (#348). The LOWs are one
stale-open tracker item, one documented inert-scaffolding item (#166), and one
new undocumented magic constant.

---

## Findings

### NH-HW-01: Direct-export APU init never zeroes the DMC DAC ($4011)
- **Severity**: MEDIUM
- **Dimension**: 4 (DPCM/DMC level handling)
- **Location**: `exporter/exporter_ca65.py:462-478` (`reset`), `:848-860` (`init_music`)
- **Status**: Existing: #348 (NH-HW-2026-07-18-1)
- **Description**: The bytecode engine zeroes the DMC direct-load level at init
  (`nes/audio_engine.asm:135-136`, `lda #$00 / sta $4011`) to prevent the
  documented Triangle/Noise mixing DC-offset/muffling quirk. The direct-export
  init paths (`reset` and the project-builder `init_music`) enable channels and
  disable sweep but never write `$00→$4011`, so a soft-reset that leaves a stale
  nonzero DAC level muffles the tone channels until the first sample plays.
- **Evidence**: Both direct-export init blocks write `$4015`, `$4017`, `$4001`,
  `$4005` but contain no `$4011` write; `grep "4011"` across the repo returns
  only `audio_engine.asm:136` and the `APU_DMC_LOAD` constant.
- **Impact**: Direct-export (`--no-patterns`, NROM/MMC1) ROMs only; cosmetic
  muffling on soft-reset, self-corrects once any DPCM sample fires.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2–§3 (direct load `$4011`);
  `docs/APU_MIXER_REFERENCE.md` (DMC DC offset into the tri/noise mixer).
- **Related**: #348; parallels the bytecode-engine init at `audio_engine.asm:135`.
- **Suggested Fix**: Add `lda #$00 / sta $4011` to both `reset` and `init_music`
  APU-init blocks, mirroring `audio_engine.asm`.

### NH-HW-02: NH-25 length-counter halt flag is fixed — issue #167 is stale-open
- **Severity**: LOW (tracker hygiene)
- **Dimension**: 1 (Pulse — control byte)
- **Location**: `nes/envelope_processor.py:144-155`
- **Status**: Existing: #167 (fix verified in place — recommend closing)
- **Description**: #167/NH-25 reported that the direct-export pulse control byte
  omitted the length-counter halt flag (bit 5) mandated by
  `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5, so a sustained note could be cut off
  by the hardware length counter reloaded via `ora #$08` on `$4003`/`$4007`. The
  current code sets `envelope_bits = 0x30` (bit 5 halt **and** bit 4 constant
  volume), so the emitted `pulse1_control`/`pulse2_control` bytes written to
  `$4000`/`$4004` carry the halt flag. With halt set, the length counter never
  decrements, making the per-note `ora #$08` reload inert. The pulse `@silence`
  path also writes `$30` (halt + zero volume). The fix is covered by the passing
  `tests/test_ca65_export.py` / `tests/test_envelope.py` suites.
- **Evidence**: `envelope_processor.py:153` `envelope_bits = 0x30`; direct-export
  writes `sta $4000` from this byte (`exporter_ca65.py:614`). Bytecode engine
  parity: `audio_engine.asm:389/430` `ora #$30`.
- **Impact**: None remaining — informational. #167 should be closed as resolved.
- **Hardware ref**: `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 "Halt Flags Always Set".
- **Related**: #167, #160 (NH-20 real durations), #161 (NH-18 phase guard).
- **Suggested Fix**: Close #167; no code change required.

### NH-HW-03: ADSR/effects envelope catalog is unreachable inert scaffolding
- **Severity**: LOW
- **Dimension**: 7 (Envelope / ADSR)
- **Location**: `nes/envelope_processor.py:18-122`, consumed at
  `nes/emulator_core.py:100-107`
- **Status**: Existing: #166 (closed-as-documented; re-verified still inert)
- **Description**: The non-`default` envelopes (`piano`/`pad`/`pluck`/
  `percussion`) and the `vibrato`/`duty_sequences` effect tables are unreachable
  from any pipeline run. `compile_channel_to_frames` hardcodes `effects=None`
  and `envelope_type` defaults to `'default'`; `grep -rn "envelope_type" --include=*.py`
  outside `tests/` shows **no producer** (parser, track_mapper, arranger). Every
  real note therefore plays the flat `(0,0,15,0)` envelope. The
  divide-by-a-`(note_duration-1-attack_end)` shape in `get_envelope_value`
  (`:84`) has a latent divide-by-zero for a 1-frame percussion note but is
  unreachable while no producer selects `envelope_type="percussion"`.
- **Evidence**: `emulator_core.py:105-107` passes `None` for `effects`; no
  non-test writer of `envelope_type`.
- **Impact**: No timbre variety today; the divide-by-zero becomes a live crash
  the moment an envelope producer (e.g. a GM instrument table) is wired up
  without first guarding the 1-frame case.
- **Hardware ref**: `docs/APU_ENVELOPE_REFERENCE.md` §4 Constant Volume Output,
  §5 Engine Implementation Notes.
- **Related**: #166; NH-19 (#162, the first would-be real consumer).
- **Suggested Fix**: Keep as documented; when a producer is added, guard
  `(note_duration - 1 - attack_end) == 0` in `get_envelope_value` first.

### NH-HW-04: Triangle linear-counter reload uses an undocumented `volume * 7` magic constant
- **Severity**: LOW
- **Dimension**: 2 (Triangle — linear counter)
- **Location**: `exporter/exporter_ca65.py:343-346`
- **Status**: NEW
- **Description**: The direct-export triangle control byte is
  `0x80 | (volume * 7)` when `volume != 0`, else `0x00`. `volume` is the 4-bit
  (0–15) `velocity_to_volume` output, so the low 7 bits become `0..105` — a
  linear-counter *reload* value derived from loudness. Because bit 7 (the linear
  counter control/halt flag) is set, the reload value is continuously re-armed
  and never gates the note, so the `* 7` scaling is functionally inert and
  correct (triangle plays on/off). But the constant `7` has no doc citation and
  the intent (why loudness feeds a halted counter's reload) is opaque; a future
  edit that clears bit 7 would suddenly make this an audible, wrong note-length
  knob. The `docs/APU_TRIANGLE_REFERENCE.md` §4 reload semantics are not
  referenced at the call site.
- **Evidence**: `control = 0x80 | (volume * 7)` at `:346`; `volume` originates
  from `velocity_to_volume` (0–15) via `compile_channel_to_frames`'s non-pulse
  branch. Contrast the bytecode engine, which writes a fixed `$FF` reload
  (`audio_engine.asm:466`) rather than a loudness-scaled one.
- **Impact**: None today (inert). Maintainability / latent-trap risk only;
  a divergence from the bytecode engine's fixed-reload approach.
- **Hardware ref**: `docs/APU_TRIANGLE_REFERENCE.md` §4 (linear counter reload),
  §1 (no volume control).
- **Related**: NH-HW-02 (both concern control-byte constants); the bytecode
  engine's `$FF` reload at `audio_engine.asm:466`.
- **Suggested Fix**: Replace with a named constant (e.g. a fixed max reload
  `0x7F` like the engine's `$FF`-minus-flag, or `0x80 | LINEAR_COUNTER_MAX`) and
  cite `docs/APU_TRIANGLE_REFERENCE.md` §4; the loudness scaling is meaningless
  for a channel with no volume.

---

## Dimensions verified clean (no finding)

- **Dim 1 (Pulse duty/vol/timer/sweep)**: duty masked `(duty & 0x03) << 6`,
  constant-volume `0x10` + halt `0x20` set, volume `& 0x0F`; sweep disabled at
  both init sites (`$08`), never re-enabled; bytecode `$4003`/`$4007` phase-reset
  guard (`last_written_hi`, forced-rewrite on note onset) holds. `PULSE_DUTY_CYCLES`
  confirmed gone.
- **Dim 2 (Triangle invariant)**: `process_all_tracks` routes triangle through the
  non-pulse branch (`default_duty=None`); emitted frame carries only
  `pitch`/`volume`/`note`, no `control`/duty; no `$30` pulse byte leaks to
  `$4008`. (See NH-HW-04 for the reload constant.)
- **Dim 3 (Noise)**: `get_noise_period` is the single source of truth (clamp
  24–60, scale 0–15, invert); `PitchProcessor._get_noise_period` delegates to it;
  mode bit read from `noise_mode` and reachable end-to-end (real producer:
  `enhanced_drum_mapper._noise_mode_for_note`); the 6-frame software decay ramp
  produces audible steps (e.g. `[15,12,10,8,5,2]`) and a re-trigger truncates the
  prior tail (`end_frame = min(end_frame, next_frame)`).
- **Dim 4 (DPCM/DMC)**: `$4011` written only once, at bytecode init, to zero the
  DAC; `dpcm` branch emits `volume:15` as a trigger gate, not a level; the old
  `@cmd_dmc_level` handler is **already removed** from `audio_engine.asm` (better
  than the skill's "still exists as dead code" note). Direct-export `$4011` gap =
  NH-HW-01. Sample residency `$C000-$FFFF` is a mapper-audit cross-ref.
- **Dim 5 (Per-channel pitch tables + 11-bit clamp)**: one parameterized
  `generate_note_table(divider)` builds pulse `/16` and triangle `/32` tables;
  `get_channel_pitch` and `midi_note_to_timer_value` both branch on `triangle`;
  all entries `max(8, min(t, 0x7FF))` (verified: max 2047, min 8 both tables);
  `midi_note_to_timer_value` clamps note 24–119; `apply_pitch_bend` re-clamps.
  Runtime bytecode pitch-add (`adc temp_pitch` with no post-add clamp) verified
  in-range: nonzero offsets only occur for notes >108 whose runtime period is
  tiny, and the max-period 2047 notes always carry offset 0.
- **Dim 6 (Velocity→volume)**: single `velocity_to_volume` (`max(1, int(15 *
  pow(v/127, 1.5)))`), clamped 0–15; envelope combine step `min(15, round(...))`
  cannot reach 16 (both factors ≤15).
- **Dim 7 (Envelope)**: constant-volume flag always set; catalog inert = NH-HW-03.
- **Dim 8 (60Hz/frame counter)**: both init sites + bytecode write `$4017 = $40`
  (4-step mode 0, IRQ inhibit); comments now read "mode 0" (NH-22 fixed); frame
  model iterates integer frames.
- **Dim 9 (Register addresses / $4015)**: all `APU_*` constants in window; init
  enables `$4015 = $0F`, DMC bit 4 set to `$1F` only on sample trigger.
- **Dim 10 (Value-range clamping)**: timers floored-8/clamped-`$7FF`, volume/duty
  masked, noise index `& 0x0F`, dmc "level" is a gate. The two unclamped ASM
  add sites (pitch, arp) re-verified: pitch add stays in range in practice; arp
  add still fed only the neutral `_encode_macro_offset(0)` (no `arp` producer).

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_NES-HARDWARE_2026-07-19.md
```
