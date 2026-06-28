# M-7: Conflicting default-mapper behaviors — get_mapper(auto,0)→MMC1, builder default auto, pipeline hardcodes MMC3

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
`get_mapper("auto", data_size=0)` returns MMC1 "for backwards compatibility". `NESProjectBuilder.__init__` defaults `mapper_name="auto"`, so a caller that constructs the builder without a mapper and without `auto_select_mapper(size)` gets MMC1 — whose build path is broken by M-5 and whose music.asm segments differ. The actual pipeline always passes `MMC3Mapper()`. Real behavioral trap.

## Evidence
```
factory.py:173-175    if data_size <= 0: return MapperFactory.get_mapper("mmc1")
project_builder.py:30 mapper_name: str = "auto"
main.py:57,424        builder = NESProjectBuilder(..., mapper=MMC3Mapper())
```

## Impact
Inconsistent default; builder used outside main.py silently selects a mapper the pipeline does not build for. MEDIUM.

## Related
M-5, M-8.

## Suggested Fix
Resolve builder `"auto"` via `auto_select(data_size)`, or default builder to MMC3. Pick one canonical default and document it.
