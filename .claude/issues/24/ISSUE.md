# NH-05: DMC level command has a consumer but no producer; level not 7-bit clamped

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #24

## Description
The bytecode exporter reads `frame_data.get('dmc_level')` and emits `CMD_DMC_LEVEL ($87, level)`, but `dmc_level` is only ever read — no stage writes it. The recent "DMC level handling" commit is dead on the live path. Also, the emitted byte is not clamped to the 7-bit `$4011` range (0–127); ≥128 sets bit 7, ≥256 breaks `:02X`.

## Evidence
`dmc_level = frame_data.get('dmc_level')` (exporter_ca65.py:774); emit with no `&0x7F` (line 939). `grep -rn dmc_level` shows reads only in exporter_ca65.py (774,783-785,826,910,938-939); no producer in nes/emulator_core.py:96-103.

## Impact
DMC direct-level control non-functional (dead); can emit out-of-range `$4011`. Compounds NH-01.

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §2–§3.

## Related
NH-01.

## Suggested Fix
Produce `dmc_level` in the dpcm frame path (or remove the dead consumer), and clamp to `level & 0x7F`.
