# PAT-03: `compression_ratio` measures only the patterned subset of a metrics-only analysis, yet is printed in the ROM success banner as if it described the ROM

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-01.md

## Description
`original_size = sum(len(events) * len(positions))` and
`compressed_size = sum(len(events))` are computed only over detected patterns. Frames
covered by no pattern contribute to neither side, so the ratio describes the patterned
subset, not the song ("96% reduction" can be reported when most of the song is
un-patterned). Compounding it: (a) `positions` include non-exact variation occurrences
(PAT-01) and self-overlapping matches (PAT-04), further inflating `original_size`; (b) the
number has no relationship to emitted ROM bytes (actual size reduction comes from
macro/instrument dedup in the bytecode serializer, #4), yet the success banner prints it
directly under "ROM size", presenting a detector metric as a property of the artifact.

## Location
`tracker/pattern_detector.py:773-798` (`calculate_compression_stats`); printed at `main.py:659` (ROM banner) and `main.py:347` (subcommand).

## Evidence
`calculate_compression_stats` sums only `original.values()` / `compressed.values()` (no
total-event term is ever passed in); banner at `main.py:656-660` prints ROM size then
"Compression ratio: X% reduction" from `pattern_result['stats']`. Check-run: 3 occurrences
(1 exact + 2 variations) of a 6-event pattern in a 17-event stream reported 66.7%
"reduction".

## Impact
Misleading headline number in every patterns-mode build and in CLAUDE.md-style claims
("~95.86% data reduction"); masks the fact that pattern detection currently has zero effect
on output size. Cosmetic but systematically wrong.

## Related
#17 (closed), #4 (closed), PAT-01, PAT-04, PL-03.

## Suggested Fix
Pass the total event count into `calculate_compression_stats` and report coverage-aware
numbers (e.g. `patterned_events / total_events` plus the dedup ratio), and label the banner
line "pattern-analysis metric" — or drop it from the ROM banner until references drive
bytes.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
- [ ] **TESTS**: A regression test pins this specific fix
