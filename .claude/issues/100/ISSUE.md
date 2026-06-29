# P-01: EnhancedPatternDetector hard-truncates to first 1000 events, defeating the shared 15000-event sampling and understating the loss

**Severity:** HIGH · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-06-29.md

## Description
Issues #21 (F-09) and #10 (F-04) were fixed by routing every entry point through `sample_events_for_detection` (uniform `np.linspace` to `MAX_PATTERN_EVENTS = 15000`) and emitting a "ROM is INCOMPLETE" warning. But `PatternDetector.detect_patterns` — the shared base reached by **every** `EnhancedPatternDetector` path (the `detect-patterns` subcommand, the pipeline's sequential fallback, and `parser_fast`) — still does an internal, *unconditional* `sequence = sequence[:MAX_EVENTS]` with `MAX_EVENTS = 1000`. This is a **head cut**, not a uniform sample, so the back half of the song is dropped. The 15000-event shared sampling is therefore a no-op for `EnhancedPatternDetector` (1000 < 15000), and the pipeline's `pattern_loss_warning` reports a fallback figure (2,000) while the detector actually keeps only the first 1,000 — the warning understates the true loss.

## Location
`tracker/pattern_detector.py:142-147` (verified: `MAX_EVENTS = 1000`; `sequence = sequence[:MAX_EVENTS]`); pipeline fallback `main.py:485-494` (`FALLBACK_MAX_EVENTS = 2000`); subcommand `main.py:295-304`.

## Evidence
```python
# tracker/pattern_detector.py:143-147
MAX_EVENTS = 1000  # Limit to prevent excessive processing time
if len(sequence) > MAX_EVENTS:
    print(f"Warning: Large sequence ({len(sequence)} events), limiting to {MAX_EVENTS} for performance")
    sequence = sequence[:MAX_EVENTS]
    events = events[:MAX_EVENTS]
```
Reproduced: feeding 2000 events prints `limiting to 1000`; the max sequence index covered by any detected pattern is 996 — indices 1000–1999 are entirely absent. The pipeline samples to `FALLBACK_MAX_EVENTS = 2000` then the detector re-cuts to 1000.

## Impact
For any track/song with >1000 detection events, pattern detection (and loop detection that feeds off it) sees only the head. On the default macro path the frames are still exported in full (so the ROM is not truncated today, because `patterns` is only a boolean switch — #4), but (a) compression quality silently collapses on long songs, (b) the user-facing INCOMPLETE warning is numerically wrong, and (c) once anyone wires `references`→bytes this becomes silent song loss. Blast radius: every long MIDI, all three `EnhancedPatternDetector` callers.

## Related
#21 (F-09, closed), #10 (F-04, closed), #46 (REG-06), P-04, P-05.

## Suggested Fix
Replace the bare `sequence[:1000]` head-cut with the shared `sample_events_for_detection` (uniform) and a single, accurate limit; or raise it to match the 15000 policy. Make the pipeline's `pattern_loss_warning` print the detector's *actual* retained count, not the pre-detector sample size.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **SIBLING**: Same pattern checked in related files (other detectors, parser_fast)
- [ ] **TESTS**: A regression test pins this specific fix (>1000-event sampling is uniform, warning count is accurate)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
