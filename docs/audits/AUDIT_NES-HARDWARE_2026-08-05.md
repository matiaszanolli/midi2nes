# NES Hardware Correctness Audit — 2026-08-05

Scope: the boundary where Python numbers become APU register writes — the four
tone channels (Pulse1/Pulse2/Triangle/Noise) + DPCM. Hot files:
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_engine.asm`, `exporter/exporter_ca65.py`. Cross-checked against
`arranger/voice_allocator.py` and `arranger/pipeline_integration.py` where the
skill's dimensions ask "is this producer live end-to-end".

Dedup source: `/tmp/audit/issues.json` (38 open issues, `gh issue list` default
scope) + `docs/audits/` history, in particular the previous NES-hardware pass
(`docs/audits/AUDIT_NES-HARDWARE_2026-07-19.md`) and the same-day arranger pass
(`docs/audits/AUDIT_ARRANGER_2026-07-19.md`).

Commits touching hardware-adjacent code since the last pass:
`7a2054d` (#364, triangle reload constant — verified fixed),
`bc5467a` (#359/#360, arranger noise strike decay — verified fixed and shared),
`36348ce` (#361–#363, mapper auto-select/capacity — mapper-audit domain, not
re-litigated here).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 2 |
| LOW      | 2 |
| **Total**| **4** |

New: 1 · Existing: 3

**Headline: the NES-hardware subsystem remains clean — no divergence wrong on
every ROM.** All ten dimensions were re-derived from the current code (not
just re-read from the prior report) and every previously-tracked fix
(NH-01..NH-11, NH-15..NH-25, NH-HW-04) was independently re-verified to still
hold, including the pulse length-counter halt bit, the triangle
volume/duty invariant, the 11-bit timer clamps on both pitch tables, the
`$4017`/`$4015`/sweep init sequence, and the bytecode engine's phase-reset
guard (`last_written_hi`) across bank switches and instrument changes.

The one **new** finding is a genuine, previously-mischaracterized gap: the
`--arranger` front-end can never emit the noise mode bit ($400E bit 7) for
metallic percussion (hi-hats, cowbell), even though the legacy front-end does
so unconditionally via `enhanced_drum_mapper.py`'s `METALLIC_NOISE_ROLES`
(#204/NH-29). The same-day arranger audit characterized this as "parity, not
a regression" — this pass finds that conclusion needs revising now that the
legacy producer's behavior is deterministic and role-specific rather than
"rarely set" at random.

The two MEDIUM/LOW-existing items (#348, #167) remain open and unfixed/stale
respectively; both are re-confirmed present in the current code exactly as
previously reported. One LOW item (#166) is closed-as-documented and
re-verified to still hold.

---

## Findings

### NH-HW-2026-08-05-1: `--arranger` drum mapping has no producer for the noise mode bit — hi-hats/cowbell lose their metallic timbre
- **Severity**: MEDIUM
- **Dimension**: 3 (Noise — period table & mode flag)
- **Location**: `arranger/gm_instruments.py:1191-1264` (`DrumMapping` dataclass
  and `GM_DRUM_MAP`), `arranger/voice_allocator.py:314-343` (`_allocate_noise`),
  `:456-461` (`process_song` noise frame emission),
  `arranger/pipeline_integration.py:282-290` (`arrange_for_nes` noise conversion)
- **Status**: NEW (refines the "parity, not a regression" verdict in
  `docs/audits/AUDIT_ARRANGER_2026-07-19.md` lines 182-185)
- **Description**: `docs/APU_NOISE_REFERENCE.md` §6 recommends Mode 1
  (periodic/short-LFSR, "a harsh, metallic buzzing tone with a discernible
  pitch") for hi-hats and cowbells rather than the default long-mode noise.
  The legacy front-end implements this: `dpcm_sampler/enhanced_drum_mapper.py`
  defines `METALLIC_NOISE_ROLES = {"hihat_closed", "hihat_open",
  "hihat_pedal", "cowbell"}` and `_noise_mode_for_note` unconditionally
  returns mode 1 for any GM percussion note that maps to one of those roles
  (#204/NH-29), threading a real `noise_mode` key through to
  `nes/emulator_core.py:164` (`e.get('noise_mode', 0) & 1`) and from there into
  `$400E` bit 7 via both exporters.

  The `--arranger` front-end has **no equivalent concept anywhere in its data
  model**. `arranger/gm_instruments.py`'s `DrumMapping` dataclass carries only
  `channel`, `play_style`, `priority`, and `noise_period` — no mode/periodic
  field exists on any of the ~35 percussion entries in `GM_DRUM_MAP`, including
  the four hi-hat/cowbell entries that the legacy path special-cases
  (`Closed Hi-Hat`/`Pedal Hi-Hat`/`Open Hi-Hat`/`Cowbell`). `_allocate_noise`
  (`voice_allocator.py:314-343`) returns only `(noise_period, velocity)`; the
  per-frame noise dict built in `process_song` (`:456-461`) carries only
  `"period"` and `"volume"` keys, never `"mode"`. `arrange_for_nes`'s
  noise-conversion step (`pipeline_integration.py:285`) reads
  `data.get('mode', 0) & 1` from that dict — a key that is structurally never
  present — so the conversion's own default (`0`) is the only value that can
  ever reach `$400E` bit 7 on this front-end. Every `--arranger` percussion
  track therefore renders exclusively as long-mode noise, regardless of GM
  drum role.

  The prior arranger audit (`AUDIT_ARRANGER_2026-07-19.md` lines 182-185)
  found this same code shape but concluded "the legacy path is equally
  mode-0-by-default... this is parity, not a regression". That
  characterization undercounts the legacy path: `_noise_mode_for_note` is not
  probabilistic or "rare" — it is a deterministic function of `DEFAULT_MIDI_
  DRUM_MAPPING`, so *every* closed/open/pedal hi-hat and cowbell hit routed to
  the noise-fallback path plays with mode 1 on the legacy front-end, 100% of
  the time. `--arranger` can never reproduce that, for any input.
- **Evidence**:
  ```python
  # dpcm_sampler/enhanced_drum_mapper.py:221-224 (legacy — live producer)
  def _noise_mode_for_note(self, midi_note: int) -> int:
      return 1 if DEFAULT_MIDI_DRUM_MAPPING.get(midi_note) in METALLIC_NOISE_ROLES else 0
  ...
  noise_events.append({
      "frame": frame, "note": midi_note, "velocity": velocity,
      "noise_mode": self._noise_mode_for_note(midi_note),   # real 0/1
  })
  ```
  ```python
  # arranger/gm_instruments.py:1191-1198 — no mode/periodic field exists
  class DrumMapping:
      name: str
      channel: NESChannel
      play_style: PlayStyle
      priority: int
      noise_period: Optional[int] = None   # for noise channel (0-15)
      # (no mode / is_metallic / periodic field anywhere in the dataclass)
  ```
  ```python
  # arranger/pipeline_integration.py:282-290 — 'mode' key never present upstream
  for frame, data in frames['noise'].items():
      ...
      mode = data.get('mode', 0) & 1     # always 0 -- process_song never writes 'mode'
      output['noise'][frame] = {'note': period, 'control': mode << 6, 'volume': volume}
  ```
  `grep -n "\"mode\"\|'mode'" arranger/voice_allocator.py` returns no hits in
  `_allocate_noise`/`process_song`/`_apply_noise_strike_decay`.
- **Impact**: Every song run through `--arranger` with GM hi-hats or a cowbell
  loses the intended metallic/periodic noise timbre and instead plays generic
  long-mode noise on those hits — audible on any drum-heavy track, and a
  regression in perceived quality relative to the legacy pipeline for exactly
  the GM roles #204/NH-29 was written to fix. Not a hardware-range violation
  (mode 0 is a legal value) and there is a workaround (use legacy/non-arranger
  mode), so this stays MEDIUM rather than HIGH.
- **Hardware ref**: `docs/APU_NOISE_REFERENCE.md` §6 (periodic/metallic mode
  recommendation for hi-hat/cowbell-type percussion); §4 (mode bit is `$400E`
  bit 7).
- **Related**: #204/NH-29 (the legacy producer this gap fails to mirror);
  `docs/audits/AUDIT_ARRANGER_2026-07-19.md` lines 182-185 (the "parity, not a
  regression" note this finding revises); cross-references `/audit-arranger`
  Dimension 3/7 territory as much as this skill's Dimension 3 — file under
  whichever domain label the tracker prefers, the underlying gap is one issue.
- **Suggested Fix**: Add a `periodic: bool = False` (or `mode: int = 0`) field
  to `DrumMapping`, set it `True` on the four `METALLIC_NOISE_ROLES`-equivalent
  `GM_DRUM_MAP` entries (Closed/Pedal/Open Hi-Hat, Cowbell), thread it through
  `_allocate_noise` → `process_song`'s noise frame dict (`"mode": ...`) →
  `arrange_for_nes`'s existing `data.get('mode', 0)` read (already wired to
  consume it once produced).

### NH-HW-2026-08-05-2: Direct-export APU init still never zeroes the DMC DAC ($4011)
- **Severity**: MEDIUM
- **Dimension**: 4 (DPCM/DMC level handling)
- **Location**: `exporter/exporter_ca65.py:474-517` (`reset`), `:876-892`
  (`init_music`)
- **Status**: Existing: #348 (NH-HW-2026-07-18-1) — re-verified still present,
  unfixed
- **Description**: Unchanged from the prior two audits. The bytecode engine
  zeroes the DMC direct-load level at init (`nes/audio_engine.asm:135-136`,
  `lda #$00 / sta $4011`) to avoid the documented Triangle/Noise mixer
  DC-offset quirk. Both direct-export init blocks (`reset` and the
  project-builder `init_music`) still write `$4015`/`$4017`/`$4001`/`$4005`
  but no `$4011` — confirmed by `grep -n "4011" exporter/exporter_ca65.py`
  returning only the unused `APU_DMC_LOAD` constant definition, no `sta`.
- **Evidence**: `exporter/exporter_ca65.py:493-504` (`reset`'s APU-init block)
  and `:877-889` (`init_music`) both omit `sta $4011`; contrast
  `nes/audio_engine.asm:135-136`.
- **Impact**: Direct-export (`--no-patterns`, NROM/MMC1) ROMs only; cosmetic
  muffling of tone channels on a soft-reset that leaves a stale nonzero DAC
  level, self-corrects once any DPCM sample fires. No change from the last
  two audits' assessment.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2-§3 (direct load `$4011`);
  `docs/APU_MIXER_REFERENCE.md` (DMC DC offset into the tri/noise mixer).
- **Related**: #348; parallels `nes/audio_engine.asm:135`.
- **Suggested Fix**: Add `lda #$00 / sta $4011` to both `reset` and
  `init_music` APU-init blocks, mirroring `audio_engine.asm`.

### NH-HW-2026-08-05-3: NH-25 length-counter halt fix confirmed in code — #167 remains stale-open
- **Severity**: LOW (tracker hygiene)
- **Dimension**: 1 (Pulse — control byte)
- **Location**: `nes/envelope_processor.py:145-176` (`get_envelope_control_byte`,
  `envelope_bits = 0x30`)
- **Status**: Existing: #167 — fix verified in place a third time (also
  confirmed in the 2026-07-19 pass as NH-HW-02); recommend closing #167
- **Description**: `envelope_bits = 0x30` sets both constant-volume (bit 4)
  and length-counter halt (bit 5) unconditionally in every pulse control byte,
  so the direct-export path's per-note `ora #$08` length-counter reload on
  `$4003`/`$4007` is inert — the halted length counter never depletes and cuts
  a sustained note. `@silence` in both `play_pulse1`/`play_pulse2` also writes
  `$30` (halt + zero volume), and the bytecode engine parity write is
  `ora #$30` (`audio_engine.asm:389,430`). No path was found that constructs a
  pulse control byte without going through `get_envelope_control_byte`.
- **Evidence**: `envelope_processor.py:174` `envelope_bits = 0x30`;
  `exporter/exporter_ca65.py:645/700` (`sta $4000`/`$4004` from the stored
  control byte, unmodified).
- **Impact**: None remaining — informational. #167 should be closed.
- **Hardware ref**: `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 "Halt Flags
  Always Set".
- **Related**: #167, #160 (NH-20 real durations), #161 (NH-18 phase guard).
- **Suggested Fix**: Close #167; no code change required.

### NH-HW-2026-08-05-4: Inert ADSR/effects envelope catalog re-verified still unreachable
- **Severity**: LOW
- **Dimension**: 7 (Envelope / ADSR)
- **Location**: `nes/envelope_processor.py:39-127`, consumed at
  `nes/emulator_core.py:102-112`
- **Status**: Existing: #166 (closed-as-documented; re-verified still inert,
  no regression)
- **Description**: `compile_channel_to_frames` still hardcodes
  `effects=None` at the `get_envelope_control_byte` call site and
  `envelope_type` still defaults to `event.get('envelope_type', 'default')`
  with no producer anywhere outside `tests/` setting that key
  (`grep -rn "envelope_type" nes/ tracker/ arranger/ exporter/` returns no
  non-test hits). Every real note still plays the flat `(0,0,15,0)` envelope;
  the `piano`/`pad`/`pluck`/`percussion` catalog and the vibrato/duty-sequence
  effects table remain unreachable production code, including the latent
  divide-by-zero in `get_envelope_value`'s percussion decay branch for a
  1-frame note (still unreachable while `envelope_type="percussion"` has no
  producer).
- **Evidence**: `emulator_core.py:110-112` passes `None` for `effects`.
- **Impact**: No timbre variety today; the divide-by-zero becomes a live crash
  risk only once a future envelope producer is wired up without guarding the
  1-frame case first.
- **Hardware ref**: `docs/APU_ENVELOPE_REFERENCE.md` §4 Constant Volume
  Output, §5 Engine Implementation Notes.
- **Related**: #166; NH-19 (#162, the first would-be real consumer, since
  fixed via the shared `noise_strike_decay_volume` helper instead).
- **Suggested Fix**: Keep as documented; when a producer is added, guard
  `(note_duration - 1 - attack_end) == 0` in `get_envelope_value` first.

---

## Dimensions verified clean (re-confirmed, no finding)

- **Dim 1 (Pulse duty/vol/timer/sweep)**: duty masked `(duty & 0x03) << 6`,
  `envelope_bits = 0x30` (const-vol + halt, see NH-HW-2026-08-05-3); volume
  `& 0x0F`; sweep disabled at all three init sites (standalone `reset`,
  project-builder `init_music`, `audio_engine.asm`) with `$08`, never
  re-enabled; bytecode `$4003`/`$4007` phase-reset guard (`last_written_hi`,
  forced `$FF` rewrite on genuine note onset via `@is_note`) re-verified to
  hold across `CMD_BANK_JUMP` and `CMD_INSTRUMENT` — neither touches
  `last_written_hi`, and instrument changes are always followed by a real note
  byte that re-arms the guard. `PULSE_DUTY_CYCLES` confirmed still gone
  (only referenced in issue/audit history text, no code hits).
- **Dim 2 (Triangle invariant)**: `process_all_tracks` routes triangle through
  the non-pulse branch (`default_duty=None`); emitted frame carries only
  `pitch`/`volume`/`note`, no `control`/duty key. `TRIANGLE_CONTROL_ON` (0xFF,
  fixed max reload, #364/NH-HW-04) confirmed in place in
  `exporter/exporter_ca65.py`, matching the bytecode engine's `$FF` write; the
  old loudness-scaled `0x80 | volume*7` is gone. No `$30`-style pulse byte
  leaks into `$4008` on any path (direct-export `@silence` writes `$00`,
  bytecode `@silence_tri` writes `$80`).
- **Dim 3 (Noise, legacy front-end)**: `get_noise_period` remains the single
  source of truth (clamp 24–60, scale 0–15, invert); `PitchProcessor.
  _get_noise_period` delegates to it; the 6-frame software decay ramp
  (`NOISE_DECAY_FRAMES`/`noise_strike_decay_volume`, both in
  `nes/envelope_processor.py`) produces audible non-degenerate steps and a
  re-trigger truncates the prior tail. The mode bit is live end-to-end on the
  legacy front-end (`enhanced_drum_mapper._noise_mode_for_note` →
  `emulator_core.py:164` → exporter `$400E` bit 7). Shared decay import
  re-confirmed in both `nes/emulator_core.py` and
  `arranger/voice_allocator.py:_apply_noise_strike_decay` per #359/
  ARR-2026-07-19-1 — no drifted second copy. See
  NH-HW-2026-08-05-1 for the arranger-side mode-bit gap.
- **Dim 4 (DPCM/DMC)**: `dpcm` branch emits `volume:15` as a trigger gate, not
  a level. `$4011` written only once, at bytecode init, to zero the DAC. The
  `@cmd_dmc_level` handler and the `CMD_DMC_LEVEL`/`$87` opcode are **fully
  removed** from both `nes/audio_engine.asm` and `exporter/exporter_ca65.py`
  (stronger than "dead code with a stale handler" — there is no handler left
  at all), consistent with `tests/test_ca65_export.py::
  test_dmc_level_command_path_removed`. Sample residency: `dpcm_packer.py`
  aligns every sample to 64 bytes from `START_ADDR = 0xC000`, matching
  `docs/APU_DMC_REFERENCE.md` §4's `$C000-$FFFF`/64-byte-aligned constraint
  (mapper-audit cross-ref for bank packing itself). Direct-export `$4011` gap
  = NH-HW-2026-08-05-2 (#348).
- **Dim 5 (Per-channel pitch tables + 11-bit clamp)**: one parameterized
  `generate_note_table(divider)` builds pulse `/16` and triangle `/32` tables;
  `get_channel_pitch` and `midi_note_to_timer_value` both branch on
  `channel == 'triangle'`; every table entry floored at 8 / clamped to 0x7FF
  (spot-checked programmatically: `NES_NOTE_TABLE[119] == 13`,
  `NES_TRIANGLE_TABLE[96] == 25`, both ≥ 8). `midi_note_to_timer_value` clamps
  note 24–119; the frame-side `get_channel_pitch` clamps per-channel
  (pulse 24-108, triangle 24-96) while the exporter's macro-offset base clamps
  to 95 — the resulting worst-case pitch/base-timer delta was recomputed this
  pass (`NES_NOTE_TABLE[108]-NES_NOTE_TABLE[95] == -30`,
  `NES_TRIANGLE_TABLE[96]-NES_TRIANGLE_TABLE[95] == -2`), both comfortably
  inside the encoder's ±127 range and the reconstructed runtime period stays
  well inside `8..0x7FF`. `apply_pitch_bend` re-clamps but remains dead code
  (no call site outside tests) — informational only, not filed as a finding
  since it mirrors already-documented inert-scaffolding elsewhere.
- **Dim 6 (Velocity→volume)**: single `velocity_to_volume`
  (`max(1, int(15 * pow(v/127, 1.5)))`), clamped 0–15; envelope combine step
  `min(15, round((envelope_volume * midi_volume) / 15.0))` cannot reach 16
  (both factors ≤ 15, product/15 ≤ 15.0 exactly at the ceiling).
- **Dim 7 (Envelope)**: constant-volume flag always set (`0x30`, shared with
  Dim 1); catalog inert = NH-HW-2026-08-05-4 (#166).
- **Dim 8 (60Hz/frame counter)**: all three init sites (`reset`, `init_music`,
  `audio_engine.asm`) write `$4017 = $40` (4-step mode 0, IRQ inhibit);
  comments consistently read "mode 0" (NH-22 stays fixed, no doc-rot
  reintroduced); frame model iterates integer frames throughout.
- **Dim 9 (Register addresses / $4015)**: all `APU_*` constants land in
  `$4000-$4017`; every emitted `sta $40xx` checked and lands on the right
  channel's register; init enables `$4015 = $0F` (Pulse1/Pulse2/Triangle/
  Noise), DMC bit 4 set to `$1F` only on sample trigger
  (`play_dpcm`/`@write_dpcm`/`@cmd_dpcm_play`, all three sites consistent).
- **Dim 10 (Value-range clamping)**: timers floored-8/clamped-`$7FF`,
  volume/duty masked (`& 0x0F` for volume at every write site, duty
  structurally 0-3 by construction from `(control >> 6) & 0x03` at the
  exporter, so the runtime `lsr/ror/ror` duty-to-bits shift trick — verified
  by hand for all 4 duty values — never sees stray upper bits), noise index
  `& 0x0F` at both the direct-export table build and the bytecode
  `@write_noise` handler, dmc "level" remains a trigger gate. The two
  unclamped ASM add sites (pitch, arp): pitch add re-verified in-range this
  pass (see Dim 5); arp add (`clc; lda current_note,x; adc temp_arp`) still
  fed only the neutral `_encode_macro_offset(0)` on every channel including
  noise (no `arp` producer anywhere in the pipeline, #166) — still HIGH the
  moment a live nonzero producer appears without a guard.

---

## Notes on scope boundaries

- The mapper auto-select/capacity changes in #361-#363 (`36348ce`) touch
  `mappers/`, `compiler/compiler.py`, and `main.py` sizing logic, not APU
  register semantics — left to the mapper audit.
- NH-HW-2026-08-05-1 sits on the boundary between this audit's Dimension 3 and
  `/audit-arranger`'s territory (GM drum-role mapping). It is filed here
  because the skill's own Dimension 3 explicitly asks whether the noise mode
  bit is "reachable end-to-end" or "dead-but-correct plumbing" for *every*
  producer, and the arranger's total absence of a mode-bit code path is a
  direct answer to that question for the `--arranger` front-end. Consider
  cross-filing under the `arranger` label as well as `nes-hardware`.

## Suggested next step

```
/audit-publish docs/audits/AUDIT_NES-HARDWARE_2026-08-05.md
```
