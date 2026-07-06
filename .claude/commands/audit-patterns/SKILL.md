---
description: "Audit pattern detection and compression — round-trip integrity, schema, parallelism"
argument-hint: "[--focus <dims>]"
---

# Pattern Detection & Compression Audit

Audit the pattern-detection and compression subsystem — the stage that finds repeating
note/volume runs, deduplicates them into a `patterns`/`references` table, and reports a
`compression_ratio`. The headline risk is **round-trip integrity**: the system claims
compression is lossless, so decompressing `patterns` + `references` MUST reproduce the exact
original frame/event stream. Any divergence is CRITICAL (claims lossless, isn't).

Shared protocol: `.claude/commands/_audit-common.md` — read it for the project layout, the
dedup procedure, and especially the **detect-patterns inter-stage contract** (the dict keys
`patterns` / `references` / `stats` / `variations`, `--no-patterns` stub semantics, and the
Multiprocessing rule for `tracker/pattern_detector_parallel.py`). Severity floors:
`.claude/commands/_audit-severity.md` — note the special rows: round-trip mismatch = CRITICAL,
multiprocessing crash without the documented fallback firing = HIGH, inaccurate compression
stats = MEDIUM. Do not restate either file; apply them.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 1,3`). Default: all.

## Extra Per-Finding Field
- **Dimension**: one of the dimensions below.

## Dimensions

### Dimension 1: Round-Trip Integrity (compress → decompress)
THE headline check. Compression must be lossless. Do not take the docstrings' word for it —
**actually round-trip a sample**. Two distinct paths exist and both must be verified:

- The pattern-dedup path: `tracker/pattern_detector.py` `PatternCompressor.compress_patterns`
  (`:799-829`) produces `compressed_data` + `pattern_refs`. (The former `PatternExporter`/
  `exporter.py` FamiTracker reconstruction path was deleted as dead + frame-space-buggy, #101
  — the `references` are analysis-only and no exporter consumes them, #4, both closed.) Build
  a small synthetic event list with known repeats, run `EnhancedPatternDetector.detect_patterns`
  (`tracker/pattern_detector.py:396`), and confirm every detected pattern's occurrences are
  exact repeats of its events. PAT-01 (#168) is now **fixed & closed**: the sequential detector
  persists an **exact-only** `positions`/`references` list — `positions` is
  `sorted(set(exact_matches))` (`pattern_detector.py:255`, `:284`), while a separate
  `occupied_positions` (exact + variation positions) is used *only* to block a different
  candidate from claiming the same frames during non-overlap selection (`:303-304`, `:315`) and
  is never persisted. So every stored reference now points at a true exact repeat of the
  pattern's `events` (variation positions no longer leak in). Any note/volume mismatch found by
  your own round-trip is still CRITICAL; still flag any change that starts having an exporter
  reconstruct from `references` (#4).
- The RLE/delta path: `exporter/compression.py` `CompressionEngine.compress_pattern` ↔
  `decompress_pattern`. Round-trip a pattern that exercises RLE runs, delta runs, and raw
  events together. Watch the delta decoder (`compression.py:100-107`): it mutates a running
  event and only sums keys present in the delta — confirm a key that is *absent* from a delta
  (because its diff was 0) is preserved, not reset. Confirm `_can_delta_compress`
  (`compression.py:154-177`) and `_create_delta_block` (`compression.py:179-200`) agree on the
  `numeric_keys` set so no field silently drifts.
- Existing coverage to check (and distrust if thin): `tests/test_compression.py`,
  `tests/test_compression_integration.py`,
  `tests/test_pattern_integration.py`. A round-trip with no asserted frame-by-frame equality
  is not coverage. `tests/test_pattern_integration.py:120-137` still only asserts positions
  are ints, never that the referenced window equals the pattern's stored events — with PAT-01
  now fixed that exact-only invariant holds in code, but no test pins it, so a regression would
  go unnoticed.

### Dimension 2: `pattern_result` Schema Integrity
The detect-patterns contract is a dict with `patterns`, `references`, `stats`, `variations`
(see `_audit-common.md`). Verify every producer returns all four with consistent shapes:
- `ParallelPatternDetector.detect_patterns` (`tracker/pattern_detector_parallel.py:31`),
  its `_empty_result` (`pattern_detector_parallel.py:274-283`), and the no-events early return
  (`pattern_detector_parallel.py:35-43`).
- `EnhancedPatternDetector.detect_patterns` (`tracker/pattern_detector.py:396`) and its
  no-events return (`pattern_detector.py:398-406`).
  (The dead `ThreadedPatternDetector` was removed entirely along with #102's fix — the class and
  file no longer exist. `grep -rn ThreadedPatternDetector` now only matches a doc comment
  (`tracker/pattern_detector.py:12`) and a regression test asserting it's gone
  (`tests/test_patterns.py:1184-1190`). This resolved P-08/#105's race/shape concerns by
  construction; #105 and #102 are both **closed**.)
- The `--no-patterns` stub built inline in `run_full_pipeline` (`main.py:865-881`): confirmed
  **fixed** (#104) — its `stats` keys (`original_size`, `compressed_size`, `compression_ratio`,
  `unique_patterns`, plus `total_events`/`patterned_events`/`coverage_ratio`) now match both
  detectors' schema exactly, and it reports `0` (not `1.0`) since direct export applies no
  compression (#17). The former top-level-`variations`-omission drift is also **fixed & closed**
  (#258/PAT-09): the stub now emits `'variations': {}` (`main.py:880`), matching the 4-key
  envelope both detectors return. PAT-06 (#172) is likewise **fixed & closed**: the two
  `_get_variation_summary` implementations now emit the SAME inner shape
  (`pattern_detector.py:502-520` and `pattern_detector_parallel.py:256-272` both return
  `{variation_count, exact_match_count, transposition_range, volume_range}`); the parallel path
  reports `variation_count = 0` and neutral `(0, 0)` ranges by design (exact repeats only), not
  a divergent key set. Confirm both shapes stay unified before trusting any consumer of
  `variations`.

### Dimension 3: Reference Offsets & Length Correctness
A wrong offset corrupts playback, not just space. Trace position→frame mapping end to end:
- `PatternCompressor.compress_patterns` (`pattern_detector.py:799-829`) fills `pattern_refs`
  with pattern **start positions** (sequence indices) — for the sequential detector these are
  now **exact-only** (PAT-01, #168, closed — see Dimension 1; the non-exact variation positions
  live in the non-persisted `occupied_positions` and never reach `references`). These are
  analysis-only — no exporter consumes them (#4, closed), and the one path that did
  (`PatternExporter`) was deleted as frame-space-buggy (#101, closed). Still confirm
  `len(compressed_data[pattern_id]['events'])` equals the pattern `length` — a mismatch would
  misalign any future consumer.
- The old "occurrence-index passed as pattern offset" bug (#102-adjacent, formerly described
  here as an `enumerate(positions)` loop in `main.py`) **no longer exists** — that whole code
  path was deleted. `run_full_pipeline` now calls `CA65Exporter.export_tables_with_patterns`
  with a literal empty `{}` for `references` (`main.py:917-924`), and the step-by-step
  `run_export` path (`main.py:519-560`) forwards whatever `references` a `detect-patterns` JSON
  file contains — but `export_tables_with_patterns` itself documents that the `references`
  argument is **not consumed** (`exporter/exporter_ca65.py:962-971`, #4, closed): `patterns`
  truthiness is only a boolean switch between direct frame export and the MMC3
  macro-bytecode serializer. Confirm this contract still holds before trusting any future PR
  that claims to "wire up" pattern references into the exporter.
- Overlap accounting: `_select_best_patterns` (`pattern_detector_parallel.py:216-254`) and the
  selection loop in `pattern_detector.py:296-315` mark `range(pos, pos+length)` used. Confirm
  no two retained patterns can claim the same frame (double-write) and no frame between the
  last pattern end and the song end is silently dropped. (PAT-04, #170, is now closed — the
  sequential detector's exact-match scan no longer self-overlaps; see Dimension 8.)

### Dimension 4: Compression-Ratio & Stats Accuracy
Cosmetic but must not mislead (MEDIUM floor when wrong).
`PatternCompressor.calculate_compression_stats` (`tracker/pattern_detector.py:843-891`)
computes `original_size = Σ len(events)*len(positions)` and
`compressed_size = Σ len(events)`, over detected patterns only. The former "x multiplier vs %
reduction" inconsistency is **fixed** (#17, closed): every print site now uses the same "%
reduction" convention — `main.py:655` (subcommand), `main.py:1046` (ROM success banner), and the
`--no-patterns` stub's `0` (`main.py:871`) is coherent with that convention (0% reduction, not
a misleading `1.0`).
PAT-03 (#169) is now **fixed & closed**: `calculate_compression_stats` takes a `total_events`
arg (`pattern_detector.py:843-844`) and reports a separate `coverage_ratio =
patterned_events / total_events` (`:879-881`), and both banners now print the dedup ratio
explicitly labeled as within the patterned subset PLUS a distinct "Pattern coverage" line
(subcommand `main.py:655`/`:657`, ROM banner `main.py:1046`/`:1048`). The dedup ratio still has
no relationship to emitted ROM bytes (actual size reduction comes from macro/instrument dedup
in the bytecode serializer, #4) — confirm the banner keeps the two numbers distinct and that
callers keep passing `total_events` (the analyzed/sampled count, #257/PAT-08), since omitting it
silently reads `coverage_ratio` as 0. The old PAT-01/PAT-04 inflation of `original_size` is also
gone now that `positions` is exact-only and the match scan no longer self-overlaps.

### Dimension 5: Parallel vs Sequential Equivalence + Documented Fallback
The two detectors' scoring is now **shared** (#103, closed) — verify the fix is complete, not
just that it merged the formulas:
- **Scoring**: both `ParallelPatternDetector`'s `_collect_length_candidates`
  (`pattern_detector_parallel.py:354-355`) and `EnhancedPatternDetector.detect_patterns`
  (`pattern_detector.py:238`, `:272`) now call the same module-level `score_pattern`
  (`pattern_detector.py:41`), the parallel path always passing `variation_count=0`. This is
  documented as by-design, not a bug: the parallel path's O(n) hash-grouping (#114) finds exact
  repeats only and structurally cannot detect transposed/volume-scaled variations, so it stays
  variation-free. Confirm this is still true and pinned by a test
  (`tests/test_patterns.py`) rather than re-diverging silently.
- PAT-05 (#171) is now **fixed & closed** — but the fix was a *doc correction*, not a behavior
  change: the two paths can still select *structurally different* pattern sets on identical
  input (the parallel path emits one candidate per distinct window, anchored at its first
  occurrence, and `_select_best_patterns` rejects the candidate wholesale if any position
  overlaps an already-selected pattern, so a winning pattern overlapping only a window's first
  occurrence loses that window's later occurrences entirely, while the sequential per-start scan
  recovers them via a later-anchored candidate). The `_collect_length_candidates` docstring now
  *correctly documents this non-equivalence* (`pattern_detector_parallel.py:311-320`) instead of
  overclaiming equivalence. Confirm the docstring still owns this caveat and hasn't regressed to
  an equivalence claim.
- **Fallback firing**: `run_full_pipeline` wraps `ParallelPatternDetector` in `try/except` and
  falls back to `EnhancedPatternDetector` (`main.py:827-853`), and inside the parallel detector
  `_detect_patterns_parallel` catches a pool-wide failure and calls `_detect_patterns_serial`
  (`pattern_detector_parallel.py:182-185`). Verify the inner serial fallback returns the raw
  `patterns` dict via `_select_best_patterns` (`pattern_detector_parallel.py:214`) — NOT the
  full `{patterns,references,stats,variations}` envelope — and that its caller (`detect_patterns`,
  `pattern_detector_parallel.py:76-94`) still wraps it via the compressor. If the serial
  fallback's return shape ever bypasses compression/stats, the fallback "fires" but yields a
  malformed result (HIGH).
- P-09 (#106) is now **fixed & closed**: the per-chunk `except` inside the
  *whole-pool-succeeded* path (`pattern_detector_parallel.py:164-178`) no longer silently drops
  a failed chunk's candidates — it recovers that length in-process via `_collect_length_candidates`,
  and only a length that ALSO fails the serial retry is recorded in `failed_lengths` and surfaced
  by a durable end-of-run warning (`pattern_detector_parallel.py:190-192`), not just a transient
  `pbar.write`. Confirm both the in-process retry and the persistent warning are still present.
- The outer `main.py` fallback re-trims events to `max_events` (default `DETECTOR_MAX_EVENTS` =
  1000, a named constant — not an ad-hoc "2000" as in older notes) via
  `sample_events_for_detection` (`main.py:844`) — confirm this matches the sequential detector's
  own internal cap (`pattern_detector.py:204-207`) so the warning reports the count actually
  retained, not a larger figure the detector would silently re-cut (#100, closed).

### Dimension 6: Multiprocessing Safety (pickle-ability, shared state, pool hygiene)
This dimension changed substantially since the O(n) hash-grouping rewrite (#114, closed) — the
old "entire sequence embedded in every chunk" design is gone:
- `_detect_patterns_parallel` (`pattern_detector_parallel.py:106-197`) now builds one **tiny**
  work chunk per pattern length — just `{'pattern_length': length}`
  (`pattern_detector_parallel.py:117-121`) — and ships the (potentially large) `sequence` and
  `valid_events` to each worker **once** via the `ProcessPoolExecutor(initializer=
  _init_pattern_worker, initargs=(sequence, valid_events))` call (`:146-150`), stashed as
  module globals `_WORKER_SEQUENCE`/`_WORKER_EVENTS` (`:289-298`) instead of being re-pickled
  per chunk × per length. This directly fixes the old memory-blowup / pickle-cost concern —
  confirm it stays true (no code re-introduces per-chunk copies of the full sequence).
  Everything shipped through `initargs` here is a plain list of tuples/dicts — confirm nothing
  non-picklable (a `tempo_map`, a closure, a numpy array) is added to that call in future
  changes, since `EnhancedTempoMap` itself is deliberately kept out of the worker payload.
- Confirm `_detect_patterns_worker` (`pattern_detector_parallel.py:371-379`) and
  `_init_pattern_worker` (`:293-298`) are module-level (picklable/importable by the child
  process) and that `_collect_length_candidates` (`:301-368`), the actual per-length work, reads
  the globals but mutates no shared state across workers.
- The dead `ThreadedPatternDetector` (formerly a second, thread-based, shared-`patterns`-dict
  race) is confirmed **removed** (#102, closed) — `grep -rn ThreadedPatternDetector` matches
  only a doc comment in `pattern_detector.py:12` and a regression test
  (`tests/test_patterns.py:1184-1190`) asserting it stays gone. No shared mutable state remains
  to audit here.

### Dimension 7: Large-File Sampling Not Dropping Musical Content
Sampling must not silently change the song. The old "three inconsistent limits" defect is
**fixed** (#102, closed) — there are now exactly two, sharing one implementation:
- `LARGE_FILE_THRESHOLD = 10000` (`main.py:818`) only prints advice — confirm it does not
  itself drop events.
- Both detectors now call the same module-level `sample_events_for_detection`
  (`tracker/pattern_detector.py:26-38`, uniform `np.linspace` sampling — not a head cut).
  `ParallelPatternDetector.detect_patterns` (`pattern_detector_parallel.py:60`) samples to
  `MAX_PATTERN_EVENTS = 15000` (`pattern_detector.py:16`); the sequential
  `PatternDetector.detect_patterns` (`pattern_detector.py:204-207`) samples to
  `DETECTOR_MAX_EVENTS = 1000` (`pattern_detector.py:23`) because it is O(n²)-ish. Trace whether
  the sampled `valid_events` is what later feeds `references`/frame reconstruction: since
  `export_tables_with_patterns` derives all bytes from `frames` (not from the sampled detection
  sequence, #4), the exported song is NOT altered by this sampling — only pattern-detection
  *quality* is reduced. Confirm this remains true; if a future change makes export consume the
  sampled sequence instead of `frames`, that would become CRITICAL data loss.
- The old third limit (the removed `ThreadedPatternDetector`'s 2000-stride) is gone along with
  the class (#102, closed) — confirm no new ad-hoc cap is introduced without updating the
  `MAX_PATTERN_EVENTS`/`DETECTOR_MAX_EVENTS` doc comment (`pattern_detector.py:8-23`) that
  explains why exactly two caps exist and don't shadow each other.

### Dimension 8: Pattern-Length Bounds & Match Semantics
- `min_pattern_length`/`max_pattern_length` constructor defaults are `3..32` for both detectors
  (`PatternDetector.__init__`, `pattern_detector.py:83`; `ParallelPatternDetector.__init__`,
  `pattern_detector_parallel.py:17`), but all three real entry points now consistently override
  `max_pattern_length` to the same named constants — `PATTERN_MIN_LENGTH = 3` /
  `PATTERN_MAX_LENGTH = 12` (`main.py:36-37`) — used by `run_detect_patterns`
  (`main.py:622-623`), the default parallel path (`main.py:829`), and its sequential fallback
  (`main.py:837`). This resolves the old "`detect-patterns` alone uses a default max of 32"
  drift; confirm all three call sites still reference the shared constants rather than a
  hardcoded literal before trusting this. Bounds are honored via
  `range(min, min(max, len(sequence))+1)` in both detectors — confirm a `max < min` or
  `len(sequence) < min` still can't produce a garbage/negative-range loop.
- `_find_pattern_matches` (`pattern_detector.py:320-338`, sequential detector only — the
  parallel worker uses a different O(n) grouping; see below) is now **correct** (PAT-04, #170,
  **fixed & closed**): the scan for matches after the anchor starts at `start_pos + pattern_len`
  (`:330`), not `start_pos + 1`, so a self-similar run (period < pattern length) can no longer
  produce a first "match" that overlaps the anchor window. The old `exact_matches`-count
  inflation (which fed `score_pattern` and `calculate_compression_stats` too high) and the
  divergence from the parallel path are gone (e.g. 12 identical notes, length 4 → both
  `[0, 4, 8]`). The two detectors are still NOT a "mirror" of each other — different algorithms
  (O(n²) per-start scan vs O(n) hash-grouped windows, #114) — but they now agree on the
  non-overlap invariant. Compare against the parallel detector's greedy `next_free` logic in
  `_collect_length_candidates` (`pattern_detector_parallel.py:340-345`). PAT-05 (#171, closed,
  see Dimension 5) documents the residual case where the parallel path's whole-candidate
  rejection can still lose valid later occurrences the sequential scan would recover.
- PAT-07 (#173) is now **fixed & closed**: `PatternCompressor._hash_pattern`
  (`pattern_detector.py:831-841`) returns the exact `Tuple[Tuple[int, int], ...]` of `(note,
  volume)` events (matching an updated type hint), NOT `hash()` of it. Used as the sole dedup
  key in `pattern_hash_map` (`compress_patterns`, `pattern_detector.py:807-819`) with no
  equality check on hit, keying on the tuple itself is exact and collision-free — the old 64-bit
  `hash()` could silently merge two different event tuples' `references` and drop a definition.
  Confirm the key stays the raw tuple (not re-wrapped in `hash()`/`str()`) if this path is touched.

### Dimension 9: Loop Detection Correctness
`tracker/loop_manager.py` derives loop points from `pattern_info['positions']`/`length`.
Check `LoopManager.detect_loops` (`loop_manager.py:11-50`): `loop_start = positions[-2]` and
`loop_end = positions[-1] + length` — confirm this can't produce `end <= start` (the jump
table guards it at `loop_manager.py:98`, `149`, but a malformed loop dict elsewhere may not).
Verify `generate_jump_table` keys on `loop_info['end']` (`loop_manager.py:103`, `152`): two
loops sharing an end frame would clobber each other in the jump table. Confirm
`EnhancedLoopManager` (`loop_manager.py:115`) registers tempo state on a key
(`f"loop_{end}_{start}"`, `:130`) that matches what `generate_jump_table` reads back
(`loop_manager.py:156`) — a key-format drift yields `None` tempo_state silently. Since loop
detection consumes `pattern_info['positions']` directly, note that with PAT-01 (#168) and
PAT-04 (#170) now fixed & closed, `positions` is exact-only and non-self-overlapping, so a loop
can no longer anchor on a non-exact-repeat or a self-overlapping match — this class of
downstream corruption is resolved rather than latent. Cross-check against
`tests/test_enhanced_loop_patterns.py`.

## Skeptical Checklist
- [ ] Did you actually run a compress→decompress round-trip on a sample and diff frame-by-frame (Dim 1)? Asserting from the docstring does not count.
- [ ] Do both real producers (`ParallelPatternDetector`, `EnhancedPatternDetector`) and the `--no-patterns` stub emit the same `stats` keys AND the same top-level/inner `variations` shape — all confirmed fixed (#104, #258, #172) — with no regression?
- [ ] Does `references`/`patterns` stay a pure boolean switch into the exporter with zero consumption of the actual reference values (`exporter/exporter_ca65.py:962-971`, #4)? (PAT-01, #168, is fixed so `references` is exact-only, but the exporter still must not consume it.)
- [ ] Does the parallel detector's lack of variations + PAT-05's (#171, closed but documented) anchor-blocking loss change the song vs the sequential detector on the same input, beyond the documented by-design scoring equivalence (#103)?
- [ ] Does the inner serial fallback return the bare patterns dict or the full envelope — and does its caller re-wrap it (Dim 5)?
- [ ] Does large-file sampling feed the *sampled* stream to export (data loss) or only to detection (index alignment) — confirm `frames`, not the sampled sequence, still drives every exported byte?
- [ ] Have `_find_pattern_matches`'s self-overlap (PAT-04, #170) or `_hash_pattern`'s int-as-hash (PAT-07, #173) — both now fixed & closed — regressed since this file was last refreshed?
- [ ] For each finding: re-read the code path, then try to disprove it before including it.

## Output
Write the report to: **`docs/audits/AUDIT_PATTERNS_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — finding counts by severity, the single most important round-trip result (lossless confirmed / mismatch found), and the 3 highest-leverage fixes.
2. **Findings** — base format from `_audit-common.md` plus the `Dimension` field. Lead with any CRITICAL round-trip or data-loss finding.

Then suggest:
```
/audit-publish docs/audits/AUDIT_PATTERNS_<TODAY>.md
```
