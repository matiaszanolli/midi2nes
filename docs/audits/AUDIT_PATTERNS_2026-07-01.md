# Pattern Detection & Compression Audit — 2026-07-01

Audit of the pattern-detection and compression subsystem per
`.claude/commands/audit-patterns/SKILL.md`, at HEAD `2bcb780` ("refactor: remove dead
code and consolidate pattern detection logic"). Severity floors from
`.claude/commands/_audit-severity.md`. Dedup against the corrected
`/tmp/audit/issues.json` (125 issues, open+closed — note: the initially pre-fetched
copy contained another repository's issues and was discarded/replaced) and all prior
reports in `docs/audits/`, including today's `docs/audits/AUDIT_PIPELINE_2026-07-01.md`.

Extra scrutiny was given to commit `2bcb780` and its two predecessors (`d8661c6`
#103/#104, `5a4b032` #114) per the audit request — see "Recent-commit verification"
below. All 87 pattern-related tests pass (`test_patterns.py`, `test_compression.py`,
`test_compression_integration.py`, `test_pattern_integration.py`,
`test_enhanced_loop_patterns.py`, `test_pattern_detector_parallel.py`,
`test_loop_manager.py`).

## Summary

**Round-trip result: MOSTLY LOSSLESS — one non-exact-reference defect found on the
sequential path.** I ran real compress → decompress / occurrence-diff checks, not
docstring reading:

- `exporter/compression.py` `CompressionEngine`: **lossless on all 8 test cases**
  (RLE runs, delta runs, the absent-key/zero-diff case the SKILL flags, mixed
  raw/RLE/delta, empty-silence events, `sample_id` deltas, and a 200-event random
  fuzz) — frame-by-frame `==` on every case.
- `ParallelPatternDetector` (the **default** pipeline path): every referenced
  position is an **exact** repeat of the stored pattern events (0 mismatches on a
  3000-event run), results are deterministic across runs, and the in-process serial
  fallback produces the **identical** pattern set (post-#46/#114 fixes hold).
- `EnhancedPatternDetector` (sequential fallback + `detect-patterns` subcommand):
  **FAILS the exact-repeat property** — `positions`/`references` mix in ≥85%-similar
  *variation* positions whose actual content differs from the stored pattern events
  (reproduced: pattern events `(40,20),(60,100)` referenced at a position containing
  `(41,21),(60,100)`). Because `references` are analysis-only (#4 closed, verified:
  `main.py` passes `{}` to the exporter and `export_tables_with_patterns` never reads
  them), **no ROM byte is affected today**, so this is MEDIUM (PAT-01), not CRITICAL —
  but it is the exact latent shape of the CRITICAL round-trip bug the moment anyone
  wires references→bytes, and it inflates the reported `compression_ratio` now.

### Finding counts
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 4 (one of them, PAT-02, deduped to today's pipeline audit PL-03)
- LOW: 3

### 3 highest-leverage fixes
1. **PAT-01** — Separate exact matches from variations in `positions`/`references`
   (or tag variation refs with their transposition/volume transform). Today's
   structure silently asserts "this pattern occurs here" at positions where it does
   not.
2. **PAT-04** — Fix the off-by-anchor scan in `_find_pattern_matches`
   (`pos = start_pos + 1` should be `start_pos + pattern_len`): the sequential
   detector emits self-overlapping "non-overlapping" matches (e.g. `[0, 1, 5]` for a
   length-4 pattern), inflating occurrence counts, scores and stats, and diverging
   from the parallel matcher's correct greedy.
3. **PAT-03** — Stop printing the detector's `compression_ratio` in the ROM success
   banner as if it described the ROM: it measures only the patterned subset of a
   metrics-only analysis and has no relationship to the emitted bytes (macro/bytecode
   dedup drives actual size, #4).

---

## Findings

### PAT-01: Sequential detector's `positions`/`references` include non-exact variation positions — stored pattern events do not reproduce the referenced content
- **Severity**: MEDIUM (escalates to CRITICAL if `references` ever drive output bytes)
- **Dimension**: 1 (Round-Trip Integrity) / 3 (Reference Offsets)
- **Location**: `tracker/pattern_detector.py:227` and `:253`
  (`all_positions = exact_matches + [var['position'] for var in variations]`),
  stored at `:279-286`, propagated into `references` by
  `PatternCompressor.compress_patterns` (`tracker/pattern_detector.py:752-767`);
  written to the `detect-patterns` JSON artifact at `main.py:340-345`
- **Status**: NEW (the 2026-06-29 patterns audit declared this path's round-trip
  lossless — it tested exact repeats only and missed the variation mixing; #101
  covered the separate index-vs-frame bug and was fixed by deleting the consumer)
- **Description**: `PatternDetector.detect_patterns` merges exact-match positions
  and *variation* positions (transposed / volume-scaled windows with similarity
  ≥ 0.85) into a single `positions` list, which `compress_patterns` copies verbatim
  into `references`. The stored `events` are the anchor occurrence's events, so at
  every variation position the referenced content is **different music** — the data
  structure claims "pattern X occurs at position P" where it does not. The parallel
  (default) detector is exact-only and does not have this defect.
- **Evidence**: Reproduced. Motif ×3 + one transposed copy →
  `EnhancedPatternDetector` returns `pattern_0` with `positions = [0, 5, 10]` and
  `references['pattern_0'] = [0, 5, 10]`, but the sequence windows at 5 and 10
  contain `(41,21)`/`(42,22),(65,100)` where the stored events say
  `(40,20)`/`(40,20),(60,100)`. `stats` reports
  `original_size = 18 (= 6 events × 3 positions)`, `compression_ratio = 66.7%` —
  counting the two non-exact positions as full exact occurrences.
  `tests/test_pattern_integration.py:120-137` asserts positions are ints, never that
  the referenced windows equal the pattern events, so no test catches this.
- **Impact**: No ROM byte today (`references` analysis-only, #4). Real current
  impact: (a) `compression_ratio` printed by the ROM banner (`main.py:659`) and the
  `detect-patterns` subcommand (`main.py:347`) is inflated by non-exact occurrences;
  (b) the `patterns.json` artifact the subcommand ships is internally inconsistent
  (any future consumer reconstructing events-at-references silently plays the base
  pattern where a transposition belonged — the definition of the CRITICAL round-trip
  row); (c) `LoopManager.detect_loops` (`tracker/loop_manager.py:21,36-41`) derives
  loop start/end from these positions on the opt-in analysis path
  (`tracker/parser_fast.py:182-190`), so loops can anchor on a non-repeat.
- **Related**: #4 (closed), #101 (closed), PAT-03, PAT-04; pipeline audit PL-03.
- **Suggested Fix**: Keep `positions`/`references` exact-only and carry variations
  separately (they already exist under `pattern_info['variations']` with their
  transform), or tag each reference with its `{transposition, volume_change}` so a
  consumer *can* reconstruct losslessly. Add a round-trip test asserting
  `sequence[pos:pos+length] == pattern events` for every referenced position.

---

### PAT-02: Fallback warning "the ROM is INCOMPLETE" is false — event sampling cannot make the ROM incomplete
- **Severity**: MEDIUM
- **Dimension**: 7 (Large-File Sampling) / 4 (Stats & messaging accuracy)
- **Location**: `main.py:523-530` (warning), `main.py:661-662` (success-banner
  repeat); ground truth `exporter/exporter_ca65.py:862-874` and `:944-992` (all
  bytes derive from `frames`, which are never sampled)
- **Status**: **Existing: PL-03 (`docs/audits/AUDIT_PIPELINE_2026-07-01.md`)** —
  found independently by today's pipeline audit; not re-filed, recorded here because
  it is squarely inside this audit's Dim 7. Not in any GitHub issue (#10/#100 added
  the warning; neither covers its claim being false).
- **Description**: When the parallel detector fails and the sequential fallback
  samples events to `DETECTOR_MAX_EVENTS`, the pipeline warns "the ROM is
  INCOMPLETE. Re-run with --no-patterns for full fidelity." Sampling affects only
  the *pattern-metrics* input; the CA65 exporter serializes the full `frames` dict
  regardless (verified: the bytecode serializer iterates `range(max_frame+1)` over
  `frames[channel]`; `patterns` is only a mode switch, #4). The ROM contains the
  complete song either way. Conversely, the default parallel path samples >15000-event
  files with only a transient "(lossy)" note and no banner — two samplings of the
  same kind get opposite messaging.
- **Evidence**: See PL-03 for the full write-up; independently re-verified in this
  audit by tracing `events` (sampled, feeds only `detector.detect_patterns`) vs
  `frames` (unsampled, feeds `export_tables_with_patterns`) in `run_full_pipeline`.
- **Impact**: Users discard valid, complete ROMs and re-run with `--no-patterns`,
  which switches serializers and typically *grows* the ROM — the warning causes the
  harm it claims to prevent.
- **Related**: PL-03 (canonical), #10 (closed), #100 (closed), PAT-03.
- **Suggested Fix**: As PL-03: reword to "pattern compression metrics are based on a
  sample; audio data is complete", and apply consistent messaging on the parallel
  sampling path.

---

### PAT-03: `compression_ratio` measures only the patterned subset of a metrics-only analysis, yet is printed in the ROM success banner as if it described the ROM
- **Severity**: MEDIUM
- **Dimension**: 4 (Compression-Ratio & Stats Accuracy)
- **Location**: `tracker/pattern_detector.py:773-798`
  (`calculate_compression_stats`); printed at `main.py:659` (ROM banner) and
  `main.py:347` (subcommand)
- **Status**: NEW (#17, closed, fixed only the %-vs-x unit bug — verified fixed; the
  prior audit's Dim-4 pass filed nothing beyond it)
- **Description**: `original_size = Σ len(events) × len(positions)` and
  `compressed_size = Σ len(events)` are computed **only over detected patterns**.
  Frames covered by no pattern contribute to neither side, so the ratio describes
  the patterned subset, not the song ("96% reduction" can be reported when most of
  the song is un-patterned). Compounding it: (a) `positions` include non-exact
  variation occurrences (PAT-01) and self-overlapping matches (PAT-04), further
  inflating `original_size`; (b) per #4 the number has **no relationship to emitted
  ROM bytes** (actual size reduction comes from macro/instrument dedup in the
  bytecode serializer), yet the success banner prints it directly under "ROM size",
  presenting a detector metric as a property of the artifact.
- **Evidence**: `calculate_compression_stats` sums only `original.values()` /
  `compressed.values()` (no total-event term is ever passed in); banner at
  `main.py:656-660` prints ROM size then "Compression ratio: X% reduction" from
  `pattern_result['stats']`. CHECK-run: 3 occurrences (1 exact + 2 variations) of a
  6-event pattern in a 17-event stream reported 66.7% "reduction".
- **Impact**: Misleading headline number in every patterns-mode build and in
  CLAUDE.md-style claims ("~95.86% data reduction"); masks the fact that pattern
  detection currently has zero effect on output size. Cosmetic but systematically
  wrong (MEDIUM floor: inaccurate reported stats).
- **Related**: #17 (closed), #4 (closed), PAT-01, PAT-04, PL-03.
- **Suggested Fix**: Pass the total event count into `calculate_compression_stats`
  and report coverage-aware numbers (e.g. `patterned_events / total_events` plus the
  dedup ratio), and label the banner line "pattern-analysis metric" — or drop it
  from the ROM banner until references drive bytes.

---

### PAT-04: `_find_pattern_matches` lets the first match overlap the anchor — self-overlapping "non-overlapping" matches inflate counts and diverge from the parallel matcher
- **Severity**: MEDIUM
- **Dimension**: 8 (Match Semantics) / 5 (Parallel vs Sequential Equivalence)
- **Location**: `tracker/pattern_detector.py:291-306` — `pos = start_pos + 1`
  (`:297`) contradicts the "Skip the length of the pattern to avoid overlaps"
  intent (`:302`); correct greedy for comparison:
  `tracker/pattern_detector_parallel.py:266-274`
- **Status**: NEW (related: #131/TD-03 flagged the *duplication* of this function
  "already drifting"; the duplicate copy is now gone — this is the concrete drift
  left in the surviving copy)
- **Description**: The scan for further occurrences starts at `start_pos + 1`
  instead of `start_pos + pattern_len`, so in self-similar runs (period <
  pattern length) the first "match" overlaps the anchor window. Only after a match
  does the code skip `pattern_len`. The parallel `_collect_length_candidates` uses a
  correct `next_free` greedy, so the two detectors return different `exact_matches`
  for identical input.
- **Evidence**: Reproduced. 12 identical notes, pattern length 4:
  sequential `exact_matches = [0, 1, 5]` (positions 0 and 1 overlap); parallel
  returns `[0, 4, 8]`. Because overlapping windows in a self-similar run have
  identical content, reconstruction would still be value-consistent (no double-write
  corruption is possible from this alone) — the damage is inflated occurrence
  counts → inflated `score_pattern` totals and `original_size`/`compression_ratio`,
  plus fallback-vs-default result divergence beyond the documented
  variations difference (#103).
- **Impact**: Sequential path (fallback + `detect-patterns` subcommand) overstates
  repetition on drones/ostinati and selects differently from the default path;
  stats inflate (feeds PAT-03). No byte-level effect (#4). MEDIUM per the
  reference-offset-accounting floor.
- **Related**: #131 (open, duplication aspect), #103 (closed), PAT-01, PAT-03.
- **Suggested Fix**: Initialize the scan at `start_pos + pattern_len` (matching the
  stated intent and the parallel greedy), and add a shared-behavior test comparing
  both detectors' `exact_matches` on a constant run.

---

### PAT-05: `_collect_length_candidates` docstring overclaims equivalence with the per-start scan — anchor-blocked windows lose all their later occurrences
- **Severity**: LOW
- **Dimension**: 5 (Parallel vs Sequential Equivalence)
- **Location**: `tracker/pattern_detector_parallel.py:238-249` (equivalence claim:
  "matches the old per-start output because duplicate starts of the same window
  collapsed onto that first occurrence in `_select_best_patterns` anyway");
  whole-candidate rejection at `:179-199`
- **Status**: NEW (introduced with #114's O(n) rewrite; #103 documented the
  scoring/variations divergence but not this candidate-generation divergence)
- **Description**: The parallel path emits exactly **one** candidate per distinct
  window, anchored at its first occurrence, and `_select_best_patterns` rejects a
  candidate wholesale if *any* of its positions overlaps an already-selected
  pattern. The sequential path still emits per-start candidates, so when a
  higher-scoring pattern overlaps only the window's first occurrence, the
  sequential detector recovers the later occurrences via a later-anchored candidate
  while the parallel detector loses them all. The docstring's "collapsed onto that
  first occurrence anyway" equivalence claim is therefore wrong in the general case.
- **Evidence**: Reproduced. Winner pattern P (4 occurrences) overlapping only W's
  first occurrence: sequential covers W's later occurrences at 18 and 30
  (`covered = [True, True, False]`), parallel covers none
  (`[False, False, False]`); the two detectors also select structurally different
  sets on the same input (length-12 × 3 positions vs length-6 × 4).
- **Impact**: Metrics-only today (compression quality/stats differ between default
  and fallback paths); becomes user-audible pattern-selection divergence if
  references ever drive bytes. Also doc-accuracy: the docstring asserts an
  equivalence the code does not have.
- **Related**: #103 (closed), #114 (closed), #46 (closed — determinism verified
  intact), PAT-04.
- **Suggested Fix**: Correct the docstring (claim "equivalent modulo
  anchor-blocking") or emit per-occurrence-suffix candidates for windows whose
  anchor region is contested; alternatively make selection reject per-position
  rather than per-candidate in both detectors.

---

### PAT-06: `_get_variation_summary` shapes drift between the two detectors
- **Severity**: LOW
- **Dimension**: 2 (Schema Integrity)
- **Location**: `tracker/pattern_detector.py:448-458`
  (`{variation_count, transposition_range, volume_range}`) vs
  `tracker/pattern_detector_parallel.py:203-211`
  (`{variation_count, exact_matches}`)
- **Status**: NEW (#104, closed, unified the `stats` schema only; the prior audit's
  P-05/#103 covered the *count* divergence, not the key drift)
- **Description**: The `variations` member of the detect-patterns envelope has a
  different per-pattern inner shape depending on which detector produced it: the
  sequential summary carries `transposition_range`/`volume_range`; the parallel
  summary instead carries `exact_matches` and can never report a nonzero
  `variation_count`. A grep of `main.py`, `debug/`, `nes/`, `exporter/` finds **no
  reader** of `['variations']`, and `run_detect_patterns` drops the key from its
  JSON artifact entirely (noted as by-design in AUDIT_PIPELINE_2026-07-01), so the
  drift is currently harmless — the same latent-trap class as the fixed #104.
- **Evidence**: Reader grep returns nothing outside the detectors and tests;
  compare the two `_get_variation_summary` bodies.
- **Impact**: None today; a future consumer written against one shape breaks (or
  silently mis-reads) on the other path.
- **Related**: #104 (closed), #103 (closed).
- **Suggested Fix**: Emit one shape from both (e.g. always
  `{variation_count, exact_match_count, transposition_range, volume_range}` with
  neutral values on the parallel path), mirroring the #104 stats unification.

---

### PAT-07: `_hash_pattern` returns `hash()` (docstring says str) — a collision silently merges unrelated patterns' references
- **Severity**: LOW
- **Dimension**: 3 (Reference Correctness) / hardening
- **Location**: `tracker/pattern_detector.py:769-771`; consumer
  `compress_patterns` (`:745-757`)
- **Status**: NEW
- **Description**: The dedup key for "identical patterns" is Python's 64-bit
  `hash(tuple((note, volume), ...))`, not the tuple itself (the docstring claims a
  "unique hash"/str). A hash collision between two different event tuples would
  merge the second pattern into the first: its `positions` are appended to the
  wrong pattern's `references` and its own definition is dropped. Probability is
  astronomically low per song, but the failure is silent and the fix is free —
  the tuple is already hashable and using it directly as the dict key is exact.
- **Evidence**: `pattern_hash = self._hash_pattern(...)` used as the sole identity
  key in `pattern_hash_map`; no equality confirmation on hit.
- **Impact**: Worst case (collision): wrong positions attributed to a pattern in
  `patterns.json`/stats — analysis-only today (#4). Also minor doc-rot (int vs
  documented str).
- **Related**: #4 (closed), PAT-01.
- **Suggested Fix**: Key `pattern_hash_map` on the event tuple itself (drop
  `_hash_pattern`, or make it return that tuple).

---

## Recent-commit verification (2bcb780 and the fix wave it completes)

Given the audit request's extra scrutiny on `2bcb780`, each claimed fix in the
recent pattern-detection commits was re-verified against the live tree:

| Issue | Claim | Verified |
|-------|-------|----------|
| #100 | Sequential 1000-event head-cut → uniform sampling | ✓ `pattern_detector.py:194-197` uses `sample_events_for_detection`; both call sites (`main.py:331`, `main.py:523`) pre-sample to `DETECTOR_MAX_EVENTS` and warn with the true retained count |
| #102 | Three limits → two caps, per complexity class | ✓ only `MAX_PATTERN_EVENTS=15000` / `DETECTOR_MAX_EVENTS=1000` remain; `ThreadedPatternDetector` (the 2000-stride) deleted in `2bcb780`; guard test added (`tests/test_patterns.py:928-963`) |
| #103 | Shared scoring across detectors | ✓ single `score_pattern` (`pattern_detector.py:41-80`) imported by the parallel module; the exact-only/variation divergence is documented in code (residual candidate-generation divergence: PAT-05) |
| #104 | `--no-patterns` stub stats schema unified | ✓ `main.py:541-550` emits the detector schema (`original_size/compressed_size/compression_ratio/unique_patterns`); consistency test exists |
| #17 | ratio printed as % | ✓ both print sites say "% reduction" (`main.py:347`, `:659`); semantics of the number itself: PAT-03 |
| #46 | parallel determinism/fallback tested | ✓ deterministic tie-break in `_select_best_patterns:174`; empirically: two pool runs identical, pool result == serial fallback on a 3000-event input |
| #114 | O(n) grouping, sequence shipped once via pool initializer | ✓ chunks are `{'pattern_length': int}` only; initargs picklable; `_detect_patterns_worker` module-level, no shared-state mutation |
| #101 | dead `PatternExporter`/`exporter.py` deleted | ✓ files gone in `2bcb780`; no stale imports remain (`main.py` import removed) |
| #4 | references analysis-only | ✓ `main.py:563-568` passes `{}`; `export_tables_with_patterns` docstring + body never read the arg |

**Housekeeping**: issue **#105** (dead `ThreadedPatternDetector`) is *fixed by
`2bcb780`* (class removed, guard test added) but still OPEN — it can be closed.
**#131** (TD-03, copy-pasted `_find_pattern_matches`) is half-resolved: the parallel
copy is gone; the surviving copy's behavior bug is PAT-04. **#106** (per-chunk
`except…continue`, `pattern_detector_parallel.py:124-134`) was re-verified as still
present, unchanged — Existing, not re-reported.

## Dimensions checked with no new finding

- **Dim 1 (CompressionEngine)**: lossless on all cases including the absent-key
  delta and a 200-event fuzz; `_can_delta_compress` and `_create_delta_block` agree
  on `numeric_keys = {note, volume, sample_id}`; empty-dict silence events RLE
  round-trip cleanly. `tests/test_compression*.py` assert full-sequence equality
  (real coverage, not shape).
- **Dim 2 (schema)**: all live producers (parallel detect_patterns/no-events/
  `_empty_result`, sequential no-events envelope, `--no-patterns` stub) emit the
  same four `stats` keys; only `compression_ratio` is ever read
  (`main.py:347,659`). Residual inner-shape drift: PAT-06.
- **Dim 5 (fallback shape)**: inner serial fallback returns the bare patterns dict
  and its caller re-wraps via the compressor into the full envelope — correct; the
  outer `main.py` fallback pre-samples to the sequential cap and warns (accuracy of
  that warning: PAT-02/PL-03).
- **Dim 6 (multiprocessing)**: post-#114 chunks are trivially picklable; worker is
  module-level; no shared-state mutation; memory footprint of one sequence copy per
  worker is the open perf item #115 (Existing, not re-reported).
- **Dim 7 (sampling reach)**: sampled `events` feed detection only; the exporter
  consumes the never-sampled `frames` — no data-loss path (the false loss *claim*
  is PAT-02/PL-03). `LARGE_FILE_THRESHOLD` advice at `main.py:501-505` drops
  nothing.
- **Dim 8 (bounds)**: `range(min, min(max, len)+1)` degrades to empty for
  `len < min` and `max < min`; both entry points share
  `PATTERN_MIN_LENGTH/PATTERN_MAX_LENGTH` (#19 verified).
- **Dim 9 (loops)**: tempo-key format written (`loop_manager.py:130`) matches the
  read (`:156`); `end <= start` guarded (`:98,149`); a shared-end jump-table clobber
  is impossible for non-degenerate loops post-`_optimize_loops` (two non-empty
  disjoint ranges cannot share an end). Loop detection is reachable only from the
  opt-in `parse_midi_to_frames_with_analysis` and the legacy parser (the 2026-06-29
  audit's P-04 — analysis-on-every-parse — is fixed: the fast parser returns empty
  metadata). Loop quality on the sequential path inherits PAT-01/PAT-04 positions.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-07-01.md
```
