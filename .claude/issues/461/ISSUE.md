# TD-41: nes/linker_mmc3.cfg is an orphan — and a stale 128KB-era snapshot that contradicts the live 512KB config generator

- **Issue**: #461

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** NEW (long noted as "Orphan cfg" in `_audit-common.md`'s layout map, but never reported in any prior audit report nor filed as an issue — verified against all `docs/audits/*.md` and the open/closed issue list)

## Description
`grep -rn linker_mmc3` across the tree finds no reference outside audit-skill prose — no Python module, build script, or test reads it; every mapper emits `nes.cfg` programmatically via `generate_linker_config()`. It also fails the "deliberately-kept reference copy" test: it describes a **128KB** PRG layout, while `mappers/mmc3.py` generates a **512KB**, 60-swap-bank (`SWAP_BANK_COUNT = 60`, 8KB windows) configuration — so as a reference it is actively misleading.

## Evidence
```
$ head -2 nes/linker_mmc3.cfg
# MMC3 Linker Configuration (128KB PRG-ROM)
# Configured for PRG Mode 1 ($8000 fixed, $C000 swappable)

$ grep -n "SWAP_BANK_COUNT\|512 \* 1024" mappers/mmc3.py
mappers/mmc3.py:15:    SWAP_BANK_COUNT = 60
mappers/mmc3.py:32:        return 512 * 1024  # 512KB PRG-ROM

$ grep -rn "linker_mmc3" --include='*.py' --include='*.sh' --include='*.cfg' .
(no matches outside audit-skill docs)
```
Zero code references.

## Impact
A newcomer editing linker behavior may edit this file and see no effect, or trust its 128KB layout. Developer-confusion blast radius only.

## Suggested Fix
Delete it (git history preserves it). If kept intentionally, fix its header to match the generated 512KB layout and add a comment stating it is a non-authoritative reference copy — but deletion is the better fit given it has already gone stale once.

## Related
NH-28/#203 (`nes/mmc3_init.asm`, the same orphaned-file class, since deleted); `.claude/commands/_audit-common.md:34`.

## Completeness Checks
- [ ] **DOC**: If kept rather than deleted, its header comment is corrected to match the live 512KB/60-bank layout `mappers/mmc3.py` generates
