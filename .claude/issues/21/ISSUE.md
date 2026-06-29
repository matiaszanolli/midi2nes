# F-09: Asymmetric large-file handling — default path samples/truncates, step-by-step processes the full set unbounded

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md

## Description
Default path silently down-samples to 15000 events inside ParallelPatternDetector (np.linspace, pattern_detector_parallel.py:51-57) and truncates to 2000 in the fallback (main.py:324-326). run_detect_patterns uses EnhancedPatternDetector on the full event set with no threshold and no fallback (main.py:125-147). A large file the default path survives via sampling may hang/OOM under the bare detect-patterns subcommand.

## Suggested Fix
Share one large-file policy across both entry points; make sampling/truncation explicit and warned.
