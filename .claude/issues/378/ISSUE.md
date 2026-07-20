# PIPE-2026-07-19-2: Sequential-fallback sampling omits the (lossy) coverage suffix

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-19.md

## Description
When parallel detection raises and the sequential fallback fires, the events are pre-sampled to `max_events` at `main.py:930` before being passed to `EnhancedPatternDetector.detect_patterns`, which re-runs `sample_events_for_detection` internally (`tracker/pattern_detector.py:211`). Because the list is already at the cap, the detector's own `self.was_sampled` stays `False`. The subsequent `if detector.was_sampled:` check (`main.py:941`) therefore leaves `coverage_lossy_note` empty, so the success banner's "Pattern coverage" line is printed *without* the "(lossy — measured over the sampled subset)" qualifier even though the coverage number genuinely was computed over a sampled subset.

## Evidence
- `main.py:930` — `events, was_sampled = sample_events_for_detection(events, max_events)` sets a **local** `was_sampled` that drives `pattern_loss_warning` (`main.py:931-938`).
- `main.py:941` — the coverage suffix keys off `detector.was_sampled`, a *different* flag reflecting only the detector's internal (now no-op) sampling.
- `tracker/pattern_detector.py:211` — the detector re-samples but, given an already-capped list, `self.was_sampled` remains `False` (initialized `False` at line 172).

## Impact
Cosmetic. The prominent `pattern_loss_warning` ("compression stats are approximate; ROM content is unaffected") still prints, so the user is not misled about ROM integrity — only the coverage line's parenthetical is missing. No effect on ROM bytes.

## Related
#312/PAT-11 (coverage labeling); #176/PL-03.

## Suggested Fix
Drive `coverage_lossy_note` off the local `was_sampled` (OR it with `detector.was_sampled`) in the fallback branch, mirroring how `pattern_loss_warning` is set.

## Completeness Checks
- [ ] **FALLBACK**: The `EnhancedPatternDetector` fallback still fires and now reports the lossy coverage suffix correctly
- [ ] **TESTS**: A regression test pins the coverage-suffix presence when the fallback samples
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
