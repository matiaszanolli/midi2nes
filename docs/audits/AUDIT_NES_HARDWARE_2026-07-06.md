# NES Hardware Correctness Audit — 2026-07-06

Audit of the boundary where Python numeric values become APU register writes, across the
10 hardware dimensions in `.claude/commands/audit-nes-hardware/SKILL.md`, at HEAD `8308a63`.
Hot files: `nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`exporter/exporter_ca65.py`, `nes/audio_engine.asm`, plus the `--arranger` control-byte
producer (`arranger/voice_allocator.py`, `arranger/pipeline_integration.py`).

**Purpose of this pass.** The immediately preceding pass (`AUDIT_NES-HARDWARE_2026-07-05.md`,
HEAD `a7de0d4`) reported one new MEDIUM (NH-30) and re-verified 10 open findings. Since then
a bug-fixing sprint landed several of those fixes and refactored the exporter. This pass:
(a) confirms the sprint fixes actually landed and are complete; (b) re-verifies the still-open
NES-hardware findings hold at HEAD; (c) re-traces the exporter refactor (`_emit_safe_beq`,
`_pack_direct_tables_into_banks`) and the now-live pitch-macro path for regressions.

**Dedup sources:** `/tmp/audit/issues.json` (29 open issues), all prior reports in
`docs/audits/` — especially `AUDIT_NES-HARDWARE_2026-07-05.md` and
`AUDIT_NES_HARDWARE_2026-07-01.md`.

## Fix verification — prior findings closed by the sprint (`a7de0d4..8308a63`)

| Prior finding | Status at `8308a63` | Evidence |
|---|---|---|
| **NH-30 (MEDIUM, 2026-07-05)** — arranger pulse `vel // 8` floors soft notes to volume 0 | **FIXED** (#268, commit `f4a1f54`) | `arranger/voice_allocator.py:416,424` now `"volume": max(1, vel // 8)`; comment cites parity with `nes/emulator_core.py`'s `max(1, …)` floor |
| **#41 / NH-11 (LOW)** — `PitchProcessor.note_to_timer` raised for legal notes 96–108 | **FIXED** (#41, commit `6bf54d7`) | `nes/pitch_table.py:133-147` now clamps to `channel_ranges["pulse1"]=(24,108)` and returns `note_table[note]` instead of raising |
| **#163 / NH-21 (MEDIUM)** — exporter emitted `$FE` loop control byte the engine can't decode | **FIXED** (commit `a3c021b`) | `exporter/exporter_ca65.py:56-69` documents `$FE`/`$FF` reserved-out-of-data; `_encode_macro_offset` (`:71-86`) snaps `-1→0`, `-2→-3` so no data byte collides; `_compress_macro` never emits `$FE` |
| **#164 / NH-22 (LOW)** — `$4017=$40` mislabelled "mode 1" | **PARTIALLY FIXED** (commit `a3c021b`) — 2 of 3 sites; see NH-31 below | `exporter/exporter_ca65.py:848` and `nes/audio_engine.asm:131` now read "4-step mode (mode 0)"; `nes/mmc3_init.asm:63` still reads "(Mode 1)" |
| **#165 / NH-23 (LOW)** — dead `NOISE_PERIODS` / `is_midi_velocity` tables | **FIXED** (commit `1bf4a95`) | `grep NOISE_PERIODS\|is_midi_velocity exporter/exporter_ca65.py` returns nothing |
| **#166 / NH-24 (LOW)** — inert arpeggio/envelope plumbing | **FIXED / documented** (commit `1bf4a95`) | Inert arp offset now explicitly the neutral encoding (`exporter/exporter_ca65.py:1118-1121,1137`); `envelope_processor.py:1-15` docstring documents the scaffolding intent |

## Re-verification — still-open findings that hold at HEAD

| Finding | Status | Evidence |
|---|---|---|
| **#107 / NH-14 (MEDIUM)** — dead `@silence` branch on pulse1/pulse2/triangle | **Holds** | `exporter/exporter_ca65.py:600-605,655-659,707-711`: `sta last_*_note` then `_emit_safe_beq('@silence', …)` with **no `cmp #0` re-test** — the branch tests the stale Z from `cmp last_*_note` (already known ≠0), so `@silence` (`:629,683,735`) is unreachable. Contrast the DPCM path (`:797-798`) which *does* re-test with `cmp #0`. Noise (`:752`) branches straight off the load and is correct. Scope = 3 procs, matching the 2026-07-05 correction. |
| **#167 / NH-25 (LOW)** — direct-export pulse control byte omits length-counter halt (`$20`) | **Holds** | `nes/envelope_processor.py:135` sets only `envelope_bits = 0x10`; direct-export writes that byte to `$4000`/`$4004` (`exporter/exporter_ca65.py:611-613,665-667`) and `ora #$08` reloads a real (short) length counter into `$4003`/`$4007` (`:625,679`). A sustained `--no-patterns` note longer than the reloaded length value is cut by hardware. |
| **#203 / NH-28 (LOW)** — `nes/mmc3_init.asm` is fully dead | **Holds** | `nes/project_builder.py:92` only *strips* a `.include "mmc3_init.asm"` line that is no longer generated; no `.include`/`.import` of the file exists anywhere. |
| **#204 / NH-29 (LOW)** — `noise_mode` has no producer | **Holds** | Only test fixtures set `noise_mode`; `nes/emulator_core.py:166` (`e.get('noise_mode', 0) & 1`) is the sole read. Plumbing is dead-but-correct end-to-end (mode bit reaches `$400E` bit 7 via `control` bit 6). |

## Summary

| Severity | Count (NEW) |
|----------|------:|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 1 |
| **Total NEW** | **1** |

Plus 6 prior findings verified **fixed** (NH-30, #41, #163, #165, #166; #164 partially) and 4
still-open findings re-verified unchanged (#107/NH-14, #167/NH-25, #203/NH-28, #204/NH-29).

### Highest-risk hardware divergence

None. The subsystem carries **no open CRITICAL/HIGH/MEDIUM** at HEAD. Every value that reaches
an APU register is clamped on its path (timers `max(8, min(t,$7FF))`, volumes `& 0x0F` / floored
at 1, noise index 0–15, duty `& 0x03`). The one new finding is a LOW doc-rot residual inside
already-dead code.

---

## Findings

### NH-31: `nes/mmc3_init.asm:63` still labels `$4017=$40` "Mode 1" — residual of the #164 comment fix, inside dead code
- **Severity**: LOW
- **Dimension**: 8 (60Hz frame timing & frame counter init)
- **Location**: `nes/mmc3_init.asm:62-63`
- **Status**: Regression of #164 (incomplete fix); dedup-linked to #203/NH-28
- **Description**: Commit `a3c021b` closed #164/NH-22 ("`$4017=$40` mislabelled mode 1") by
  correcting the comment at the two *live* init sites (`exporter/exporter_ca65.py:848`,
  `nes/audio_engine.asm:131`), but left the third copy in `nes/mmc3_init.asm:63` reading
  `STA $4017 ; Disable APU Frame Counter IRQs (Mode 1)`. The byte written is `$40`
  (`LDA #$40` at `:62`) = `%01000000`, which is **4-step mode (mode 0)** with the interrupt-
  inhibit bit set — *not* mode 1 (5-step is `$80`/`$C0`), per
  `docs/APU_FRAME_COUNTER_REFERENCE.md` §2 Register Map / §3 Sequencer Modes. The 2026-07-05
  pass had listed all three sites under #164; two are now fixed and this one is the residual.
- **Evidence**: `nes/mmc3_init.asm:62-63`; contrast the corrected live sites at
  `exporter/exporter_ca65.py:848` and `nes/audio_engine.asm:131`.
- **Impact**: None on any generated ROM — `nes/mmc3_init.asm` is never `.include`d by
  `nes/project_builder.py` (the builder at `:92` only strips a stale `.include` line), so this
  file is entirely dead code (#203/NH-28). The wrong comment is a maintenance/doc-rot hazard
  only: a future reader wiring this file back in could copy the "mode 1" description. The
  cleanest resolution is deleting the file per #203, which subsumes this.
- **Related**: #164/NH-22 (the comment fix this is a residual of), #203/NH-28 (the whole file
  is dead and slated for removal).
- **Hardware ref**: `docs/APU_FRAME_COUNTER_REFERENCE.md` §2 (Register Map — bit 7 Mode:
  0=4-step, 1=5-step) / §3 (Sequencer Modes). `$40` has bit 7 clear ⇒ 4-step ⇒ mode 0.
- **Suggested Fix**: Delete `nes/mmc3_init.asm` per #203 (preferred), or change the `:63`
  comment to "4-step mode (mode 0), disable frame IRQ" to match the two live sites.

---

## Dimension coverage notes (verified clean at HEAD, no new findings)

- **Dim 1** (Pulse): duty `(d & 0x03) << 6`, constant-volume `0x10`, 4-bit volume mask all
  correct (`nes/envelope_processor.py:132-137`). Standalone `reset` proc and `init_music`
  disable sweep (`$08` → `$4001`/`$4005`) and init `$4017=$40` / `$4015=$0F`
  (`exporter/exporter_ca65.py:463-468`). Bytecode engine's `$4003`/`$4007` phase-reset guard
  (`nes/audio_engine.asm:413`, write-hi only when changed) holds. NH-25 (halt bit) unchanged.
  Arranger pulse control `(duty<<6)|0x30|volume` sets both halt (`0x20`) and const-vol
  (`0x10`) — more complete than direct-export.
- **Dim 2** (Triangle): non-pulse core branch emits no duty/volume control byte
  (`nes/emulator_core.py:115-126`); direct-export derives `$4008` as `0x00`/`0x80|(vol*7)`
  independently (`exporter/exporter_ca65.py:343-346`); arranger writes constant `0x81`
  (`pipeline_integration.py:259`). No pulse-style volume/duty leaks into `$4008`/`$400B`.
- **Dim 3** (Noise): `get_noise_period` clamp+invert (`nes/pitch_table.py:62-75`) and
  `PitchProcessor._get_noise_period` delegation in lockstep. `NOISE_DECAY_FRAMES = 6` software
  ramp with re-trigger truncation (`nes/emulator_core.py:158-186`). Silence path writes `$30`
  (const-vol 0) to `$400C` (`exporter/exporter_ca65.py:776`). Mode bit reaches `$400E` bit 7
  but has no producer (#204/NH-29).
- **Dim 4** (DPCM): `$4011` written only to zero the DAC at the live init sites; per-song dense
  `sample_id` remap (`nes/emulator_core.py:214-235`) survives the byte ceiling;
  `@cmd_dmc_level` handler still has no producer (dead, LOW, tracked).
- **Dim 5/10** (Pitch tables / clamping): pulse `/16` vs triangle `/32` tables distinct and
  single-sourced from `NES_NOTE_TABLE`/`NES_TRIANGLE_TABLE` (`nes/pitch_table.py:51-52`), both
  `max(8, min(t,$7FF))`. **Correction to the SKILL's "inert pitch macro" assumption**: the
  bytecode serializer's pitch macro *is* a live nonzero producer for pulse notes 96–108 —
  `pitch_offset = _encode_macro_offset(pitch_val - base_timer)` (`exporter/exporter_ca65.py:1117`)
  where the serializer clamps the stream note to ≤95 (`:1075`) but `pitch_val` reflects the true
  note. The engine's `adc temp_pitch`/`adc temp_pitch_hi` add (`nes/audio_engine.asm:406-411`)
  has no post-clamp, **but is not a hardware bug**: the engine period tables are emitted from the
  same `NES_NOTE_TABLE`/`NES_TRIANGLE_TABLE` (`:1023-1027`) that `midi_note_to_timer_value` uses,
  so `engine_period[clamped_note] + (pitch_val - base_timer)` reconstructs exactly `pitch_val ∈
  [8,$7FF]` — always in range. The sign-extension guard (`:364-370`) and offset range
  (~[-30,0] for the 96–108 window, inside the signed byte) confirm no overflow. Arp macro
  remains genuinely inert (neutral offset only).
- **Dim 6** (Velocity→volume): legacy path `max(1, int(15*pow(v/127,1.5)))` on all channels
  (`nes/emulator_core.py:113,119,168`), bounded; `get_envelope_control_byte` product/15 cannot
  round to 16. Arranger pulse floor now `max(1, vel//8)` (NH-30 fixed).
- **Dim 7** (Envelope): constant-volume bit unconditionally set (`envelope_processor.py:135`);
  percussion divide-by-zero shape unreachable (no `envelope_type="percussion"` producer —
  grep-confirmed outside `tests/`).
- **Dim 8/9** (Frame counter / register window / `$4015`): `$4017=$40` + `$4015=$0F` before
  playback on both live init paths; standalone `reset` proc `lda #$40/sta $4017/lda #$0F/sta
  $4015` (`exporter/exporter_ca65.py:463-468`). Every emitted `sta $40xx` lands in `$4000–$4017`
  on the correct register. Only doc-rot residual is NH-31 (dead `mmc3_init.asm`).

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-07-06.md
```
