# F-07: compression_ratio is a percentage but printed as …x

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #17

## Description
calculate_compression_stats computes compression_ratio = ((original - compressed)/original) * 100 (pattern_detector.py:748) — a percentage reduction in [0,100]. The banner prints "Compression ratio: {…:.2f}x" (main.py:484). A 96% reduction shows as "95.86x", the figure CLAUDE.md cites as a multiplier.

## Evidence
Formula pattern_detector.py:748; x suffix main.py:484.

## Impact
Cosmetic but misleading; documented "95.86x" is actually ~96% reduction (≈25x). Display-only → LOW.

## Related
F-01

## Suggested Fix
Print {ratio:.1f}% reduction, or convert to a true multiplier original/compressed and label x.

**Location:** `tracker/pattern_detector.py:746-754`; printed `main.py:157,484`
