# NH-HW-04: Triangle linear-counter reload uses an undocumented `volume * 7` magic constant

**Issue:** #364
**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES-HARDWARE_2026-07-19.md
**Labels:** low, nes-hardware, enhancement
**Dimension:** 2 (Triangle — linear counter)
**Location:** `exporter/exporter_ca65.py:343-346`
**Status (as filed):** NEW / CONFIRMED

## Description
The direct-export triangle control byte is `0x80 | (volume * 7)` when `volume != 0`, else `0x00`. `volume` is the 4-bit (0–15) `velocity_to_volume` output, so the low 7 bits become `0..105` — a linear-counter *reload* value derived from loudness. Because bit 7 (the linear counter control/halt flag) is set, the reload value is continuously re-armed and never gates the note, so the `* 7` scaling is functionally inert and correct (triangle plays on/off). But the constant `7` has no doc citation and the intent is opaque; a future edit that clears bit 7 would suddenly make this an audible, wrong note-length knob.

## Evidence
- `control = 0x80 | (volume * 7)` at `exporter/exporter_ca65.py:346`; `volume` originates from `velocity_to_volume` (0–15) via `compile_channel_to_frames`'s non-pulse branch.
- Contrast the bytecode engine, which writes a fixed `$FF` reload (`nes/audio_engine.asm:466`).

## Impact
None today (inert). Maintainability / latent-trap risk only; a divergence from the bytecode engine's fixed-reload approach.

## Hardware ref
`docs/APU_TRIANGLE_REFERENCE.md` §4 (linear counter reload), §1 (no volume control).

## Related
NH-HW-02 (both concern control-byte constants); the bytecode engine's `$FF` reload at `nes/audio_engine.asm:466`.

## Suggested Fix
Replace with a named constant (e.g. a fixed max reload `0x7F`, or `0x80 | LINEAR_COUNTER_MAX`) and cite `docs/APU_TRIANGLE_REFERENCE.md` §4; the loudness scaling is meaningless for a channel with no volume.
