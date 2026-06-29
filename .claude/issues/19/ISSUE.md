# F-08: Pattern-detector parameter divergence between default and step-by-step

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md

## Description
Default path runs ParallelPatternDetector(..., max_pattern_length=12) (main.py:316) and EnhancedPatternDetector(..., max_pattern_length=12) in fallback (main.py:322); run_detect_patterns runs EnhancedPatternDetector(tempo_map, min_pattern_length=3) with NO max_pattern_length (main.py:130). Different params produce different patterns/references.

## Suggested Fix
Factor pattern-detection parameters into one shared constant/helper used by both entry points.
