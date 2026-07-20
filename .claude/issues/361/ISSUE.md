# MAP-2026-07-19-1: --mapper auto overstates MMC3 direct-export (--no-patterns) capacity by ~85x

Issue: #361
Labels: medium, mappers, bug

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-19.md

## Description
For a direct (`--no-patterns`) export, MMC3 does **not** bank-pack frame tables (`direct_export_bank_size()` returns `None`, inherited from `BaseMapper`), so `export_direct_frames` emits everything into `RODATA`, which loads into the 8 KB fixed bank `PRG_FIX`. MMC3's *real* direct-export budget is therefore `PRG_FIX_SIZE − FIXED_BANK_ENGINE_RESERVE = 6,138` bytes (`mappers/mmc3.py:179-202`) — smaller than NROM's 30 KB and MMC1's 112 KB. But `auto_select` ranks mappers by the flat `get_data_capacity` (NROM 30 KB < MMC1 112 KB < **MMC3 522,240 B**), i.e. exactly backwards from real direct-export capacity. Consequently MMC3 is auto-picked only when the estimated direct size is >112 KB (too big for MMC1), and in that entire window the MMC3 direct pre-flight (`validate_segment_sizes`) always rejects it. Net effect: `--mapper auto --no-patterns` can never actually produce an MMC3 direct ROM; in the 112 KB–510 KB window `auto` "selects" MMC3 and the very next step declares MMC3 too small.

## Location
`mappers/factory.py:83-114` (`auto_select` uses `can_fit_data` → `get_data_capacity`); `mappers/base.py:162-181` (flat `get_data_capacity`); `mappers/mmc3.py:31-36` (`prg_rom_size` 512 KB, no `direct_export_bank_size` override → inherits `None`); reached from `main.py:604-606` and `main.py:1003-1005` (`estimate_direct_export_size` → `MapperFactory.auto_select`).

## Evidence
```
$ python3 -c "from mappers.factory import MapperFactory as F; m=F.auto_select(200*1024); \
    print(m.name, m.get_data_capacity()); print(m.validate_segment_sizes({'RODATA':200*1024}))"
MMC3 522240
['fixed-bank data (204,800 bytes of CODE+RODATA) exceeds the MMC3 PRG_FIX budget
 (~6,138 bytes). The direct (--no-patterns) export packs frame tables into the 8 KB
 fixed bank — enable pattern compression or shorten the song.']
```

## Impact
`--mapper auto --no-patterns` on any song whose direct frame tables estimate between ~112 KB and ~510 KB. Blast radius is the CLI auto-selection UX only — the capacity pre-flight (Dimension 4) always fires before `ld65`, so **no broken ROM ships**; the failure is a confusing "auto picked MMC3, then MMC3 is too small" message. Workaround: drop `--no-patterns` (the default MMC3 bytecode path bank-switches and does fit), or shorten the song.

## Related
Dimension 4 pre-flight (`main.py:check_mapper_capacity`) is the backstop that keeps this from becoming a silent overrun; #255 (MMC1 direct bank-packing, which MMC3 direct lacks).

## Hardware ref
`docs/MAPPER_MMC3_REFERENCE.md` §2–3 (`$E000-$FFFF` fixed last bank; only `$C000-$DFFF` swappable in Mode 1 — direct tables have no swap window and must fit the single fixed bank).

## Suggested Fix
Make `auto_select` export-mode-aware — for a direct export, rank by each mapper's real direct budget (`direct_export_bank_size()` pool for MMC1, `PRG_FIX` budget for MMC3), or simply exclude MMC3 from direct-export auto-selection and let the pre-flight message point at pattern compression. Alternatively add a dedicated "direct capacity" method distinct from the flat `get_data_capacity`.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other mappers' direct capacity vs flat `get_data_capacity`)
- [ ] **TESTS**: A regression test pins `auto_select` picking a mapper whose direct pre-flight then accepts it
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
