# ARR-2026-08-06-1: GM_INSTRUMENT_MAP's curated channel is discarded by role-based override for 16/128 instruments

**Severity:** MEDIUM · **Domain:** arranger · **Source:** docs/audits/AUDIT_ARRANGER_2026-08-06.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/408

## Description
`_determine_role` seeds `preferred_channel` from `GM_INSTRUMENT_MAP`'s curated `channel`
field, but an unconditional role→channel `if/elif` chain (BASS→TRIANGLE, MELODY→PULSE1,
HARMONY→PULSE2, DECORATIVE→PULSE2) always overwrites it afterward. 16 of 128 GM programs
(e.g. Ocarina/Whistle/Blown Bottle curated for TRIANGLE, "FX 4 (atmosphere)" curated for
NOISE) never reach their curated channel.

## Location
- `arranger/role_analyzer.py:204-276` (`_determine_role`)
- `arranger/gm_instruments.py` (`GM_INSTRUMENT_MAP`)

## Impact
Audible timbre mismatch for the 16 affected GM programs — not a crash or data loss.

## Suggested Fix
Only override `preferred_channel` when musical analysis meaningfully disagrees with the
GM hint, or drop the now-decorative `channel` field from entries whose role already
implies the outcome.
