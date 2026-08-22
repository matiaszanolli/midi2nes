# ARR-2026-08-21-5: Contract/allocator tests skip the documented floor/clamp and fallback edge cases

**GitHub Issue:** #452
**Source Report:** docs/audits/AUDIT_ARRANGER_2026-08-21.md
**Severity:** LOW · **Domain:** arranger
**Filed:** 2026-08-21

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-08-21.md

## Description
The suites added for #84/#87 cover the happy paths well (81/81 pass) but none of the edge cases the fixes exist for:
- No test drives a **period-0** noise hit through `arrange_for_nes`'s `max(1, period & 0x0F)` floor via the *contract* test (only the hi-hat rendering test touches it indirectly), and no test hits the noise **volume floor** (`max(1, min(15, v))`) with volume 0, nor DPCM `note` at the exporter-relevant 95 boundary.
- `DPCM_SAMPLE_SLOTS`' slot-2 fallback (`.get(mapping.name, 2)`) and `_allocate_noise`'s no-curated-period fallback (`noise_period = 5`) are untested — and that `5` is a **separate literal** from `get_drum_mapping`'s own "Unknown Drum" default `5` (`arranger/gm_instruments.py:1322`); nothing pins the two in sync, so a change to either silently diverges the fallback sound.

## Location
`tests/test_arranger_frame_contract.py`, `tests/test_voice_allocator.py`

## Evidence
Test inventories read in full (`grep -n "def test"` both files; contract file read whole). `tests/test_arranger_frame_contract.py:31-86` asserts key sets and two value cases only.

## Impact
The floors/fallbacks guarding the rest-sentinel and unknown-drum contracts can regress without any test failing. Working code today — LOW (missing coverage on a working path).

## Related
#253 (period-0 sentinel decision), #268/NH-30 (volume floor), skill-doc verify items.

## Suggested Fix
Add parametrized edge-case tests (period 0, volume 0, slot-2 drum if `GM_DRUM_MAP` ever grows a third `use_sample` entry — assertable today by monkeypatching a mapping — and the literal-5 fallback), and have one of them assert `_allocate_noise`'s fallback equals `get_drum_mapping(<unmapped>).noise_period` so the two literals cannot drift apart.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
