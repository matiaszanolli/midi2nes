# NES Hardware Correctness Audit — 2026-07-17

Scope: the boundary where Python numbers become APU register writes — `nes/emulator_core.py`,
`nes/pitch_table.py`, `nes/envelope_processor.py`, `nes/audio_engine.asm`, and the serializer
`exporter/exporter_ca65.py`. All 10 dimensions swept. Primary task: re-verify the additive
pitch macro reconstruction stays within the 11-bit timer range now that the CA65 serializer
emits nonzero `pitch_seq` offsets.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 (Existing #167) |
| MEDIUM   | 0 |
| LOW      | 1 (NEW) |

**Headline:** No new hardware-range or vector/init defect. The recent bug-fixing sprint holds
across every dimension checked. The one HIGH is a pre-existing, already-tracked open issue
(#167 / NH-25), re-confirmed still reproducing. The one NEW finding is a LOW dead-code residual.

**Primary-task result (additive pitch macro, Dim 5/10): PASS — reconstruction stays ≤ `$7FF`.**
Empirically enumerating every producible note through both channel paths, the runtime
reconstruction `ntsc_period[current_note] + temp_pitch` ranges over `[24, 2047]` = `[$18, $7FF]`,
maxing at exactly `$7FF` (the lowest note, delta 0) and never exceeding it. The offset is only
ever ≤ 0 in practice: the serializer clamps the *stream* note to ≤ 95 (`exporter/exporter_ca65.py:1082`)
while the frame `pitch` is clamped to the channel ceiling (108/96), so the delta
`pitch_val - base_timer` is negative for top-of-range notes and 0 elsewhere; both operands come
from the same per-channel table (`ntsc_period_*`/`triangle_period_*` are emitted directly from
`NES_NOTE_TABLE`/`NES_TRIANGLE_TABLE`, `exporter/exporter_ca65.py:1023-1027`), so the reconstruction
is `= pitch_val` (exact, modulo the ±1-unit `$FE/$FF` snap in `_encode_macro_offset`). Worst-case
delta magnitude observed is ~30 units — far inside the `[-128, 127]` encoding window, so no
clamp-to-`-128` underflow either. This matches the prior audit's finding; no producer widens the
delta past the 11-bit ceiling (arp add is still fed the neutral `_encode_macro_offset(0)`).

## Dimension verification ledger (no finding unless noted)

- **Dim 1 — Pulse duty/vol/timer/sweep:** duty `(duty & 0x03) << 6`, const-volume `0x10`, volume
  `& 0x0F` all correct in `envelope_processor.py:132-137`. Sweep disabled (`lda #$08`) at **both**
  init sites (`exporter/exporter_ca65.py:471-473`, `:851-853`). Bytecode phase-reset guard
  (`last_written_hi`) intact for both pulses (`nes/audio_engine.asm:419-423, 456-460`). **See
  finding below for the direct-export halt-bit gap (NH-25).**
- **Dim 2 — Triangle no-volume/no-duty:** non-pulse branch (`emulator_core.py:115-126`) emits only
  `pitch`/`volume`/`note`, no `control`/duty. Direct-export triangle control derived independently
  as `0x80 | (volume*7)` or `0x00` (`exporter/exporter_ca65.py:343-346`) — real linear-counter
  reload, `bit 7` set (length/linear halt). `@silence` writes `$00`. No pulse control byte leaks.
- **Dim 3 — Noise:** `get_noise_period` single source of truth, clamps to range 24–60, inverts
  (`pitch_table.py:62-75`); `PitchProcessor._get_noise_period` delegates. Period floored at 1,
  mode `& 1`, `NOISE_DECAY_FRAMES=6` software ramp yields audibly distinct steps
  (15,13,10,8,5,2 at peak) and is truncated on re-trigger (`emulator_core.py:158-186`). Direct-export
  ctrl = `$30 | vol` (const vol + halt) (`exporter/exporter_ca65.py:409`). `noise_mode` still has no
  producer — **Existing #204 / NH-29 (dead-but-correct plumbing)**.
- **Dim 4 — DPCM/DMC:** `dpcm` branch emits `volume:15` as a trigger gate, not a level
  (`emulator_core.py:226-230`). `$4011` written only at init to zero the DAC. `play_dpcm` triggers
  via `$4015=$1F` (`exporter/exporter_ca65.py:823-824`). See LOW finding for the orphan
  `@cmd_dmc_level` handler.
- **Dim 5 — Per-channel pitch tables + 11-bit clamp:** both tables built from `generate_note_table`
  (divider 16/32), clamp `max(8, min(timer, 0x7FF))` (`pitch_table.py:41-45`); `apply_pitch_bend`
  re-clamps. Exporter base timer branches on `channel == 'triangle'` (`:52-54`), clamps note 24–119
  (#158). Direct-export re-asserts `max(8, min(pitch, 0x7FF))` before byte split (`:354-360`).
  **Additive-pitch reconstruction verified ≤ `$7FF` (see Summary).**
- **Dim 6 — Velocity→4-bit volume:** `max(1, int(15*pow(v/127,1.5)))` in all three sites; envelope
  combine `min(15, round((env*midi)/15.0))` cannot reach 16 (both factors ≤15, round of 15.0 = 15).
  All outputs in `[0,15]`.
- **Dim 7 — Envelope/ADSR:** inert scaffolding confirmed — `effects` hardcoded `None`
  (`emulator_core.py:107`), no producer sets `envelope_type` (grep clean outside tests); every real
  note plays flat `default`. Const-volume bit `0x10` set unconditionally. Percussion divide
  (`envelope_processor.py:69`) is both unreachable (no producer) *and* structurally guarded (the
  denominator can only be 0 when `frame_offset < note_duration-1` is already false). **Existing
  #166 / NH-24 (closed-as-documented).**
- **Dim 8 — 60Hz frame counter:** both init sites write `lda #$40 / sta $4017` (4-step mode 0, IRQ
  inhibit); comments now correctly say "mode 0" (`exporter/exporter_ca65.py:465-466, 847-848`).
  NH-22 doc-rot fix holds. Frame model iterates integer frames.
- **Dim 9 — Register addresses / `$4015`:** all `sta $40xx` land in-window; both init sites enable
  `$4015=$0F`; DMC enabled to `$1F` only on trigger. All channels a song uses are covered.
- **Dim 10 — Value-range clamping sweep:** timers floored-at-8/11-bit-clamped; volume/duty masked;
  noise index masked `& 0x0F`; dmc "level" is a trigger gate. Both live unclamped-add sites in
  `audio_engine.asm` receive only in-range (pitch) or neutral-zero (arp) deltas — verified above.

## Findings

### NH-HW-2026-07-17-1: Direct-export pulse control byte omits the length-counter halt flag
- **Severity**: HIGH
- **Dimension**: 1 (Pulse) / 7 (constant-output)
- **Location**: `exporter/exporter_ca65.py:611-626` (`play_pulse1`), `:665-680` (`play_pulse2`);
  control byte source `nes/envelope_processor.py:132-137`; frame value `nes/emulator_core.py:106-114`
- **Status**: Existing: #167 (NH-25) — re-confirmed still reproducing
- **Description**: The direct-export (`--no-patterns`) pulse "new note" path writes the control
  byte straight from `pulse{1,2}_control` (`= duty_bits | 0x10 | volume` from
  `get_envelope_control_byte`) to `$4000`/`$4004`. **Bit 5 (length-counter halt, `0x20`) is never
  set.** The same routine then does `ora #$08` before `sta $4003`/`sta $4007`, loading a real
  (short) length-counter value on every new note. `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 mandates
  the halt flag always be set so the 60Hz software model isn't undercut by the hardware length
  counter. The bytecode engine does this correctly (`ora #$30` on `$4000`/`$4004`,
  `nes/audio_engine.asm:390, 431`); only the direct-export path is affected.
- **Evidence**: `envelope_processor.py:137` returns `duty_bits | envelope_bits | (volume & 0x0F)`
  with `envelope_bits = 0x10` (no `0x20`). `exporter/exporter_ca65.py:625` `ora #$08 ; Set length
  reload for new notes` then `sta $4003`. With halt clear, the loaded length counter decrements at
  the frame-counter rate.
- **Impact**: A `--no-patterns` pulse note held longer than the reloaded length-counter duration is
  cut off mid-note by hardware regardless of continued frame writes. Now that NH-20 (#160) lets real
  note durations flow through, this is a live audible defect on sustained pulse notes in direct
  builds. Blast radius: any `--no-patterns` ROM (NROM/MMC1 builds always take this path); pulse1/pulse2.
- **Hardware ref**: `docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 "Engine Implementation Notes";
  `docs/APU_PULSE_REFERENCE.md` §1 (control byte layout, bit 5 = length halt / envelope loop).
- **Related**: #167. Distinct from the bytecode path (correct). Cross-refs NH-14 (#107, the
  neighboring `@silence` dead-branch issue).
- **Suggested Fix**: OR `0x20` into the pulse control byte for the direct-export path (either in
  `get_envelope_control_byte` — but that would also touch the bytecode path, which already sets it
  via `ora #$30` — or, more surgically, emit `ora #$20` before `sta $4000`/`$4004` in
  `play_pulse1`/`play_pulse2`). Verify no double-halt regression in the bytecode engine.

### NH-HW-2026-07-17-2: Orphan `@cmd_dmc_level` handler in the live playback engine (dead code)
- **Severity**: LOW
- **Dimension**: 4 (DPCM/DMC)
- **Location**: `nes/audio_engine.asm:222` (`beq @cmd_dmc_level`), `:259-260` (`@cmd_dmc_level` /
  `CMD_DMC_LEVEL $87` handler)
- **Status**: NEW
- **Description**: The `CMD_DMC_LEVEL` ($87) producer was removed (#72 / D-09) — no exporter path
  emits the opcode, guarded by regression test
  `tests/test_ca65_export.py::test_dmc_level_command_path_removed`. The **consumer** side (the
  dispatch `beq` and the `@cmd_dmc_level` handler that reads a 7-bit operand and writes `$4011`)
  still lives in `audio_engine.asm`. It is unreachable dead code: `$87` can never appear in the
  emitted bytecode stream. There is no real hardware "DMC volume" register, so this is correct to
  leave dead, but the orphan handler and its dispatch branch are pure residue.
- **Evidence**: `grep CMD_DMC_LEVEL exporter/exporter_ca65.py` → no producer; the handler exists
  only in `nes/audio_engine.asm:259`.
- **Impact**: None at runtime (unreachable). Maintenance/clarity only — invites a future reader to
  wire up a `$4011` level write that hardware doesn't support as a channel volume.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2–§3 (`$4011` is a one-shot 7-bit DAC load, not a
  per-note volume).
- **Related**: #72 / D-09 (producer removal); sibling dead-code issues #203 (NH-28), #204 (NH-29),
  #107 (NH-14).
- **Suggested Fix**: Delete the `@cmd_dmc_level` label/handler and its `beq @cmd_dmc_level` dispatch
  entry from `nes/audio_engine.asm`; keep the `$4011`-at-init DAC-zero write untouched.

---
Suggested next step:
```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-07-17.md
```
