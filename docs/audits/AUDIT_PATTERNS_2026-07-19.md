# Pattern Detection & Compression Audit — 2026-07-19

## Summary

**Round-trip result: LOSSLESS CONFIRMED (empirically).** I ran actual
compress→decompress round-trips on both compression paths and diffed frame-by-frame:

- **Pattern-dedup path** (`EnhancedPatternDetector` / `ParallelPatternDetector` →
  `PatternCompressor`): every persisted `references` position maps to a window that is an
  exact `(note, volume)` match of the stored pattern `events`. 0 mismatches across the
  sequential and parallel paths. The PAT-01 (#168) exact-only invariant holds in code.
- **RLE/delta path** (`CompressionEngine.compress_pattern` ↔ `decompress_pattern`): a
  pattern exercising RLE runs, delta runs (including a numeric key whose diff was 0 and is
  therefore absent from the delta), and raw events with an extra non-numeric key round-tripped
  to an exact match. The 0-diff-key preservation the skill flags is correct.

No CRITICAL (lossy-where-claims-lossless) finding. Schema integrity (Dimension 2) is intact:
both detectors, both empty-result paths, and the `--no-patterns` stub emit the identical
7-key `stats` set and the unified 4-key `variations` inner shape. `_hash_pattern` (PAT-07/#173)
still returns the raw tuple, not `hash()`. The exporter still treats `references` as
non-consumed (#4).

**Finding counts:** CRITICAL 0 · HIGH 0 · MEDIUM 1 · LOW 1 (+ 1 existing coverage gap noted).

**3 highest-leverage fixes:**
1. **PAT-A (MEDIUM):** Fix the scoring/persistence mismatch in the sequential detector —
   candidates win on variation count but persist exact-only positions, producing
   single-occurrence "patterns" with 0% compression that displace the genuinely-repeating
   shorter pattern and make `compression_ratio`/`coverage_ratio` misleading.
2. **PAT-B (LOW):** Apply the PAT-04/#170 self-overlap fix to `DrumPatternDetector`'s emergent
   scan (still starts at `start + 1`), which the DPCM drum mapper actually uses.
3. Land the missing exact-only round-trip test (**Existing #311/PAT-10**) so the invariant this
   audit just re-verified by hand is pinned against regression.

---

## Findings

### PAT-A: Variation-driven selection persists single-occurrence patterns with 0% compression
- **Severity**: MEDIUM
- **Dimension**: Dimension 4 (Compression-Ratio & Stats Accuracy); touches Dimension 1/3
- **Location**: `tracker/pattern_detector.py:242-263` (scoring/candidate build), `:295-319`
  (selection), `:866-885` (`calculate_compression_stats`)
- **Status**: NEW
- **Description**: The sequential `PatternDetector` scores a candidate with
  `score_pattern(length, len(exact_matches), len(variations))` — variations count toward the
  `total_count` that clears the "≥3 occurrences" gate and drives the length/frequency bonuses.
  But after the PAT-01 (#168) fix, the candidate persists `positions = sorted(set(exact_matches))`
  (exact-only). A candidate can therefore be *selected on the strength of its variations* yet
  store a **single** exact position. Selection then marks that candidate's whole
  `occupied_positions` range used, blocking the genuinely-repeating shorter exact pattern that
  overlaps it. `calculate_compression_stats` computes `original_size = Σ len(events)·len(positions)`
  over the exact-only positions, so a single-position pattern yields
  `original_size == compressed_size` → `compression_ratio = 0.0`.
- **Evidence**: Reproduced. Input = `ABCD` (4 events) repeated 4× followed by 5 filler events.
  Clean `ABCD×4` alone detects `pattern_0 len 4 positions [0,4,8,12]`, ratio 75.0%, coverage
  100%. Add the filler and the detector instead selects:
  ```
  pattern_0 len 10 positions [8] exact [8]   # a SINGLE occurrence
  refs {'pattern_0': [8]}
  stats compression_ratio 0.0, coverage_ratio 47.6
  ```
  The length-10 window at pos 8 wins because it accrued ≥2 *variations* (its first 8 of 10
  events match a neighboring window ≥0.85 similarity), giving it a high length-bonus score; its
  variation positions (in the non-persisted `occupied_positions`) consume frames 8–17 and block
  the length-4 `ABCD` candidate. The round-trip is still exact (the one stored position matches
  its events), so this is not a losslessness bug — it is degraded compression plus a misleading
  0% ratio and a coverage figure derived from a degenerate selection.
- **Impact**: `detect-patterns` output and both success banners under-report real compressibility
  and can report `compression_ratio 0.0` on songs that contain obvious repeats. Compression
  *quality* is degraded (a zero-benefit long pattern is stored and blocks a real one). No ROM
  impact — `export_tables_with_patterns` derives every byte from `frames` and does not consume
  `references` (#4) — so blast radius is the analysis/metrics surface and the `detect-patterns`
  JSON, not playback. Parallel path is unaffected (exact-only, no variations).
- **Related**: PAT-01 (#168, closed — this is a side effect of that fix's scoring/persistence
  split), #4, #169/PAT-03.
- **Suggested Fix**: Make scoring consistent with what is persisted: either score the sequential
  candidate on `len(positions)` (exact-only) so a single-exact-occurrence window cannot clear the
  ≥3 gate, or drop candidates whose exact `len(positions) < 3` before selection. Keep
  `occupied_positions` for overlap-blocking but do not let a variation-only candidate win a region
  it cannot actually compress.

### PAT-B: `DrumPatternDetector` emergent scan self-overlaps (PAT-04/#170 fix not applied here)
- **Severity**: LOW
- **Dimension**: Dimension 8 (Pattern-Length Bounds & Match Semantics)
- **Location**: `tracker/pattern_detector.py:666` (`detect_drum_patterns` emergent-pattern loop)
- **Status**: NEW
- **Description**: PAT-04 (#170) fixed the self-overlap in `_find_pattern_matches` by starting
  the post-anchor scan at `start_pos + pattern_len`. The sibling `DrumPatternDetector.detect_drum_patterns`
  emergent-pattern scan was not updated: it iterates `for pos in range(start + 1, len(sequence) - length + 1)`
  and appends every `pos` whose window is similar, with no skip-by-`length`. On a self-similar
  drum run (period < pattern length) this counts overlapping "matches", inflating
  `len(matches)` fed to `score_drum_pattern` and the subsequent `_optimize_drum_patterns` overlap
  math.
- **Evidence**: `tracker/pattern_detector.py:666` `for pos in range(start + 1, len(sequence) - length + 1):`
  with `matches.append(pos)` at `:671` and no `pos += length` skip, contrasted with the fixed
  `_find_pattern_matches` at `:334-339`. `DrumPatternDetector` is live: imported and used by
  `dpcm_sampler/enhanced_drum_mapper.py:4,208,257` (`detect_drum_patterns`).
- **Impact**: Suboptimal / inflated drum-pattern selection heuristics in the DPCM drum mapper.
  It affects which drum patterns are flagged, not lossless music data — no ROM corruption. Blast
  radius is the drum-mapping quality path only. (May be better owned by the DPCM audit.)
- **Related**: PAT-04 (#170, closed for `_find_pattern_matches`).
- **Suggested Fix**: Mirror the `_find_pattern_matches` non-overlap discipline in the emergent
  drum scan — skip `length` after a match — so overlapping self-similar windows aren't
  double-counted.

### Existing coverage gap (noted, not re-filed): exact-only round-trip invariant untested
- **Severity**: LOW
- **Dimension**: Dimension 1 (Round-Trip Integrity)
- **Location**: `tests/test_pattern_integration.py:123-138`
- **Status**: Existing: #311 (PAT-10)
- **Description**: `test_pattern_positions_format` still only asserts `positions` are `int`s; no
  test asserts the referenced window equals the pattern's stored `events`. This audit re-verified
  the invariant by hand (0 mismatches), but nothing pins it in CI, so a regression of the PAT-01
  exact-only guarantee would pass. Already tracked as open issue **#311**; no new finding filed.
- **Suggested Fix**: (per #311) add a test that, for each detected pattern, asserts
  `sequence[pos:pos+length] == [(e['note'], e['volume']) for e in events]` for every `pos` in
  `references`.

---

## Dimensions verified clean (no finding)

- **Dim 1 (round-trip):** Both paths lossless — empirically diffed, 0 mismatches. RLE + delta +
  raw + 0-diff-key-absent all preserved.
- **Dim 2 (schema):** Sequential/parallel/`_empty_result`/no-events/`--no-patterns` stub all emit
  the same 7 `stats` keys (`compression_ratio, original_size, compressed_size, unique_patterns,
  total_events, patterned_events, coverage_ratio`) and the same 4-key `variations` inner shape.
- **Dim 3 (offsets/length):** `len(compressed['events']) == length`; exporter does not consume
  `references` (#4 contract intact at `exporter/exporter_ca65.py:964-971`).
- **Dim 5 (parallel/serial + fallback):** Inner serial fallback returns the bare patterns dict via
  `_select_best_patterns`; caller re-wraps through the compressor into the full envelope.
  `_collect_length_candidates` docstring still owns the PAT-05 (#171) non-equivalence caveat.
  In-process per-sub-chunk retry (#106) and the durable end-of-run partial-detection warning both
  present.
- **Dim 6 (multiprocessing):** Sequence/events shipped once via `initializer=_init_pattern_worker`
  / `initargs`; work chunks carry only `{pattern_length, start_range}`. Worker + initializer are
  module-level and mutate no shared state. `ThreadedPatternDetector` confirmed gone.
- **Dim 7 (sampling):** Two caps only (`MAX_PATTERN_EVENTS=15000`, `DETECTOR_MAX_EVENTS=1000`),
  shared `sample_events_for_detection` (uniform `np.linspace`, not head cut). Sampling feeds
  detection only; export still derives from `frames`.
- **Dim 8 (bounds/match semantics):** `_find_pattern_matches` PAT-04 fix intact; `_hash_pattern`
  PAT-07 returns raw tuple. (Drum-detector exception → PAT-B above.)
- **Dim 9 (loops):** `LoopManager.detect_loops` guards `len(positions) > 1`, so a single-position
  pattern (as produced in PAT-A) is skipped rather than raising `IndexError` on `positions[-2]`.
  `EnhancedLoopManager` tempo key format matches between write (`:141`) and read (`:167`).

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-07-19.md
```
