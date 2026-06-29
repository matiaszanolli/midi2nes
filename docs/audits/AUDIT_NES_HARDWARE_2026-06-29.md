# NES Hardware Correctness Audit — 2026-06-29

Audit of the boundary where Python numeric values become APU register writes, across all
10 hardware dimensions. Hot files: `nes/emulator_core.py`, `nes/pitch_table.py`,
`nes/envelope_processor.py`, `nes/audio_constants.py`, `exporter/exporter_ca65.py`, plus
the generated `nes/audio_engine.asm`.

**Pipeline note.** `main.py` frame generation goes through
`nes/emulator_core.py:NESEmulatorCore.process_all_tracks` (the **live** core; `main.py:18,58`).
A second, near-duplicate `NESEmulatorCore` in `nes/envelope_processor.py` is **dead** (not
imported by `main.py`). Export enters via `CA65Exporter.export_tables_with_patterns`
(`main.py:244,522`); with empty `patterns` it falls back to `export_direct_frames`
(the `--no-patterns` path and the empty-pattern case). With patterns it emits the
macro-bytecode consumed by `nes/audio_engine.asm`.

**Regression context.** The prior report (`AUDIT_NES_HARDWARE_2026-06-28.md`) raised NH-01…
NH-12. Commits on this branch (`7b57028`, `5e155ee` "route noise and DPCM channels to their
APU registers (#9)", and the pitch-table / DMC-clamp work) have since **fixed** NH-01
(noise/DPCM now carry `note`/period/`dmc_level` and both exporter paths emit
`$400C/$400E/$400F` and the DPCM trigger), NH-02 + NH-03 (distinct `/16` pulse and `/32`
triangle tables, single source of truth), NH-04 (the two noise-period impls now agree and
invert), NH-05 (a `dmc_level` producer + 7-bit clamp now exist), NH-06 (timers floor at
`max(8, …)`), NH-07 (sweeps disabled at init), and NH-09/NH-12's concrete code basis
(`export_direct_frames` now derives its iNES header from the selected mapper, and `CLAUDE.md`
ROM Structure now says MMC3). Those are **not** re-reported as findings; the still-open
issues that survived are listed below, and three NEW findings were uncovered.

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 1 |
| LOW      | 4 |
| **Total**| **6** |

### Highest-risk hardware divergences

1. **DPCM note-off triggers an out-of-range DMC sample on the direct-export path**
   (NH-13, HIGH, NEW). In `export_direct_frames`'s `play_dpcm`, the `beq @done` that is
   meant to skip triggering on a silent (`note == 0`) frame is **unreachable**, because the
   preceding `sta last_dpcm_note` does not affect the Z flag. On every drum note-off the
   engine computes `sample_id = note - 1 = $FF`, indexes the single-byte `dpcm_*_table`
   stubs at offset 255, and triggers DMC with out-of-bounds garbage parameters.
2. **All four direct-export silence branches are dead** (NH-14, MEDIUM, NEW). The same
   `sta`-then-`beq` flag bug makes the `@silence` block in `play_pulse1`, `play_pulse2`,
   `play_triangle`, and `play_noise` unreachable. The channels only go quiet because the
   zero-valued silent-frame data coincidentally mutes them, and the note-off retriggers the
   length counter / resets phase (an audible click) instead of the intended clean silence.

---

## Findings

### NH-13: `play_dpcm` note-off triggers a DMC sample at an out-of-range table index
- **Severity**: HIGH
- **Dimension**: 4 (DPCM/DMC) + 9 ($4015 enable / register correctness)
- **Location**: `exporter/exporter_ca65.py:675-682` (`play_dpcm` in `export_direct_frames`)
- **Status**: NEW
- **Description**: The direct-export DPCM playback proc reads the per-frame `dpcm_note`
  byte (`note = sample_id + 1`, `0` = rest), compares it to `last_dpcm_note`, and is
  intended to skip triggering when the note is `0` (a note-off / rest frame):
  ```asm
  lda (temp_ptr),y          ; A = dpcm_note[frame]
  cmp last_dpcm_note
  beq @done                 ; unchanged - sample already triggered
  sta last_dpcm_note
  beq @done                 ; note 0 -> nothing to trigger   <-- DEAD
  sec
  sbc #1                    ; sample_id = note - 1
  tay
  ... lda dpcm_bank_table,y / dpcm_pitch_table,y / ... ; trigger DMC
  ```
  On a 6502, `STA` does **not** modify the Z flag. We only reach the `sta` when the
  preceding `cmp last_dpcm_note` was *not* equal (otherwise the first `beq @done` is taken),
  so Z is **clear**. The second `beq @done` therefore tests the stale `cmp` result and is
  **never** taken. When a drum hit (e.g. `note = 6`) is followed by a rest frame
  (`note = 0`, the value emitted for every empty DPCM frame at lines 243-246), the proc
  falls through with `A = 0`, computes `sbc #1 → $FF`, `tay`, and indexes
  `dpcm_bank_table,y` / `dpcm_pitch_table,y` / `dpcm_addr_table,y` / `dpcm_len_table,y` at
  **offset 255**, then writes those bytes to `$4010/$4012/$4013` and triggers DMC via
  `$4015 = $1F`.
- **Evidence**: `exporter/exporter_ca65.py:676-682`. The stub tables are a **single byte**
  each (`nes/project_builder.py:453-456`: `dpcm_bank_table: .byte $00` …), so offset 255 is
  255 bytes of adjacent RODATA. The silent-frame value is always `$00`
  (`exporter/exporter_ca65.py:243-246`). The same flag bug is absent in the bytecode engine
  (`nes/audio_engine.asm:483-511` recovers `sample_id` only on a genuine note value).
- **Impact**: In `--no-patterns` (direct-export) mode, every drum/sample track plays a
  garbage DMC sample (wrong bank, address, length, rate) on the frame after each hit —
  audible garbage noise and, with the wrong `$4013` length, runaway DMA. Blast radius: any
  GM-drum / sampled MIDI compiled with `--no-patterns`. (The default pattern path uses the
  bytecode engine and is unaffected.)
- **Related**: NH-14 (same root-cause flag bug in the four tone-channel silence branches);
  prior NH-01/NH-05 (DPCM dispatch, now otherwise fixed).
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2 (`$4012 = $C000 + A*64`, `$4013` length
  `L*16+1`), §3 (trigger via `$4015` bit 4), §4 (sample must reside in `$C000–$FFFF`; a
  bad length/address bleeds into `$8000`). `docs/NES_APU_REFERENCE.md` §3.1 (`$4015`).
- **Suggested Fix**: Test the loaded note explicitly before `sbc`, e.g. re-load /
  `cmp #0` (or move the note value through a register whose load sets Z) so `beq @done`
  branches on `note == 0`, not on the stale `cmp last_dpcm_note` result. Bounds-guard the
  `sbc #1` against `note == 0` regardless.

### NH-14: All four direct-export tone-channel `@silence` branches are unreachable (dead `beq`)
- **Severity**: MEDIUM
- **Dimension**: 1 (Pulse) + 2 (Triangle) + 3 (Noise) + 9 (register correctness)
- **Location**: `exporter/exporter_ca65.py:419-423` (pulse1), `490-494` (pulse2),
  `559-563` (triangle), `625-628` (noise)
- **Status**: NEW
- **Description**: Each tone-channel proc uses the same idiom:
  ```asm
  cmp last_pulse1_note
  beq @sustain              ; same note -> hold (Z used correctly here)
  sta last_pulse1_note
  beq @silence              ; "if note is 0, silence"  <-- DEAD
  ```
  As in NH-13, the `sta` does not set Z and we only reach it when the `cmp` was *not* equal
  (Z clear), so `beq @silence` is **never** taken. On a note→silence transition the proc
  falls through and writes the silent frame's zero-valued `control`/`timer` tables
  (`control = $00`, `timer_lo/hi = $00`, with `ora #$08` on the high byte) to the channel
  registers, and the explicit `@silence` block (`lda #$30 ; constant volume 0` for pulse/
  noise, `lda #$00 / sta $4008` for triangle) never executes.
- **Evidence**: lines 419-423, 490-494, 559-563, 625-628. The `@silence` labels at
  461-465, 532-535, 601-604, 653-655 are dead. For pulse the fallthrough writes `$4000=$00`
  (volume 0, *no* constant-volume flag) + `$4003=$08` (length reload, phase reset); for
  triangle `$4008=$00` (linear-counter halt); for noise `$400C=$00` + `$400F=$08` (length
  reload). The intended clean `$30` (constant-volume-0) write is skipped.
- **Impact**: Channels still end up effectively silent because the zero data happens to mute
  them (pulse timer `$00` is `t<8`; triangle linear-counter `$00` halts; noise volume 0),
  so this is not a stuck-note bug — but every note-off **reloads the length counter and
  resets the pulse phase** (the `ora #$08` writes), reintroducing exactly the popping the
  `@sustain` short-circuit was added to avoid (`docs/APU_PULSE_REFERENCE.md` §2 "writing
  `$4003`/`$4007` immediately restarts the sequencer … audible click"). Direct-export ROMs
  only. Workaround: use the default pattern path. MEDIUM (audible artifact, with workaround;
  intended silence logic is dead).
- **Related**: NH-13 (identical 6502 flag bug, higher impact on DPCM).
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §2 (`$4003` restarts sequencer → click),
  §5 cond. 4 (`t < 8` silences); `docs/APU_TRIANGLE_REFERENCE.md` §5 (linear-counter halt
  silence); `docs/APU_NOISE_REFERENCE.md` §2 (`$400C --lc.vvvv` constant-volume silence).
- **Suggested Fix**: Test the loaded note for zero with an instruction that sets Z
  (re-`lda`/`cmp #0`, or `tax`/`tay` on the note before `sta`) so `beq @silence` branches on
  `note == 0`. Then the existing `@silence` blocks run and the phase-reset is avoided.

### NH-08: Dead/contradictory pulse volume expression in `compile_channel_to_frames`
- **Severity**: LOW
- **Dimension**: 6 (velocity → 4-bit volume)
- **Location**: `nes/emulator_core.py:59`
- **Status**: Existing: #34
- **Description**: The pulse-branch `volume` is
  `min(15, velocity // 8) if velocity == 0 else max(1, int(15*pow(velocity/127,1.5)))`.
  The `velocity == 0` arm is unreachable — the loop `continue`s on velocity 0 at
  `nes/emulator_core.py:29-30`, so `velocity > 0` always holds here. The dead arm is also a
  linear `velocity // 8` that contradicts the 1.5-power curve used everywhere else. Harmless
  (live pulse playback uses the `control` byte from `get_envelope_control_byte`, not this
  `volume` field), but misleading.
- **Evidence**: `if velocity == 0: continue` (line 29) then `… if velocity == 0 else …`
  (line 59). Still present at HEAD (`7b57028`).
- **Impact**: None functionally; maintenance noise.
- **Related**: #34 (tracking issue), NH-13/NH-14 (other dead branches).
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §1 (4-bit volume); curve rationale
  `docs/APU_ENVELOPE_REFERENCE.md` §6 (engine-driven constant volume).
- **Suggested Fix**: Drop the unreachable branch; keep the single power-curve expression.

### NH-10: Additive vibrato pitch in the dead duplicate core re-opens the 11-bit clamp
- **Severity**: LOW
- **Dimension**: 5 + 10 (clamp re-opened by additive step)
- **Location**: `nes/envelope_processor.py:203-206,218,231` (dead duplicate `NESEmulatorCore`)
- **Status**: Existing: #38
- **Description**: The duplicate `NESEmulatorCore.compile_channel_to_frames` in
  `envelope_processor.py` adds vibrato (`modified_pitch += pitch_mod`, line 206) **after**
  the pitch was produced, with **no re-clamp** to `[8, 0x7FF]`, then stores `modified_pitch`
  into the frame (lines 218, 231). The exporter masks rather than clamps, so an out-of-range
  value would wrap. This would be HIGH on a live path, but this core is **dead** — `main.py`
  imports `nes/emulator_core.py`, whose live `compile_channel_to_frames` applies no
  `pitch_mod` (verified at `nes/emulator_core.py:48-73`). Latent trap + duplication.
- **Evidence**: `main.py:18` imports `nes.emulator_core`; the vibrato/effects path exists
  only in the `envelope_processor.py` copy. Still present at HEAD.
- **Impact**: None today (dead); becomes HIGH if this copy is ever wired in.
- **Related**: #38 (tracking issue); duplication of `NESEmulatorCore`.
- **Hardware ref**: `docs/APU_PITCH_TABLE_REFERENCE.md` §1 (11-bit range);
  `docs/APU_PULSE_REFERENCE.md` §5 cond. 4 (`t < 8` silence).
- **Suggested Fix**: Delete the duplicate `NESEmulatorCore`; if vibrato is wanted, add it to
  the live core with a re-clamp to `[8, 0x7FF]`.

### NH-11: `note_to_timer` range guard contradicts the channel ranges it serves
- **Severity**: LOW
- **Dimension**: 5 / 10 (range-validation consistency)
- **Location**: `nes/pitch_table.py:133-139`
- **Status**: Existing: #41
- **Description**: `note_to_timer` raises for `midi_note >= 96` ("out of NES range
  (24-95)"), but `CHANNEL_RANGES`/`channel_ranges` allow pulse up to MIDI 108 and the note
  tables are generated for the full 0–127. The guard is inconsistent with the rest of the
  module (which clamps rather than raises) and would reject legal pulse notes 96–108. It is
  unused on the live path (`get_channel_pitch` is the live entry) but a foot-gun.
- **Evidence**: `if midi_note < 24 or midi_note >= 96: raise ValueError(… "(24-95)")`
  (line 137-138) vs `channel_ranges["pulse1"] = (24, 108)` (line 82). Still present at HEAD.
- **Impact**: None today (unused); a trap if adopted.
- **Related**: #41 (tracking issue).
- **Hardware ref**: `docs/APU_PITCH_TABLE_REFERENCE.md` §3 (full 0–127 MIDI indexing).
- **Suggested Fix**: Align the guard with the clamp policy (clamp, don't raise), or remove
  the dead method.

### NH-15: `PULSE_DUTY_CYCLES` is dead and its 8-bit values contradict the 2-bit duty field
- **Severity**: LOW
- **Dimension**: 1 (Pulse duty) — doc-rot / dead constant
- **Location**: `nes/audio_constants.py:9-14`
- **Status**: NEW
- **Description**: `PULSE_DUTY_CYCLES` maps duty IDs `1..4` to 8-bit waveform bit patterns
  (`0b00000001`, `0b00000011`, `0b00001111`, `0b01111100`). A repo-wide search shows the
  constant is **referenced nowhere** outside its own definition — it is dead. It is also
  hardware-wrong as a "duty cycle" value: the NES pulse duty is a **2-bit** field (`DD`,
  values 0–3) in bits 6–7 of `$4000`/`$4004` (`docs/APU_PULSE_REFERENCE.md` §4), and the
  live control byte correctly uses `(duty_cycle & 0x03) << 6`
  (`nes/envelope_processor.py:121`). The 8-bit patterns here resemble the *sequencer output
  waveforms* per duty, not anything the engine writes, so the constant invites a future
  contributor to write an 8-bit "duty" into a 2-bit field.
- **Evidence**: `grep -rn PULSE_DUTY_CYCLES` → only `nes/audio_constants.py:9`. Doc duty
  table is 2-bit (`%00`/`%01`/`%10`/`%11`) at `docs/APU_PULSE_REFERENCE.md` §4. The
  `NES_ENVELOPES` block in the same file is likewise unused.
- **Impact**: None today (dead); a correctness trap and stale-constant noise.
- **Related**: NH-08 (other dead audio code).
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §4 (Duty Cycles — 2-bit `DD`, values 0–3).
- **Suggested Fix**: Delete `PULSE_DUTY_CYCLES` (and the unused `NES_ENVELOPES`/commented
  blocks), or, if a duty table is wanted, store the canonical 2-bit values `{0,1,2,3}` with
  a doc cross-reference.

---

## Verified clean / fixed since 2026-06-28

- **Noise & DPCM now reach their registers (was NH-01, CRITICAL).** `process_all_tracks`
  carries `note`=period index, mode in `control` bit 6, scaled `volume` for noise
  (`nes/emulator_core.py:88-111`) and `note`=`sample_id+1` (+ optional clamped `dmc_level`)
  for DPCM (112-130). Both exporter paths emit them: direct mode writes
  `$400C/$400E/$400F` and the DPCM trigger (`exporter/exporter_ca65.py:211-249,612-706`),
  bytecode mode via `nes/audio_engine.asm`. Matches `docs/APU_NOISE_REFERENCE.md` §2,
  `docs/APU_DMC_REFERENCE.md` §3.
- **Triangle pitch (was NH-02/NH-03, HIGH).** Distinct `/16` pulse and `/32` triangle
  tables (`nes/pitch_table.py:25-52`), selected by channel in `get_channel_pitch`
  (105-108) and `midi_note_to_timer_value` (`exporter/exporter_ca65.py:55-57`); the
  exporter emits separate `ntsc_period_*` and `triangle_period_*` tables from the same
  source (893-897). Matches `docs/APU_PITCH_TABLE_REFERENCE.md` §1.
- **Noise period direction (was NH-04, HIGH).** `get_noise_period` now inverts
  (`return 15 - …`, `nes/pitch_table.py:75`) and `_get_noise_period` delegates to it (116),
  so higher note → lower index → higher pitch (`docs/APU_NOISE_REFERENCE.md` §3).
- **Timer `t >= 8` floor (was NH-06, HIGH).** `generate_note_table` clamps `max(8, …)`
  (`nes/pitch_table.py:45`), `apply_pitch_bend` floors at 8 (131), and the exporter
  re-asserts `max(8, min(pitch, 0x7FF))` before the byte split
  (`exporter/exporter_ca65.py:176-177`). Matches `docs/APU_PULSE_REFERENCE.md` §3/§7.
- **Sweep init (was NH-07, HIGH).** Both init paths write `$08` to `$4001`/`$4005`
  (`exporter/exporter_ca65.py:286-290,728-730`; `nes/audio_engine.asm:135-140`). Matches
  `docs/APU_PULSE_REFERENCE.md` §1/§5.
- **DMC 7-bit level clamp + producer (was NH-05, HIGH).** `process_all_tracks` produces a
  `dmc_level` clamped `max(0, min(127, …))` (`nes/emulator_core.py:127-128`); the exporter
  masks `& 0x7F` (`exporter/exporter_ca65.py:947`) and the engine `and #$7F`
  (`nes/audio_engine.asm:255`). (Note: no upstream MIDI stage currently *populates*
  `e['dmc_level']`, so `CMD_DMC_LEVEL` remains latent — but it is now range-safe.) Matches
  `docs/APU_DMC_REFERENCE.md` §2/§3.
- **iNES header / mapper (was NH-09/NH-12).** `export_direct_frames` now derives the header
  from the selected mapper (`exporter/exporter_ca65.py:75-83`), and `CLAUDE.md` ROM
  Structure says MMC3 (`CLAUDE.md:195-197`). Issue #43 (NH-12 doc-rot) is open but its
  concrete code basis appears resolved — recommend closing after confirmation.
- **`$4017` / `$4015` init.** `$4017 = $40` (4-step, IRQ inhibit) and `$4015 = $0F`
  before playback (`exporter/exporter_ca65.py:282-284,724-727`;
  `nes/audio_engine.asm:128-133`), plus `$4011 = 0` at bytecode init (122-123). Matches
  `docs/APU_FRAME_COUNTER_REFERENCE.md` §4 and `docs/APU_DMC_REFERENCE.md` §6.
- **Pulse control byte.** `(duty & 0x03) << 6 | 0x10 | (volume & 0x0F)`
  (`nes/envelope_processor.py:121-126`) — duty bits 6-7, constant-volume bit 4, 4-bit
  volume bits 0-3. Matches `docs/APU_PULSE_REFERENCE.md` §2 + `docs/APU_ENVELOPE_REFERENCE.md`.
- **Triangle invariant.** Triangle frames carry only `pitch`/`volume`, no duty/control byte
  (`nes/emulator_core.py:61-73,81-87`); the exporter derives a linear-counter value
  `0x80 | (volume*7)` for `$4008`, `$00` for silence (`exporter/exporter_ca65.py:160-168`).
  No pulse volume/duty leaks into `$4008`/`$400B`. Matches `docs/APU_TRIANGLE_REFERENCE.md`.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-06-29.md
```
