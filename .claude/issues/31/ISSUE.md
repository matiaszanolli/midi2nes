# NH-07: Sweep units ($4001/$4005) never disabled at init — stale sweep can bend pitch

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #31

## Description
`APU_PULSE1_SWEEP=0x4001` / `APU_PULSE2_SWEEP=0x4005` are defined but never written, including in init. Init writes only `$4015`, `$4017`, `$4015`. Sweep power-on state is not guaranteed disabled; a stale enabled sweep continuously bends pitch (and overflow can silence). Correct init must zero `$4001`/`$4005`.

## Evidence
Reset proc writes only $4015/$4017/$4015 (exporter_ca65.py:213-219); `grep -c "sta $4001|sta $4005"` = 0. `init_music` (541, 969) omits it too.

## Impact
Uncontrolled pitch bend / silencing on pulse channels depending on power-on garbage; intermittent wrong pitch.

## Hardware ref
`docs/APU_PULSE_REFERENCE.md` §1, §2, §5 cond. 2.

## Related
NH-09.

## Suggested Fix
Add `lda #$08 / sta $4001 / sta $4005` (sweep disabled, valid shift) to both init paths.
