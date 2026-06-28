# F-09: Asymmetric large-file handling — default path samples/truncates, step-by-step processes the full set unbounded

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #21

## Description
Default path silently down-samples to 15000 events inside ParallelPatternDetector (np.linspace, pattern_detector_parallel.py:51-57) and truncates to 2000 in fallback (F-04, main.py:324-326). run_detect_patterns uses EnhancedPatternDetector on the full event set with no threshold and no fallback (main.py:125-147). A large file the default path survives via sampling may hang or OOM under bare detect-patterns.

## Evidence
pattern_detector_parallel.py:51 MAX_EVENTS = 15000; main.py:130 no size guard.

## Impact
Inconsistent robustness; the "debugging" subcommand is least robust on large inputs a user would debug. Silent sampling at 15000 is an undocumented lossy step.

## Related
F-04

## Suggested Fix
Share one large-file policy across both entry points; make sampling/truncation explicit and warned, or honor --no-patterns consistently.

**Location:** `tracker/pattern_detector_parallel.py:50-58`; `main.py:324-326`; `main.py:125-147`
