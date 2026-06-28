# F-08: Pattern-detector parameter divergence between default and step-by-step

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #19

## Description
Default path runs ParallelPatternDetector(..., max_pattern_length=12) (main.py:316) and EnhancedPatternDetector(..., max_pattern_length=12) in fallback (322); run_detect_patterns runs EnhancedPatternDetector(tempo_map, min_pattern_length=3) with no max_pattern_length (130). Different detector classes and length bounds → different patterns/references for the same input.

## Evidence
main.py:130 vs 316/322.

## Impact
Step-by-step detect-patterns output differs from default. Byte impact small today (exporter ignores references), but JSON artifacts diverge; if F-01 is fixed this becomes a playback divergence.

## Related
F-01, F-06

## Suggested Fix
Factor pattern-detection parameters into one shared constant/helper used by both entry points.

**Location:** `main.py:316,322` vs `main.py:130`
