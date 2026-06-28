# NES Hardware Correctness Audit — 2026-06-28

Audit of the boundary where Python numeric values become APU register writes, across
all 10 hardware dimensions. Hot files: `nes/emulator_core.py`, `nes/pitch_table.py`,
`nes/envelope_processor.py`, `nes/audio_constants.py`, `exporter/exporter_ca65.py`.

Pipeline note: `main.py` frame generation goes through
`nes/emulator_core.py:NESEmulatorCore.process_all_tracks` (the **live** core). A second,
near-duplicate `NESEmulatorCore` lives in `nes/envelope_processor.py` and is **dead**
(not imported by `main.py`); findings are tagged accordingly. Export always enters via
`CA65Exporter.export_tables_with_patterns`; with no patterns it falls back to
`export_direct_frames` (`--no-patterns` and the empty-pattern case).

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 1 |
| HIGH     | 5 |
| MEDIUM   | 3 |
| LOW      | 3 |
| **Total**| **12** |

### Highest-risk hardware divergences (wrong on *every* ROM)

1. **Noise & DPCM channels are silent / dropped on every ROM** (NH-01, CRITICAL).
   `process_all_tracks` emits noise/DPCM frames with no `note`/`period`/`dmc_level`
   keys, and *neither* exporter path turns them into `$400C/$400E` (noise) or
   `$4011/$4015` (DMC) writes. All percussion and samples are silent. This is the
   concrete root cause behind open issue **#3 "Output seems silent"** for any drum track.
2. **Every Triangle note plays one octave too low** (NH-02, HIGH). `nes/pitch_table.py`
   uses the *pulse* timer formula (`fCPU/16`) for the triangle channel, but triangle
   hardware divides by 32 — the same timer sounds an octave lower (`docs/APU_PITCH_TABLE_REFERENCE.md` §1).
3. **Two internal pitch tables disagree by a factor of ~2** (NH-03, HIGH).
   `nes/pitch_table.py` (A4→253) and `exporter/exporter_ca65.py:NOTE_TABLE_NTSC`
   (A4→127) are an octave apart, and the bytecode path subtracts one from the other to
   form a pitch offset, corrupting pitch on every bytecode-mode note.

---

## Findings

### NH-01: Noise and DPCM channels never reach their APU registers (all percussion/samples silent)
- **Severity**: CRITICAL
- **Dimension**: 3 (Noise period/mode) + 4 (DPCM/DMC level) + 9 ($4015 enable)
- **Location**: `nes/emulator_core.py:88-103`, `exporter/exporter_ca65.py:117-188` (direct) and `746-959` (bytecode)
- **Status**: NEW (root cause for open issue #3 "Output seems silent")
- **Description**: `process_all_tracks` builds noise frames as
  `{"noise_mode": 0, "volume": 15|0}` and DPCM frames as
  `{"sample_id": …, "volume": 15|0}` — **no `note`, no `period`, no `dmc_level`**.
  - `export_direct_frames` only iterates `['pulse1','pulse2','triangle']`
    (`exporter/exporter_ca65.py:117`) and emits **no** noise (`$400C/$400E/$400F`) or
    DMC (`$4010-$4013`) register writes at all. Noise/DPCM are dropped on the floor.
  - `export_tables_with_patterns` does loop noise/dpcm
    (`exporter/exporter_ca65.py:748`), but reads `note = frame_data.get('note', 0)`
    (line 769); since noise/dpcm frames carry no `note`, every entry collapses to
    note 0 → silence, and the period index / `noise_mode` are never written.
- **Evidence**:
  ```python
  # nes/emulator_core.py:88-103 — no 'note'/'period'/'dmc_level' produced
  "noise_mode": 0, "volume": 15 if ... else 0
  "sample_id": e.get('sample_id', 0), "volume": 15 if ... else 0
  # exporter_ca65.py:117 — direct path ignores noise/dpcm entirely
  for channel_name in ['pulse1', 'pulse2', 'triangle']:
  ```
- **Impact**: Every ROM with drums or samples plays no percussion and no DPCM. Blast
  radius: all four-on-the-floor / GM-drum MIDIs (the common case). Matches the symptom
  in issue #3.
- **Related**: NH-04 (noise period table never consulted), NH-05 (DMC level dead),
  issue #3.
- **Hardware ref**: `docs/APU_NOISE_REFERENCE.md` §2 (`$400E` `M---.PPPP` period index +
  mode), §6 (drum mapping must set Period/Mode); `docs/APU_DMC_REFERENCE.md` §3 (trigger
  via `$4015` bit 4 + `$4011` level); `docs/NES_APU_REFERENCE.md` §3.1 (`$4015` enables).
- **Suggested Fix**: Have `process_all_tracks` carry a `period` (0–15) and `noise_mode`
  bit into noise frames and a `dmc_level`/trigger into dpcm frames, and add noise/DPCM
  emission to both exporter paths (write `$400C/$400E/$400F`; `$4011/$4012/$4013` + a
  `$10` to `$4015`).

### NH-02: Triangle channel uses the pulse timer formula → every triangle note an octave low
- **Severity**: HIGH
- **Dimension**: 2 (Triangle invariant) + 5 (per-channel pitch table)
- **Location**: `nes/pitch_table.py:16-33, 77-104`; consumed at `nes/emulator_core.py:44,81-87` and `exporter/exporter_ca65.py:164-166`
- **Status**: NEW
- **Description**: `PitchProcessor.get_channel_pitch(note, 'triangle')` returns
  `self.note_table[note]`, and `note_table` is built with the **pulse** formula
  `timer = fCPU/(16*freq) - 1` (`nes/pitch_table.py:87`). Triangle hardware uses
  `f = fCPU/(32*(t+1))` — for the *same* timer value the triangle sounds **one octave
  lower** than a pulse. There is no separate triangle table and no octave compensation,
  so the triangle is pitched an octave below the intended note.
- **Evidence**: For A4 (MIDI 69): `generate_note_table()[69] = 253`. Triangle hardware
  with t=253 → `1789773/(32*254) ≈ 220 Hz = A3`, not 440 Hz. The correct triangle timer
  for A4 is `int(fCPU/(32*440)-1) = 126`.
- **Impact**: Every triangle note (typically the bassline) is an octave flat on every
  ROM produced via `export_direct_frames`. Wrong pitch on every triangle note = HIGH.
- **Related**: NH-03 (the `/16` vs `/32` confusion also explains the table mismatch).
- **Hardware ref**: `docs/APU_PITCH_TABLE_REFERENCE.md` §1 ("for a given period the Pulse
  waves sound **one octave higher** than the Triangle"); `docs/APU_TRIANGLE_REFERENCE.md`
  §3 (`f = fCPU / (32 * (tval + 1))`).
- **Suggested Fix**: Generate a distinct triangle table using the `/32` formula (or halve
  the period index appropriately) and select it by channel in `get_channel_pitch`.

### NH-03: Two divergent NTSC pitch tables (`pitch_table.py` vs exporter) an octave apart
- **Severity**: HIGH
- **Dimension**: 5 (per-channel pitch table correctness)
- **Location**: `nes/pitch_table.py:28` vs `exporter/exporter_ca65.py:34-44,54-57`
- **Status**: NEW
- **Description**: `process_all_tracks` writes `pitch` from `pitch_table.py`
  (`fCPU/16` formula → A4 = 253). The bytecode exporter independently recomputes a base
  timer from its own `NOTE_TABLE_NTSC` (`midi_note_to_timer_value`, A4 = 127) and then
  forms a *pitch offset* `pitch_val - base_timer` (`exporter/exporter_ca65.py:819,834`).
  Because the two tables differ by ~2x, this offset is ≈ the base period itself
  (253 − 127 = 126), gets clamped to ±127, and is then added to the doc's embedded
  `ntsc_period` table at runtime — corrupting the played pitch. The two tables cannot
  both be right; `NOTE_TABLE_NTSC` matches the triangle (`/32`) scale while
  `pitch_table.py` matches the pulse (`/16`) scale.
- **Evidence**:
  ```
  pitch_table.py: A4=253  C4=426  C2=1709
  exporter NOTE_TABLE_NTSC: A4=127  C4=214  C2=856   # ~half — octave down
  ```
- **Impact**: In bytecode (pattern) mode the pitch offset is garbage on every note; the
  two-table split is a latent octave bug independent of NH-02. Affects every ROM built
  with patterns enabled (the default).
- **Related**: NH-02.
- **Hardware ref**: `docs/APU_PITCH_TABLE_REFERENCE.md` §2–§3 (single authoritative
  MIDI-indexed table + generation math); §1 (pulse vs triangle octave).
- **Suggested Fix**: Single source of truth — derive both the Python `pitch` and the
  exporter base table from the same per-channel formula, or have the exporter consume the
  pitch already in the frame rather than recomputing a base and differencing.

### NH-04: Noise period table broken and never consulted; module/instance impls disagree
- **Severity**: HIGH
- **Dimension**: 3 (Noise period table & mode)
- **Location**: `nes/pitch_table.py:46-61` and `106-114`
- **Status**: NEW
- **Description**: Two contradictory noise-period implementations exist and **neither is
  on the pipeline path** (NH-01):
  - Module `get_noise_period` (line 52) indexes `NOISE_PERIOD_TABLE = [0x0..0xF]` — an
    identity list of indices, **not** the hardware period table — and does **not**
    invert, so higher MIDI note → higher index → longer period → *lower* frequency
    (backwards).
  - `PitchProcessor._get_noise_period` (line 106) returns `15 - scaled` (inverts
    correctly: higher note → higher pitch) but maps to a bare 0–15 index.
  The real NTSC period table (`docs/APU_NOISE_REFERENCE.md` §3) lives only as
  `NOISE_PERIODS` in the exporter (`exporter/exporter_ca65.py:47`) and is unused. The
  4-bit index written to `$400E` is what hardware wants — but `NOISE_PERIOD_TABLE`
  being an identity list means the "table" adds nothing and the non-inverted
  `get_noise_period` direction is wrong.
- **Evidence**: `NOISE_PERIOD_TABLE = [0x0,…,0xF]` (line 47); `get_noise_period` returns
  `NOISE_PERIOD_TABLE[index]` with no inversion vs `_get_noise_period` returning
  `15 - …`.
- **Impact**: Once NH-01 is fixed, whichever helper is wired in determines drum pitch;
  the non-inverted one makes higher drum notes lower-pitched. Today: dead, but a
  correctness trap.
- **Related**: NH-01.
- **Hardware ref**: `docs/APU_NOISE_REFERENCE.md` §2 (`$400E` `M---.PPPP`, 4-bit index),
  §3 (period table — lower index = shorter period = higher frequency).
- **Suggested Fix**: Delete the identity `NOISE_PERIOD_TABLE`/`get_noise_period`; keep a
  single inverting MIDI→index mapper that feeds the `$400E` low nibble, and pick the
  mode bit (bit 7) per drum (`gm_instruments` already defines `noise_period` per drum).

### NH-05: DMC level command has a consumer but no producer; level not 7-bit clamped
- **Severity**: HIGH
- **Dimension**: 4 (DPCM/DMC level)
- **Location**: `exporter/exporter_ca65.py:774,783-785,826,938-939`; producer absent in `nes/emulator_core.py:96-103`
- **Status**: NEW
- **Description**: The bytecode exporter reads `frame_data.get('dmc_level')` and emits
  `CMD_DMC_LEVEL ($87, level)`. A repo-wide search shows `dmc_level` is **only ever
  read** — no stage writes it (`process_all_tracks` dpcm frames carry only `sample_id`
  and `volume`). The recent "DMC level handling" commit is therefore dead on the live
  path. Separately, the emitted byte `${event["dmc_level"]:02X}` is **not clamped to the
  7-bit `$4011` range (0–127)**; a value ≥128 sets bit 7 (out of spec) and ≥256 breaks
  the `:02X` formatting.
- **Evidence**:
  ```python
  dmc_level = frame_data.get('dmc_level')   # never set upstream
  lines.append(f'    .byte $87, ${event["dmc_level"]:02X} ; CMD_DMC_LEVEL')  # no &0x7F
  ```
- **Impact**: DMC direct-level control is non-functional (dead) and, if ever fed, can
  emit an out-of-range `$4011` value. Compounds NH-01 (DPCM silent).
- **Related**: NH-01.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2 (`$4011` `-DDD.DDDD`, 7-bit), §3
  (direct load 0–127, no wrap).
- **Suggested Fix**: Produce `dmc_level` in the dpcm frame path (or remove the dead
  consumer), and clamp emitted level to `level & 0x7F`.

### NH-06: Pulse/Triangle timer not clamped to `t >= 8`; low notes silently mute
- **Severity**: HIGH
- **Dimension**: 1 (Pulse timer) + 5 (11-bit clamp) + 10 (range sweep)
- **Location**: `nes/pitch_table.py:30,88` (clamp is `max(0, min(timer,0x7FF))`); exporter `exporter_ca65.py:165-166`
- **Description**: All timer clamps in `pitch_table.py` clamp only the **upper** 11-bit
  bound (`min(timer, 0x07FF)`) and the lower bound to `0`. The pulse channel is
  **silenced whenever the timer `t < 8`** (`docs/APU_PULSE_REFERENCE.md` §3, §5). High
  MIDI notes (e.g. MIDI ≥ ~103) produce timers below 8 and silently mute the channel
  instead of playing. The exporter writes `pitch & 0xFF` / `(pitch>>8)&0x07` — masking
  only, never enforcing `>= 8`.
- **Evidence**: `generate_note_table()` for MIDI 107 ≈ timer 7 (< 8); no path raises this
  to 8. `docs/APU_PULSE_REFERENCE.md` §7 explicitly: "Our Python exporter and frequency
  tables **must clamp timer values to >= 8**."
- **Impact**: High notes on pulse/triangle go silent; wrong output on common high-register
  melodies. HIGH per the out-of-range rule.
- **Related**: NH-02, NH-03.
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §3 ("t < 8 → channel silenced"), §5
  cond. 4, §7 ("must clamp timer values to >= 8"); `docs/NES_APU_REFERENCE.md` §2.1.
- **Suggested Fix**: Clamp note timers to `max(8, min(timer, 0x7FF))` in the table
  generators and re-assert it at the exporter before the byte split.

### NH-07: Sweep units ($4001/$4005) never disabled at init — stale sweep can bend pitch
- **Severity**: HIGH
- **Dimension**: 1 (Pulse sweep) + 9 (register init)
- **Location**: `exporter/exporter_ca65.py:213-219` (reset init), `542-548` (`init_music`)
- **Description**: `APU_PULSE1_SWEEP=0x4001` / `APU_PULSE2_SWEEP=0x4005` are defined but
  the engine **never writes them**, including in the init sequences. The init writes only
  `$4015`, `$4017`, `$4015`. The sweep unit's power-on state is not guaranteed disabled;
  per the pulse reference a sweep left enabled continuously bends the channel's pitch
  (mixer condition 2 can also silence on overflow). A correct init must zero `$4001`/`$4005`.
- **Evidence**: reset proc writes `sta $4015` / `sta $4017` / `sta $4015` only; no
  `sta $4001`/`sta $4005` anywhere in the file.
- **Impact**: Possible uncontrolled pitch bend / silencing on pulse channels depending on
  power-on garbage; intermittent, hard-to-reproduce wrong pitch across ROMs.
- **Related**: NH-09 (init completeness).
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §1 (sweep unit feeds the timer), §2
  (`$4001/$4005` `EPPP.NSSS`), §5 cond. 2 (sweep overflow silences).
- **Suggested Fix**: Add `lda #$08 / sta $4001 / sta $4005` (sweep disabled, valid shift)
  — or `#$00` with enable bit clear — to both init paths.

### NH-08: Dead/contradictory pulse volume expression in `compile_channel_to_frames`
- **Severity**: MEDIUM
- **Dimension**: 6 (velocity → 4-bit volume)
- **Location**: `nes/emulator_core.py:59`
- **Description**: The pulse-branch `volume` is
  `min(15, velocity // 8) if velocity == 0 else max(1, int(15*pow(velocity/127,1.5)))`.
  The `velocity == 0` arm is **unreachable**: the loop `continue`s on velocity 0 at
  line 29-30, so `velocity` is always > 0 here. The dead arm `velocity // 8` is also a
  linear mapping that contradicts the 1.5-power curve used everywhere else. Harmless
  today (the live control byte for pulse comes from `get_envelope_control_byte`, not this
  `volume` field), but it is misleading dead code that masks intent.
- **Evidence**: `if velocity == 0: continue` (line 29) then `... if velocity == 0 else ...`
  (line 59).
- **Impact**: None functionally (pulse playback uses `control`); cosmetic/maintenance.
- **Related**: NH-10.
- **Hardware ref**: `docs/APU_PULSE_REFERENCE.md` §1 (4-bit volume); curve rationale in
  `docs/APU_ENVELOPE_REFERENCE.md` §4–§5.
- **Suggested Fix**: Drop the unreachable branch; keep the single power-curve expression.

### NH-09: `export_direct_frames` emits an iNES header for MMC1 while the pipeline builds MMC3
- **Severity**: MEDIUM
- **Dimension**: 9 (register/header correctness — cross-ref mappers)
- **Location**: `exporter/exporter_ca65.py:70-75`
- **Description**: The standalone direct export hardcodes `.byte $10 ; Mapper 1 (MMC1)`
  and `$08 ; 128K PRG ROM (MMC1)`. The prepare/full pipeline uses `MMC3Mapper`
  (`CLAUDE.md`, `_audit-common.md` "prepare → default mapper MMC3"). A standalone ROM
  emitted this way declares MMC1 in its header regardless of the project's MMC3 linker
  config — a header/linker mismatch if these are ever combined.
- **Evidence**: header bytes `$08` / `$10` at lines 72-74 vs prepare default MMC3.
- **Impact**: Standalone direct-export ROMs misdeclare the mapper; only bites when this
  path is used to produce a final ROM (not the main pipeline). Cross-refs the mapper audit.
- **Related**: NH-01 (direct path also drops noise/dpcm).
- **Hardware ref**: `docs/NES_APU_REFERENCE.md` (iNES header overview); mapper detail in
  `docs/MAPPER_MMC1_REFERENCE.md` / `docs/MAPPER_MMC3_REFERENCE.md`.
- **Suggested Fix**: Parameterize the header mapper byte/PRG size from the selected mapper
  rather than hardcoding MMC1, or document the direct path as MMC1-only.

### NH-10: Additive pitch modification in the dead duplicate core re-opens the 11-bit clamp
- **Severity**: LOW
- **Dimension**: 5 + 10 (clamp re-opened by additive step)
- **Location**: `nes/envelope_processor.py:203-206` (dead `NESEmulatorCore`)
- **Description**: The duplicate `NESEmulatorCore.compile_channel_to_frames` in
  `envelope_processor.py` adds vibrato (`modified_pitch += pitch_mod`) **after** the
  pitch was clamped, with **no re-clamp**; the exporter then masks (`& 0xFF` /
  `& 0x07`) rather than clamps, so an out-of-range value wraps silently. This would be
  HIGH on a live path, but this `NESEmulatorCore` is **dead** — `main.py` imports
  `nes/emulator_core.py`, whose live `compile_channel_to_frames` applies no pitch_mod.
  Filed LOW as a latent trap + duplication.
- **Evidence**: `main.py:51` uses `nes.emulator_core`; the effects/vibrato path exists
  only in `nes/envelope_processor.py`'s copy.
- **Impact**: None today (dead); becomes HIGH if this copy is ever wired in.
- **Related**: NH-08; duplication of `NESEmulatorCore`.
- **Hardware ref**: `docs/APU_PITCH_TABLE_REFERENCE.md` §1 (11-bit range);
  `docs/APU_PULSE_REFERENCE.md` §3 (`t < 8` silence).
- **Suggested Fix**: Delete the duplicate `NESEmulatorCore` in `envelope_processor.py`;
  if vibrato is wanted, add it to the live core with a re-clamp to `[8, 0x7FF]`.

### NH-11: `note_to_timer` range guard contradicts the channel ranges it serves
- **Severity**: LOW
- **Dimension**: 5 / 10 (range validation consistency)
- **Location**: `nes/pitch_table.py:129-135`
- **Description**: `note_to_timer` raises for `midi_note >= 96` ("out of NES range
  (24-95)"), but `CHANNEL_RANGES`/`channel_ranges` allow pulse up to MIDI 108 and the
  note table is generated for the full 0–127. The guard is inconsistent with the rest of
  the module (which clamps rather than raises) and would reject legal pulse notes 96–108
  if used. It appears unused on the live path but is a correctness/consistency trap.
- **Evidence**: `if midi_note < 24 or midi_note >= 96: raise ValueError(... "(24-95)")`
  vs `channel_ranges["pulse1"] = (24, 108)`.
- **Impact**: None today (unused); a foot-gun if adopted.
- **Hardware ref**: `docs/APU_PITCH_TABLE_REFERENCE.md` §2 (full 0–127 MIDI indexing).
- **Suggested Fix**: Align the guard with the 11-bit/`t>=8` clamp policy (clamp, don't
  raise), or remove the dead method.

### NH-12: Doc-rot — `export_direct_frames` header comments/mapper conflict with MMC3 default
- **Severity**: LOW
- **Dimension**: cross-cutting (doc-rot)
- **Location**: `exporter/exporter_ca65.py:72-74`; cross-ref `CLAUDE.md` "Always use MMC1"
- **Description**: `CLAUDE.md`'s "ROM Structure" section still says "Always use MMC1
  mapper configuration / PRG-ROM 128KB", while the live pipeline (`prepare`,
  `run_full_pipeline`) uses MMC3 and `_audit-common.md` documents MMC3 as the default.
  The exporter header comments perpetuate the stale MMC1 claim. Pure documentation drift
  (the functional mismatch is NH-09).
- **Evidence**: `CLAUDE.md` "Always use MMC1 mapper configuration"; `_audit-common.md`
  "prepare → default mapper MMC3".
- **Impact**: Misleads contributors about the mapper in use.
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` (the actual default mapper).
- **Suggested Fix**: Update `CLAUDE.md` ROM Structure and the exporter comments to MMC3.

---

## Notes on what was verified clean

- **Pulse duty/volume control byte** (`get_envelope_control_byte`,
  `nes/envelope_processor.py:120-126`): duty masked `(duty & 0x03) << 6` (bits 6-7),
  constant-volume flag `0x10` (bit 4) set, volume `& 0x0F` (bits 0-3) — matches
  `docs/APU_PULSE_REFERENCE.md` §2 and `docs/APU_ENVELOPE_REFERENCE.md` §4. Correct.
- **Triangle control invariant** (`process_all_tracks` → non-pulse branch): triangle
  frames carry only `volume`/`pitch`, **no duty/control byte**; `export_direct_frames`
  derives a linear-counter value `0x80 | (volume*7)` for `$4008` and `$00` for silence
  (`exporter/exporter_ca65.py:150-158,517-519`) — a linear-counter control, not a
  borrowed pulse volume/duty byte. Matches `docs/APU_TRIANGLE_REFERENCE.md` §4 and the
  Method-1 silence (`$00`/`$80` to `$4008`, §5). Correct (no Triangle-volume violation).
- **`$4017` init** = `lda #$40 / sta $4017` (`exporter/exporter_ca65.py:216-217`):
  `$40 = %01000000` = 4-step mode, IRQ inhibit set — matches
  `docs/APU_FRAME_COUNTER_REFERENCE.md` §4 ("Writing `$40` sets 4-step mode, IRQ
  disabled"). Correct. (Note: the SKILL text calling `$40` "5-step" is itself imprecise;
  the doc and code agree it is 4-step/IRQ-off.)
- **`$4015` enable** = `lda #$0F / sta $4015` after the `$4017` write
  (`exporter/exporter_ca65.py:218-219`, `544`): enables pulse1/pulse2/triangle/noise
  (`---D NT21` low nibble) per `docs/NES_APU_REFERENCE.md` §3.1. The enable bits are
  present even though noise data is never produced (NH-01).
- **Velocity → 4-bit volume curve** (`int(15*pow(v/127,1.5))`, `max(1,…)`, `min(15,…)`):
  stays in 0–15 and never collapses a present note to 0 — consistent with
  `docs/APU_PULSE_REFERENCE.md` §1 / `docs/APU_ENVELOPE_REFERENCE.md` §4. In range.
- **Register addresses** `APU_*` (`exporter/exporter_ca65.py:7-30`) all fall in
  `$4000–$4015` and map to the correct channel/function per
  `docs/NES_APU_REFERENCE.md` §3.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-06-28.md
```
