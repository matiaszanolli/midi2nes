# NH-28: nes/mmc3_init.asm is fully dead code — duplicate reset/NMI/IRQ/APU-init never included in any generated project

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/203
**Severity:** LOW
**Domain:** nes-hardware
**Source:** docs/audits/AUDIT_NES-HARDWARE_2026-07-03.md
**Labels:** low, nes-hardware, bug

## Description
`nes/mmc3_init.asm` defines a complete alternate reset/NMI/IRQ handler set with its own APU init sequence and `.segment "VECTORS"`. `nes/project_builder.py` never copies this file into the output directory and never emits a real `.include "mmc3_init.asm"` — it only strips a stale leftover include string. The actual reset/NMI/vectors/APU-init that ships is the inline template in `NESProjectBuilder._create_main_asm`. The file also carries the same "Mode 1" comment mislabel as NH-22/#164, but since it never reaches ca65 this is moot rather than a live third instance.

Previously miscategorized as live in `AUDIT_DPCM_2026-06-29.md`'s "Items checked and NOT reported" section (cited `nes/mmc3_init.asm:68-69` as a confirmed-correct live init site — correct in isolation, but the file is never assembled).

## Location
- `nes/mmc3_init.asm` (whole file)
- Only reference: `nes/project_builder.py:92` (stale-include strip only, never an add)

## Impact
None on shipped ROMs (dead code). Maintenance hazard: a future contributor editing APU init in this plausibly-named file would have zero effect on real builds.

## Related
#164/NH-22 (same comment mislabel, live copies), #38/NH-10 (prior dead duplicate-implementation pattern).

## Suggested Fix
Delete `nes/mmc3_init.asm`, or wire it in and fix the Mode-1 comment if intended as future alternate code path.

## Dedup
Checked against `/tmp/audit/issues_nes-hardware.json` (47 open issues) via `gh search issues` for "mmc3_init" — no matches at all, open or closed.
