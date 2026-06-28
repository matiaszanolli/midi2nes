# M-3: Music data never size-checked against mapper PRG capacity on any pipeline path (silent-overrun risk)

**Severity:** CRITICAL · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
`can_fit_data` / `auto_select` / `get_data_capacity` exist but are referenced only inside `mappers/factory.py` and `mappers/base.py` — never from `main.py` or `nes/project_builder.py`. Both pipeline entry points instantiate `MMC3Mapper()` explicitly and call `prepare_project`, which writes project files with no comparison of generated music-data size to `mapper.get_data_capacity()`. Oversized music flows straight to `ld65`.

## Evidence
```
main.py:57,424        builder = NESProjectBuilder(..., mapper=MMC3Mapper())
mappers/base.py:136   get_data_capacity()     # defined
mappers/base.py:145   can_fit_data()          # defined, internal-only
mappers/factory.py:84 auto_select()           # defined, internal-only
nes/project_builder.py:74-100  prepare_project — no capacity check
```

## Impact
PRG overrun is undetected by the pipeline. Severity floor for undetected PRG overrun is CRITICAL. Relies entirely on ld65 region overflow (and with M-1 the link never reaches that stage). If M-1 fixed and ld65 overflow confirmed to error, re-score MEDIUM.

## Related
M-1, M-7.

## Suggested Fix
After music.asm/DPCM are generated, compute total size and call `mapper.can_fit_data(size)` before linking; raise a clear error naming the overflowing bank. Add a >capacity test.
