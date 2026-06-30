# F-07: compression_ratio is a percentage but printed as …x
Severity: LOW · Domain: pipeline · Source: AUDIT_PIPELINE_2026-06-28.md

calculate_compression_stats computes compression_ratio = ((original-compressed)/original)*100
— a percent reduction [0,100] (tracker/pattern_detector.py:748). Banner prints
"Compression ratio: {…:.2f}x" (main.py:484) and run_detect_patterns prints {…:.2f} (main.py:157).
A 96% reduction shows as "95.86x". Fix: print {ratio:.1f}% reduction, OR convert to true
multiplier original/compressed labelled x. SIBLING both print sites; TESTS unit; DOC CLAUDE.md.
