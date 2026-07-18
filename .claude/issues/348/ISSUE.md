# NH-HW-2026-07-18-1: Direct-export APU init never zeroes the DMC DAC ($4011)
**Filed as:** #348

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-18.md

## Description
`docs/APU_DMC_REFERENCE.md` §5 "Silence Initialization" states the engine init routine should write `$00` to `$4011` so the DPCM counter starts at 0 and doesn't accidentally muffle the other channels (the non-linear mixer means a nonzero DMC output level inversely attenuates Triangle/Noise). The bytecode/pattern engine performs this init (`nes/audio_engine.asm:128`, `sta $4011`). The **direct-export** path emitted by `export_direct_frames` (`--no-patterns`) — both the standalone `reset` proc and the project-builder-facing `init_music` (`exporter/exporter_ca65.py:848-860`, `:445-486`) — initializes `$4015`, `$4017`, and the sweep units but **omits the `$00 → $4011` DAC-zero**, even though the same path emits `play_dpcm` and can trigger DPCM samples. On power-on the DMC DAC is already 0, so there is no defect on a fresh boot; the gap manifests only on a soft reset (the DAC retains its prior level), where Triangle/Noise can come back muffled.

## Evidence
```
$ grep -n 'sta \$4011' nes/audio_engine.asm exporter/exporter_ca65.py
nes/audio_engine.asm:128:    sta $4011          # bytecode engine: DAC zeroed
# exporter_ca65.py: no match — neither reset nor init_music zeroes $4011
```
`init_music` (`exporter_ca65.py:848-860`) writes `$4017`, `$4015`, `$4001`/`$4005`, `frame_counter` — no `$4011`. Standalone `reset` likewise.

## Impact
`--no-patterns` (direct-export) ROMs only. No audible defect on power-on (DAC = 0); on soft reset the un-zeroed DMC output level can DC-offset the mixer and attenuate Triangle/Noise. Defense-in-depth / consistency gap between the two export engines, not a wrong-on-every-ROM divergence. The default (pattern/MMC3) path is unaffected.

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §5 "Silence Initialization" and "Non-linear Mixer Trick" (`$4011` DAC starts at 0 for safety; nonzero level muffles Triangle/Noise).

## Related
#203/NH-28 (`nes/mmc3_init.asm` is dead code — it *does* zero `$4011` but is never included in any generated project, so it does not cover this path).

## Suggested Fix
Add `lda #$00` / `sta $4011` to `init_music` (and the standalone `reset` APU-init block) in `exporter/exporter_ca65.py`, mirroring `nes/audio_engine.asm:128`, so both export engines satisfy the doc's silence-init mandate.

## Completeness Checks
- [ ] **CHANNEL**: the DMC DAC zero does not disturb the Triangle/Noise init already present
- [ ] **SIBLING**: both the standalone `reset` proc and `init_music` get the `$4011` zero
- [ ] **CC65**: the added init assembles and links on the direct-export (`--no-patterns`) path
- [ ] **TESTS**: a test asserts the direct-export init emits `sta $4011`
- [ ] **DOC**: `docs/APU_DMC_REFERENCE.md` §5 remains accurate for both engines after the fix