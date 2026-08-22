# PAT-2026-08-21-2: `parse_midi_to_frames_with_analysis` feeds sampled-space pattern positions to loop detection over the full event list

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-08-21.md
**GitHub Issue:** #436

## Location
`tracker/parser_fast.py:213-239`; interacts with `tracker/pattern_detector.py:219-222` (internal
sampling) and `tracker/loop_manager.py:138-139` (per-event tempo read)

## Description
`parse_midi_to_frames_with_analysis` runs `pattern_detector.detect_patterns(note_on_events)` and
then `loop_manager.detect_loops(note_on_events, pattern_data['patterns'])` with the **full**
`note_on_events` list. But `EnhancedPatternDetector` (constructed here with the default
`max_events=DETECTOR_MAX_EVENTS=1000`) uniformly samples any larger input internally
(`pattern_detector.py:219-222`), so every persisted `positions` value is an index into the
**sampled** sequence. For a track with more than 1000 note-ons, the loop points land at
sampled-space indices while `EnhancedLoopManager.detect_loops` dereferences them against the full
list — `events[loop_info['start']]['tempo']` reads a completely different event's tempo. The
detector even exposes `was_sampled` for exactly this labeling purpose (#312/PAT-11), and this
caller ignores it. `tracker/parser.py:84-100` (the production-dead full parser, #346/TD-26) has
the same shape.

## Evidence
Call chain: `parser_fast.py:222` (`detect_patterns(note_on_events)`) → `pattern_detector.py:219-222`
(sampling when `len > max_events`) → positions persisted in sampled index space →
`parser_fast.py:225-227` (`detect_loops(note_on_events, pattern_data['patterns'])`) →
`loop_manager.py:138-139` (full-list indexing with sampled-space indices).

## Impact
Latent — off the default pipeline (only `run_full_pipeline` → `parse_midi_to_frames` is live;
callers of the `_with_analysis` variant are tests and its own `__main__` block, all with small
inputs today). Any future/external caller handing it a real-sized MIDI track (>1000 note-ons is
common) gets loop metadata whose `start`/`end`/`tempo_state` silently mean something different
than the events they accompany.

## Related
#97 (path documented-and-kept), #346/TD-26, #312/PAT-11 (the `was_sampled` flag this caller
ignores), #345/TEMPO-16 (the loop manager's tempo read this misalignment now feeds wrong indices
into), PAT-2026-08-21-3 (sibling finding, same report).

## Suggested Fix
In `parse_midi_to_frames_with_analysis`, either construct the detector with
`max_events=len(note_on_events)` (no sampling; this path is explicitly the "expensive analysis"
variant), or check `pattern_detector.was_sampled` after detection and skip/flag loop detection
when positions are not in full-event space.
