# M-10: CLAUDE.md/README still describe MMC1 as the always-on mapper — contradicts MMC3 pipeline default

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
`CLAUDE.md:31` correctly says the pipeline defaults to MMC3, but "ROM Structure" (`:194-196`) and Project Status (`:266`) still assert MMC1/128KB. README leads with the MMC3 engine (consistent); drift is localized to CLAUDE.md lower sections.

## Evidence
```
grep -niE "always use mmc1|128KB|MMC1 ROM" CLAUDE.md  -> lines 194/196/266
```

## Impact
Misleads contributors about the active mapper/ROM size. LOW.

## Related
M-7.

## Suggested Fix
Update CLAUDE.md "ROM Structure" and "Project Status" to MMC3 / 512KB, or qualify as "MMC3 default; MMC1/NROM selectable".
