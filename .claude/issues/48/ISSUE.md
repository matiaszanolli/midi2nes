# REG-08: Legacy multi-track channel-allocation heuristic untested (track_mapper.py 206-240)

**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

GitHub: https://github.com/matiaszanolli/midi2nes/issues/48
Labels: low, regression, enhancement

## Description
test_track_mapper.py covers single-track pitch-split (chord/arpeggio/grouping) but not the multi-track else branch ranking by average_pitch: melody→pulse1, harmony→pulse2 (arpeggio fallback), bass→triangle, drums→noise/dpcm. Default multi-track allocation unverified.

## Evidence
tracker/track_mapper.py ~206-240 multi-track branch; test_track_mapper.py has no multi-track allocation test.

## Impact
Regression in default multi-track voice assignment (e.g. bass to pulse) ships green for the most common MIDI shape.

## Suggested Fix
Add test feeding test_midi/multiple_tracks.mid: assert highest-avg-pitch→pulse1, lowest→triangle, drum-named→noise.
