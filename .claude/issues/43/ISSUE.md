# NH-12: Doc-rot — export_direct_frames header comments / CLAUDE.md conflict with MMC3 default

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #43

## Description
`CLAUDE.md`'s "ROM Structure" still says "Always use MMC1 mapper configuration / PRG-ROM 128KB", while the live pipeline uses MMC3 and `_audit-common.md` documents MMC3 as the default. The exporter header comments perpetuate the stale MMC1 claim. Pure documentation drift (functional mismatch is NH-09).

## Evidence
`CLAUDE.md:194,196,266`; `_audit-common.md` "prepare → default mapper MMC3"; exporter comments at exporter_ca65.py:72-74.

## Impact
Misleads contributors about the mapper in use.

## Hardware ref
`docs/MAPPER_MMC3_REFERENCE.md`.

## Related
NH-09.

## Suggested Fix
Update `CLAUDE.md` ROM Structure and the exporter header comments to MMC3.
