# REG-04: The entire --arranger front-end has zero test coverage (no test references it)

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

GitHub: https://github.com/matiaszanolli/midi2nes/issues/44
Labels: medium, regression, enhancement

## Description
`grep -rln "arrange_for_nes|--arranger|arranger" tests/` returns nothing. The arranger front-end (role analysis, GM mapping, channel allocation, arpeggiation) has no behavioral test. 56-73% coverage is incidental import/init.

## Evidence
No test imports arrange_for_nes / VoiceRoleAnalyzer / VoiceAllocator.

## Impact
Regressions in role detection, GM→channel mapping, or arpeggiation ship silently for every --arranger run.

## Suggested Fix
Add tests/test_arranger.py: role analysis on multiple_tracks.mid; arpeggiation of a 3-note chord (alternating single-note, period per docs/arpeggio.md); triangle channel-honoring invariant; contract shape match with process_all_tracks.
