# SAFE-2026-08-06-1: run_export's DPCM-pack block gives zero feedback when dpcm_index.json is missing

**Severity:** LOW · **Domain:** safety · **Source:** docs/audits/AUDIT_SAFETY_2026-08-06.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/411

## Description
`run_export` only checks `if dpcm_pack_warning:` (None when the index is simply missing),
unlike `run_full_pipeline` which explicitly branches on `pack_result.index_found`. A song
with percussion silently loses its drums in the exported ASM with no warning at all when
`export` runs somewhere `dpcm_index.json` doesn't exist. Survived the #380 dedup fix,
which deliberately kept presentation logic at each call site.

## Location
- `main.py:709-720` (`run_export`) vs. `main.py:1097-1109` (`run_full_pipeline`)

## Impact
Messaging-only LOW; ROM/ASM byte content unaffected either way.

## Suggested Fix
Add the same `if not pack_result.index_found:` info-line branch to `run_export`.
