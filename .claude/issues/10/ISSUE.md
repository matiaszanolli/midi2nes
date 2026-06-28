# F-04: Pattern-detector fallback truncates events to 2000 with no warning of incomplete output → silent song loss

**Severity:** CRITICAL · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #10

## Description
If ParallelPatternDetector.detect_patterns raises, the except Exception fallback builds EnhancedPatternDetector and for len(events)>2000 does events = events[:2000] (line 326). Remaining frames discarded. Today the exporter reads frames not events (F-01) so truncation corrupts only the dead ca65_references table, but the message is framed as perf, and a maintainer wiring references→bytes ships only the first 2000 events.

## Evidence
main.py:324-327. Print at 325 frames it as perf; no "output incomplete" notice; SUCCESS banner unconditional.

## Impact
Data loss changing the song once compression is functional (F-01); today corrupts the dead reference table. Reachability depends on the parallel detector raising (F-09 also silently samples). Large MIDI files risk truncated ROMs reported as success.

## Related
F-01, F-09

## Suggested Fix
Do not truncate silently. Keep all events (accept slowness) or abort with "file too large; re-run with --no-patterns". If kept, print a prominent WARNING reflected in the success banner.

**Location:** `main.py:319-327`
