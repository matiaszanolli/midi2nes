# NES Hardware Correctness Audit — 2026-07-18

Scope: the boundary where Python numbers become APU register writes —
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_engine.asm`, and the serializer `exporter/exporter_ca65.py`. All 10
dimensions swept on branch `master` (HEAD `272a186`). This run re-derives the whole
subsystem from the current committed tree (the prior `AUDIT_NES_HARDWARE_2026-07-18.md`
audited an unmerged working-tree diff on branch `fix/audit-167-88-91`; that branch has
since merged, so this report supersedes it against `master`).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 1 (NEW) |

**Highest-risk hardware divergences (wrong on every ROM):** none found. All the
per-ROM-fatal invariants hold on `master`:

- **Halt bit (NH-25 / #167) is fixed in code.** `get_envelope_control_byte` now returns
  `duty_bits | 0x30 | (volume & 0x0F)` — bit 5 (length-counter halt) is set
  unconditionally, so a sustained direct-export pulse note can no longer be cut mid-note
  by the hardware length counter (commit `cb2a8ac`). The tracker issue #167 is still
  **OPEN**, but the code carries the fix; this is stale-tracker state, not a live defect,
  and is skipped as a finding per the dedup protocol.
- **NH-14 (#107, unreachable direct-export `@silence`) is fixed** — every tone-channel
  proc now re-tests the loaded note with `cmp #0` after the flag-clobbering `sta`, so the
  `beq @silence` branch is reachable and note-off no longer reloads the length counter /
  resets the pulse phase (commit `0859b79`; #107 CLOSED).
- **NH-29 (#204, noise-mode dead plumbing) is resolved** — `noise_mode` now has a real
  producer (`dpcm_sampler/enhanced_drum_mapper.py:_noise_mode_for_note`, wired at
  `:334`/`:396`), so the mode bit is reachable end-to-end (#204 CLOSED).
- **#309 (@cmd_dmc_level orphan handler)** — the removal (`f78c618`) is now present on
  `master`; `grep -n cmd_dmc_level nes/audio_engine.asm` returns nothing. The LOW finding
  the prior 07-18 report raised against the unmerged branch no longer applies.

The one NEW finding (LOW) is a defense-in-depth gap on the `--no-patterns` direct-export
path only: its APU init never zeroes the DMC DAC (`$4011`), unlike the bytecode engine.

## Dimension verification ledger (no finding unless noted)

- **Dim 1 — Pulse duty/vol/timer/sweep:** duty `(duty_cycle & 0x03) << 6`
  (`envelope_processor.py:142`) and volume `& 0x0F` (`:155`) correct; constant-volume +
  halt is `0x30` (`:153`), matching the bytecode engine's `ora #$30`
  (`audio_engine.asm:381,422`). Sweep disabled (`lda #$08` → `$4001`/`$4005`) at all
  three init sites: standalone `reset` (`exporter_ca65.py:471-473`), `init_music`
  (`:854-856`), and `audio_engine.asm:143-145`. `$08` = `E`(bit7)=0 → unit disabled per
  `docs/APU_PULSE_REFERENCE.md` §1/§5, regardless of the stray negate bit; no path
  re-enables sweep. Bytecode phase-reset guard (`last_written_hi`, `.res 5`) intact —
  `$4003`/`$4007` written only on a changed high byte (`audio_engine.asm:410-414,447-451`).
  `grep -rn PULSE_DUTY_CYCLES` returns nothing (NH-15 removal holds).
- **Dim 2 — Triangle no-volume/no-duty:** `process_all_tracks` routes triangle through
  the non-pulse branch (`emulator_core.py:128-134`, `duty = None`), whose frame dict
  carries only `pitch`/`volume`/`note` — `get_envelope_control_byte` is never called, so
  no duty/4-bit-volume byte can reach `$4008`/`$400B` (`:114-120`). Direct-export triangle
  control is derived independently as a real linear-counter reload
  (`0x80 | (volume * 7)` / `0x00`, `exporter_ca65.py:343-346`), volume ≤15 so
  `volume*7` ≤ 0x69 stays inside the 7-bit reload field. `@silence_tri` writes `$80`
  (`audio_engine.asm:482`) and direct-export `@silence` writes `$00`
  (`exporter_ca65.py:739`) — both silence per `docs/APU_TRIANGLE_REFERENCE.md` §5;
  neither writes a pulse-style volume.
- **Dim 3 — Noise:** `get_noise_period` (`pitch_table.py:62-75`) is the single source of
  truth (clamp to `CHANNEL_RANGES["noise"]` 24–60, scale 0–15, invert `15 - scaled`);
  `PitchProcessor._get_noise_period` delegates to it (`:110-116`). `process_all_tracks`
  computes a real period via `midi_to_nes_pitch(..., 'noise')` floored at 1, reads
  `noise_mode` from the event (`:160`), and the mode bit now has a live producer (Dim 3
  wiring, NH-29 resolved). The `NOISE_DECAY_FRAMES = 6` software ramp
  (`peak*(span-offset)/span`, floored at 1, `:172-179`) reaches audible decay (e.g. peak
  15 → 15,12,10,8,5,2) and a re-trigger truncates the prior tail via
  `end_frame = min(end_frame, next_frame)` (`:167-170`). Direct-export noise ctrl is
  `0x30 | vol` (`exporter_ca65.py:409`) — halt + constant volume set.
- **Dim 4 — DPCM/DMC:** `dpcm` branch emits `volume: 15` as a one-shot trigger gate, not
  a level (`emulator_core.py:219-222`). The only `$4011` write in the bytecode engine
  zeroes the DAC at init (`audio_engine.asm:128`); the trigger paths write only
  `$4010`/`$4012`/`$4013`/`$4015=$1F` (`:246-254`, `:523-530`; `exporter_ca65.py:822-824`).
  `@cmd_dmc_level` handler is gone from `master`. **See the LOW finding** below — the
  direct-export init omits the `$4011` DAC-zero that this same engine performs.
- **Dim 5 — Per-channel pitch tables + 11-bit clamp:** `generate_note_table(divider)`
  builds `NES_NOTE_TABLE` (÷16) and `NES_TRIANGLE_TABLE` (÷32) from one function with
  `timer = max(8, min(timer, 0x07FF))` (`pitch_table.py:41-52`). `get_channel_pitch`
  branches on `channel_type == "triangle"` (`:105-108`); the exporter's
  `midi_note_to_timer_value` branches identically (`exporter_ca65.py:52-54`), so the frame
  `pitch` and the base timer it is differenced against stay on the same table.
  `apply_pitch_bend` re-clamps `max(8, min(new_timer, 0x07FF))` (`:130-131`). NH-16
  clamp bounds `24..119` (`:46`) are consistent with `CHANNEL_RANGES`.
  **Additive-pitch re-verification:** the live macro producer emits
  `pitch_offset = _encode_macro_offset(pitch_val - base_timer)` (`:1140`, `:1159`) only
  where the instruction-stream note is clamped to ≤95 (`:1085`) while the frame `pitch`
  reflects the channel-clamped note (≤108 pulse / ≤96 triangle). Worked example, pulse
  MIDI 108: base = `NES_NOTE_TABLE[95]` = 55, `pitch_val` = `NES_NOTE_TABLE[108]` = 25,
  delta = −30 (in `[-128,127]`, no `$FE`/`$FF` collision). Runtime reconstruction
  `ntsc_period_low[95]=0x37` `adc 0xE2` → `0x19` (25) with the sign-extended high byte
  resolving to 0 (`audio_engine.asm:397-403`) — stays ≤ `$7FF` and ≥ 8. Every producible
  delta is a small negative, so the un-re-clamped add is in-range (correct, not a bug).
  Flag HIGH only if a producer ever widens the delta past the 11-bit ceiling.
- **Dim 6 — Velocity→4-bit volume:** single shared `velocity_to_volume`
  (`envelope_processor.py:4-15`): `max(1, int(15*pow(v/127,1.5)))`, clamped `[0,15]` and
  `0` only for `velocity ≤ 0` (filtered upstream by the note-off `continue`). Both
  `emulator_core.py` branches use it (`:112`, `:118`, `:161`). The envelope-combine step
  `min(15, round((envelope_volume * midi_volume) / 15.0))` (`:133`) cannot exceed 15
  (both factors ≤15 → product/15 ≤15, `round(15.0)=15`), and the return masks `& 0x0F`.
- **Dim 7 — Envelope/ADSR:** still inert scaffolding — `effects` hardcoded `None`
  (`emulator_core.py:106`); `grep -rn "envelope_type" --include=*.py .` outside tests
  shows no producer, so every real note plays the flat `default (0,0,15,0)` envelope. The
  constant-volume flag (bit 4) is set unconditionally as part of `0x30` (`:153`). The
  percussion divide-by-zero shape in `get_envelope_value` (`:84`) remains unreachable
  because no producer selects `envelope_type="percussion"`. Existing #166/NH-24
  (closed-as-documented) — unchanged.
- **Dim 8 — 60Hz frame counter:** all init sites write `lda #$40` / `sta $4017`
  (`exporter_ca65.py:465-466`, `:850-851`; `audio_engine.asm:133-134`) = 4-step mode
  (bit7 clear) + frame-IRQ inhibit (bit6 set) per `docs/APU_FRAME_COUNTER_REFERENCE.md`
  §2–§3; all three comments correctly read "mode 0" (NH-22 doc-rot fix holds). Frame model
  is integer-per-tick (`compile_channel_to_frames` iterates `range(start_frame,
  end_frame)`, `:102`; NMI `inc frame_counter`, `audio_engine`/direct-export). No float
  frame accumulation in the engine.
- **Dim 9 — Register addresses / `$4015`:** every emitted `sta $40xx` lands in
  `$4000-$4017` (swept: `$4000-$400F`, `$4010`, `$4012`, `$4013`, `$4015`, `$4017`; no
  `$4011` in the exporter procs — see LOW finding). Both init sites enable channels via
  `$4015 = $0F` and defer DMC (bit 4) to the trigger's `$1F` write. `APU_*` constants
  (`exporter_ca65.py:6-29`) map to the correct channel/function.
- **Dim 10 — Value-range clamping sweep:** note → channel-range clamp; timer →
  `max(8, min(·, 0x7FF))` (table build + `apply_pitch_bend` + the exporter's pre-split
  re-assert `exporter_ca65.py:354-355`); volume → `& 0x0F`; duty → `& 0x03`; noise index
  → `get_noise_period` `[0,15]`; dmc "level" → trigger gate, no register value. Live
  unclamped-add sites re-verified: the pitch-macro add receives only small negative
  deltas (Dim 5, in-range); the arp add (`adc temp_arp`, `audio_engine.asm:339-342`) is
  fed only the neutral `0` offset (no `arp` producer). Both would become HIGH the moment a
  producer widens their input past the register ceiling with no guard added.

## Findings

### NH-HW-2026-07-18-1: Direct-export APU init never zeroes the DMC DAC (`$4011`)
- **Severity**: LOW
- **Dimension**: 4 (DPCM/DMC)
- **Location**: `exporter/exporter_ca65.py:445-486` (standalone `reset` proc),
  `:848-860` (`init_music`)
- **Status**: NEW
- **Description**: `docs/APU_DMC_REFERENCE.md` §5 "Silence Initialization" states the
  engine init routine "should write `$00` to `$4011` to ensure the DPCM counter starts at
  0 and doesn't accidentally muffle the other channels" (the non-linear mixer means a
  nonzero DMC output level inversely attenuates Triangle/Noise, §5 "Non-linear Mixer
  Trick"). The bytecode/pattern engine performs this init (`nes/audio_engine.asm:127-128`,
  `sta $4011`). The **direct-export** path emitted by `export_direct_frames`
  (`--no-patterns`) — both the standalone `reset` proc and the project-builder-facing
  `init_music` — initializes `$4015`, `$4017`, and the sweep units but **omits the
  `$00 → $4011` DAC-zero**, even though the same path emits `play_dpcm` and can trigger
  DPCM samples. On power-on the DMC DAC is already 0, so there is no defect on a fresh
  boot; the gap manifests only on a soft reset (the DAC retains its prior level), where
  Triangle/Noise can come back muffled. The prior `AUDIT_NES_HARDWARE_2026-07-06.md` (Dim
  4) stated "`$4011` written only to zero the DAC at the live init sites" — that is
  accurate for the bytecode engine but overlooked the direct-export init, which is a live
  init site that does *not* zero it.
- **Evidence**:
  ```
  $ grep -n 'sta \$4011' nes/audio_engine.asm exporter/exporter_ca65.py
  nes/audio_engine.asm:128:    sta $4011          # bytecode engine: DAC zeroed
  # exporter_ca65.py: no match — neither reset nor init_music zeroes $4011
  ```
  `init_music` (`exporter_ca65.py:848-860`) writes `$4017`, `$4015`, `$4001`/`$4005`,
  `frame_counter` — no `$4011`. Standalone `reset` (`:462-478`) likewise.
- **Impact**: `--no-patterns` (direct-export) ROMs only. No audible defect on power-on
  (DAC = 0); on soft reset the un-zeroed DMC output level can DC-offset the mixer and
  attenuate Triangle/Noise. Defense-in-depth / consistency gap between the two export
  engines, not a wrong-on-every-ROM divergence. The default (pattern/MMC3) path is
  unaffected.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §5 "Silence Initialization" and
  "Non-linear Mixer Trick" (`$4011` DAC starts at 0 for safety; nonzero level muffles
  Triangle/Noise).
- **Related**: #203/NH-28 (`nes/mmc3_init.asm` is dead code — it *does* zero `$4011` but
  is never included in any generated project, so it does not cover this path). Prior
  DPCM audits (`AUDIT_DPCM_2026-07-18.md:323-324`) verified the `$4011` init on
  `mmc3_init.asm`, which is exactly the dead file.
- **Suggested Fix**: Add `lda #$00` / `sta $4011` to `init_music` (and the standalone
  `reset` APU-init block) in `exporter/exporter_ca65.py`, mirroring
  `nes/audio_engine.asm:127-128`, so both export engines satisfy the doc's silence-init
  mandate.

---
Suggested next step:
```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-07-18.md
```
