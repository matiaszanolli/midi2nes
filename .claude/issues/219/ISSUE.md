# PERF-03: Pattern-detection sampling caps are hardcoded magic numbers with no config override

- **GitHub Issue**: https://github.com/matiaszanolli/midi2nes/issues/219
- **Labels**: low, performance, bug
- **Source Report**: docs/audits/AUDIT_PERFORMANCE_2026-07-03.md
  (originally reported as PERF-03 in `docs/audits/AUDIT_PERFORMANCE_2026-06-29.md`,
  never filed as a GitHub issue by a prior `/audit-publish` run — filed now.)
- **Severity**: LOW
- **Dimension**: D-sampling / config — pattern-detection thresholds
- **Location**: `tracker/pattern_detector.py:16` (`MAX_PATTERN_EVENTS = 15000`), `:23` (`DETECTOR_MAX_EVENTS = 1000`), `main.py:550` (`LARGE_FILE_THRESHOLD = 10000`, advisory-only)
- **Status filed as**: NEW (carried over from prior report, never previously filed)

## Description
Three independent hardcoded numeric caps govern pattern-detection sizing, with no
config override path:
- `MAX_PATTERN_EVENTS = 15000` — sampling cap before the O(n) parallel
  `ParallelPatternDetector`.
- `DETECTOR_MAX_EVENTS = 1000` — cap used by the O(n^2)-ish sequential
  `EnhancedPatternDetector` (`detect-patterns` subcommand + pipeline sequential
  fallback).
- `LARGE_FILE_THRESHOLD = 10000` (`main.py:550`) — advisory-only; only prints a
  warning suggesting `--no-patterns`, does not change behavior.

Checked `config/default_config.yaml:8-13` and `config/config_manager.py:16,143,261-267`:
`processing.pattern_detection.min_length`/`similarity_threshold` exist as config keys
and are validated, but none of these three constants is read from config anywhere.

## Evidence
```
tracker/pattern_detector.py:16:MAX_PATTERN_EVENTS = 15000
tracker/pattern_detector.py:23:DETECTOR_MAX_EVENTS = 1000
main.py:550:                LARGE_FILE_THRESHOLD = 10000
```
`grep -rn "PATTERN_MIN_LENGTH\|PATTERN_MAX_LENGTH\|MAX_PATTERN_EVENTS\|DETECTOR_MAX_EVENTS" main.py config/`
matches only the hardcoded definitions and their direct use sites.

## Impact
Users cannot tune pattern-detection sampling behavior without editing source.
Workaround exists (edit constants directly), so LOW — maintainability/defense-in-depth
gap, not an incorrectness issue.

## Related
Consolidated by #100/#102 (both closed) — down from four thresholds
(`FALLBACK_MAX_EVENTS` no longer exists) to the current three. No open issue matched
this finding on keyword search.

## Suggested Fix
Add `processing.pattern_detection.max_events` (sequential) and
`processing.pattern_detection.max_pattern_events` (parallel-path sampling cap) config
keys, read them in `main.py`/`tracker/pattern_detector.py` with the current hardcoded
values as defaults, and validate them alongside the existing
`min_length`/`similarity_threshold` keys in `config/config_manager.py`.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
