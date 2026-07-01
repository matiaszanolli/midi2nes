# REG-07: No dedicated mapper tests — MapperFactory size-based auto-select (51%) and header/nes.cfg consistency unverified

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

## Description
Mappers are only exercised indirectly through `test_ca65_export.py`. `MapperFactory`'s auto-select-by-data-size logic and each mapper's `header`/`linker_config`/`capacity` outputs are untested in isolation. Per `_audit-severity.md`, a mapper-header vs `nes.cfg` mismatch is HIGH — there is no test asserting the iNES header byte (mapper number) matches the `nes.cfg` the same mapper emits.

## Evidence
`grep -rln MapperFactory tests/` → only `test_ca65_export.py` (no isolated mapper test). `mappers/factory.py` 51%, `mappers/base.py` 54%, `mappers/nrom.py` 64%. No `tests/test_mappers.py` exists.

## Impact
A wrong auto-selected mapper or a header/linker drift (HIGH severity) would ship unguarded. PRG-capacity-overrun detection (a CRITICAL row) is also untested at the mapper layer.

## Suggested Fix
Add `tests/test_mappers.py`:
1. **Auto-select**: feed `MapperFactory` data sizes crossing each capacity threshold; assert the expected mapper (NROM→MMC1→MMC3) is chosen.
2. **Header↔cfg consistency**: for each mapper assert the iNES header's mapper nibble equals the mapper number its `nes.cfg`/linker config targets.
3. **Capacity overrun**: assert data exceeding a mapper's PRG capacity is detected (raises or escalates), not silently truncated.

## Completeness Checks
- [ ] **RANGE**: Capacity-overrun path raises/escalates rather than silently truncating
- [ ] **CONTRACT**: iNES header mapper nibble == nes.cfg/linker config mapper number (asserted)
- [ ] **SIBLING**: All mappers (NROM, MMC1, MMC3) covered by the consistency assertion
- [ ] **TESTS**: `tests/test_mappers.py` pins auto-select, header/cfg, and overrun
- [ ] **DOC**: If behavior contradicted `docs/MAPPER_MMC1_REFERENCE.md` / `docs/MAPPER_MMC3_REFERENCE.md`, the doc was corrected
