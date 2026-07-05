# #168 — PAT-01: Sequential detector's `positions`/`references` include non-exact variation positions — stored pattern events do not reproduce the referenced content

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-01.md

## Description
`PatternDetector.detect_patterns` merges exact-match positions and *variation* positions
(transposed / volume-scaled windows with similarity >= 0.85) into a single `positions`
list, which `compress_patterns` copies verbatim into `references`. The stored `events` are
the anchor occurrence's events, so at every variation position the referenced content is
different music — the data structure claims "pattern X occurs at position P" where it does
not. The parallel (default) detector is exact-only and does not have this defect.

## Location
`tracker/pattern_detector.py:227` and `:253`
(`all_positions = exact_matches + [var['position'] for var in variations]`), stored at
`:279-286`, propagated into `references` by `PatternCompressor.compress_patterns`
(`tracker/pattern_detector.py:752-767`); written to the `detect-patterns` JSON artifact at
`main.py:340-345`.

## Evidence
Reproduced. Motif ×3 + one transposed copy -> `EnhancedPatternDetector` returns `pattern_0`
with `positions = [0, 5, 10]` and `references['pattern_0'] = [0, 5, 10]`, but the sequence
windows at 5 and 10 contain `(41,21)`/`(42,22),(65,100)` where the stored events say
`(40,20)`/`(40,20),(60,100)`. `stats` reports `original_size = 18 (= 6 events × 3
positions)`, `compression_ratio = 66.7%` — counting the two non-exact positions as full
exact occurrences. `tests/test_pattern_integration.py:120-137` asserts positions are ints,
never that the referenced windows equal the pattern events, so no test catches this.

## Impact
No ROM byte today (`references` analysis-only, #4). Real current impact: (a)
`compression_ratio` printed by the ROM banner and the `detect-patterns` subcommand is
inflated by non-exact occurrences; (b) the `patterns.json` artifact the subcommand ships is
internally inconsistent (any future consumer reconstructing events-at-references silently
plays the base pattern where a transposition belonged); (c) `LoopManager.detect_loops`
derives loop start/end from these positions on the opt-in analysis path, so loops can
anchor on a non-repeat.

## Related
#4 (closed), #101 (closed), PAT-03, PAT-04; pipeline audit PL-03.

## Suggested Fix
Keep `positions`/`references` exact-only and carry variations separately (they already
exist under `pattern_info['variations']` with their transform), or tag each reference with
its `{transposition, volume_change}` so a consumer can reconstruct losslessly. Add a
round-trip test asserting `sequence[pos:pos+length] == pattern events` for every referenced
position.

## Completeness Checks
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **TESTS**: A regression test pins this specific fix

---

# #169 — PAT-03: `compression_ratio` measures only the patterned subset of a metrics-only analysis, yet is printed in the ROM success banner as if it described the ROM

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
