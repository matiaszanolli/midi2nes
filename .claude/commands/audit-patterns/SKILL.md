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
  (`:737-767`) produces `compressed_data` + `pattern_refs`. (The former `PatternExporter`/
  `exporter.py` FamiTracker reconstruction path was deleted as dead + frame-space-buggy, #101
  — the `references` are analysis-only and no exporter consumes them, #4, both closed.) Build
  a small synthetic event list with known repeats, run `EnhancedPatternDetector.detect_patterns`
  (`tracker/pattern_detector.py:355`), and confirm every detected pattern's occurrences are
  exact repeats of its events. **Still open**: PAT-01 (#168) — the sequential detector merges
  exact-match positions with *variation* positions (transposed/volume-scaled windows with
  similarity ≥ 0.85) into one `positions`/`references` list (`pattern_detector.py:227`, `:253`,
  stored `:279-286`), but the stored `events` are only the anchor occurrence's events. At every
  variation position the "referenced" content is actually different music — reconstructing
  from `references` today would silently play the wrong notes there. Not yet CRITICAL only
  because nothing reconstructs from `references` (#4); flag any change that starts consuming
  them without first fixing PAT-01. Any note/volume mismatch found by your own round-trip = CRITICAL.
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
  is not coverage. `tests/test_pattern_integration.py:120-137` currently only asserts positions
  are ints, never that the referenced window equals the pattern's stored events — that gap is
  exactly what lets PAT-01 go unnoticed.

### Dimension 2: `pattern_result` Schema Integrity
The detect-patterns contract is a dict with `patterns`, `references`, `stats`, `variations`
(see `_audit-common.md`). Verify every producer returns all four with consistent shapes:
- `ParallelPatternDetector.detect_patterns` (`tracker/pattern_detector_parallel.py:24`),
  its `_empty_result` (`pattern_detector_parallel.py:213-220`), and the no-events early return
  (`pattern_detector_parallel.py:28-34`).
- `EnhancedPatternDetector.detect_patterns` (`tracker/pattern_detector.py:355`) and its
  no-events return (`pattern_detector.py:357-363`).
  (The dead `ThreadedPatternDetector` was removed entirely along with #102's fix — it is no
  longer just "unused", the class and file no longer exist. `grep -rn ThreadedPatternDetector`
  now only matches a doc comment and a regression test asserting it's gone
  (`tests/test_patterns.py:930-936`). This also resolves P-08/#105's race/shape concerns by
  construction, even though the tracking issue is still open on GitHub — re-verify it is
  actually closed as part of publishing this audit.)
- The `--no-patterns` stub built inline in `run_full_pipeline` (`main.py:590-598`): confirmed
  **fixed** (#104) — its `stats` keys (`original_size`, `compressed_size`, `compression_ratio`,
  `unique_patterns`) now match both detectors' schema exactly, and it reports `0` (not `1.0`)
  since direct export applies no compression (#17). One residual, currently-harmless drift: the
  stub omits a top-level `variations` key entirely, while both detectors always include one
  (`{}` or a per-pattern dict). `grep -rn "\['variations'\]"` across `main.py`/`tracker/`/
  `exporter/` finds no reader of `pattern_result['variations']` outside the detectors and
  tests, and `run_detect_patterns` (`main.py:389-393`) drops the key from its JSON artifact
  by design — so this is LOW/doc-only today. Still open: PAT-06 (#172) — where `variations` IS
  populated, its *inner* shape drifts between detectors (`_get_variation_summary`:
  `pattern_detector.py:448-458` emits `{variation_count, transposition_range, volume_range}`;
  `pattern_detector_parallel.py:203-211` emits `{variation_count, exact_matches}`, and can never
  report a nonzero count). Harmless while unread, but the same latent-trap class as the fixed #104.

### Dimension 3: Reference Offsets & Length Correctness
A wrong offset corrupts playback, not just space. Trace position→frame mapping end to end:
- `PatternCompressor.compress_patterns` (`pattern_detector.py:737-767`) fills `pattern_refs`
  with pattern **start positions** (sequence indices) — for the sequential detector these
  include non-exact variation positions merged in with exact ones (PAT-01, #168, open — see
  Dimension 1). These are analysis-only — no exporter consumes them (#4, closed), and the one
  path that did (`PatternExporter`) was deleted as frame-space-buggy (#101, closed). Still
  confirm `len(compressed_data[pattern_id]['events'])` equals the pattern `length` — a mismatch
  would misalign any future consumer.
- The old "occurrence-index passed as pattern offset" bug (#102-adjacent, formerly described
  here as `main.py:352-361`'s `enumerate(positions)` loop) **no longer exists** — that whole
  code path was deleted. `run_full_pipeline` now calls `CA65Exporter.export_tables_with_patterns`
  with a literal empty `{}` for `references` (`main.py:611-617`), and the step-by-step
  `run_export` path (`main.py:301-317`) forwards whatever `references` a `detect-patterns` JSON
  file contains — but `export_tables_with_patterns` itself documents that the `references`
  argument is **never consumed** (`exporter/exporter_ca65.py:866-875`, #4, closed): `patterns`
  truthiness is only a boolean switch between `export_direct_frames` and the MMC3
  macro-bytecode serializer. Confirm this contract still holds before trusting any future PR
  that claims to "wire up" pattern references into the exporter — it would need to fix PAT-01
  first or it would ship the variation-position bug into real ROM bytes.
- Overlap accounting: `_select_best_patterns` (`pattern_detector_parallel.py:163-201`) and the
  selection loop in `pattern_detector.py:265-289` mark `range(pos, pos+length)` used. Confirm
  no two retained patterns can claim the same frame (double-write) and no frame between the
  last pattern end and the song end is silently dropped. Note PAT-04 (#170, open, see
  Dimension 8): the sequential detector's `positions` can already contain a self-overlapping
  match *before* this de-dup step runs, inflating counts independent of the de-dup logic itself.

### Dimension 4: Compression-Ratio & Stats Accuracy
Cosmetic but must not mislead (MEDIUM floor when wrong).
`PatternCompressor.calculate_compression_stats` (`tracker/pattern_detector.py:773-798`)
computes `original_size = Σ len(events)*len(positions)` and
`compressed_size = Σ len(events)`, over detected patterns only. The former "x multiplier vs %
reduction" inconsistency is **fixed** (#17, closed): every print site now uses the same "%
reduction" convention — `main.py:396` (subcommand), `main.py:721` (ROM success banner), and the
`--no-patterns` stub's `0` (`main.py:596`) is coherent with that convention (0% reduction, not
a misleading `1.0`).
Still open: PAT-03 (#169) — frames covered by no pattern contribute to *neither* side of the
ratio, so it describes only the patterned subset, not the whole song (a "96% reduction" can be
reported when most of the song is un-patterned), and it is compounded by PAT-01 (non-exact
variation positions inflating `original_size`) and PAT-04 (self-overlapping matches inflating
it further). The number has no relationship to emitted ROM bytes (actual size reduction comes
from macro/instrument dedup in the bytecode serializer, #4) yet the ROM success banner
(`main.py:721`) prints it right under the ROM size line as if it described the artifact.
Verify any fix passes total event count into `calculate_compression_stats` and/or relabels the
banner line as a detector metric rather than a ROM property.

### Dimension 5: Parallel vs Sequential Equivalence + Documented Fallback
The two detectors' scoring is now **shared** (#103, closed) — verify the fix is complete, not
just that it merged the formulas:
- **Scoring**: both `ParallelPatternDetector._collect_length_candidates`
  (`pattern_detector_parallel.py:279-284`) and `EnhancedPatternDetector.detect_patterns`
  (`pattern_detector.py:224`, `:250`) now call the same module-level `score_pattern`
  (`pattern_detector.py:41-80`), the parallel path always passing `variation_count=0`. This is
  documented as by-design, not a bug: the parallel path's O(n) hash-grouping (#114) finds exact
  repeats only and structurally cannot detect transposed/volume-scaled variations, so it stays
  variation-free. Confirm this is still true and pinned by a test
  (`tests/test_patterns.py`) rather than re-diverging silently.
- Despite shared scoring, PAT-05 (#171, open) shows the two paths can still select
  *structurally different* pattern sets on identical input: the parallel path emits one
  candidate per distinct window (anchored at its first occurrence) and
  `_select_best_patterns` rejects a candidate wholesale if any position overlaps an
  already-selected pattern, so when a winning pattern overlaps only a window's first
  occurrence, the parallel path loses that window's later occurrences entirely, while the
  sequential per-start scan recovers them via a later-anchored candidate. The
  `_collect_length_candidates` docstring's equivalence claim (`pattern_detector_parallel.py:238-249`)
  is therefore wrong in the general case — flag it as doc-rot if not yet corrected.
- **Fallback firing**: `run_full_pipeline` wraps `ParallelPatternDetector` in `try/except` and
  falls back to `EnhancedPatternDetector` (`main.py:557-580`), and inside the parallel detector
  `_detect_patterns_parallel` catches a pool-wide failure and calls `_detect_patterns_serial`
  (`pattern_detector_parallel.py:136-139`). Verify the inner serial fallback returns the raw
  `patterns` dict via `_select_best_patterns` (`pattern_detector_parallel.py:161`) — NOT the
  full `{patterns,references,stats,variations}` envelope — and that its caller (`detect_patterns`,
  `pattern_detector_parallel.py:57-75`) still wraps it via the compressor. If the serial
  fallback's return shape ever bypasses compression/stats, the fallback "fires" but yields a
  malformed result (HIGH).
- Still open: P-09 (#106) — the per-chunk `except Exception … continue`
  (`pattern_detector_parallel.py:131-134`) inside the *whole-pool-succeeded* path silently drops
  a failed chunk's candidate patterns with only a transient `pbar.write` line; unlike the
  whole-pool failure (which has a durable serial fallback), a single-chunk failure has no
  persistent warning and no re-run. Metrics-only today (#4), but should surface a durable
  end-of-run warning.
- The outer `main.py` fallback re-trims events to `DETECTOR_MAX_EVENTS` (1000, a named
  constant — not an ad-hoc "2000" as in older notes) via `sample_events_for_detection`
  (`main.py:571-572`) — confirm this matches the sequential detector's own internal cap
  (`pattern_detector.py:194-197`) so the warning reports the count actually retained, not a
  larger figure the detector would silently re-cut (#100, closed).

### Dimension 6: Multiprocessing Safety (pickle-ability, shared state, pool hygiene)
This dimension changed substantially since the O(n) hash-grouping rewrite (#114, closed) — the
old "entire sequence embedded in every chunk" design is gone:
- `_detect_patterns_parallel` (`pattern_detector_parallel.py:87-144`) now builds one **tiny**
  work chunk per pattern length — just `{'pattern_length': length}`
  (`pattern_detector_parallel.py:98-102`) — and ships the (potentially large) `sequence` and
  `valid_events` to each worker **once** via the `ProcessPoolExecutor(initializer=
  _init_pattern_worker, initargs=(sequence, valid_events))` call (`:112-116`), stashed as
  module globals `_WORKER_SEQUENCE`/`_WORKER_EVENTS` (`:226-235`) instead of being re-pickled
  per chunk × per length. This directly fixes the old memory-blowup / pickle-cost concern —
  confirm it stays true (no code re-introduces per-chunk copies of the full sequence).
  Everything shipped through `initargs` here is a plain list of tuples/dicts — confirm nothing
  non-picklable (a `tempo_map`, a closure, a numpy array) is added to that call in future
  changes, since `EnhancedTempoMap` itself is deliberately kept out of the worker payload.
- Confirm `_detect_patterns_worker` (`pattern_detector_parallel.py:300-308`) and
  `_init_pattern_worker` (`:230-235`) are module-level (picklable/importable by the child
  process) and that `_collect_length_candidates` (`:238-297`), the actual per-length work, reads
  the globals but mutates no shared state across workers.
- The dead `ThreadedPatternDetector` (formerly a second, thread-based, shared-`patterns`-dict
  race) is confirmed **removed** (#102, closed) — `grep -rn ThreadedPatternDetector` matches
  only a doc comment in `pattern_detector.py:12` and a regression test
  (`tests/test_patterns.py:930-936`) asserting it stays gone. No shared mutable state remains
  to audit here.

### Dimension 7: Large-File Sampling Not Dropping Musical Content
Sampling must not silently change the song. The old "three inconsistent limits" defect is
**fixed** (#102, closed) — there are now exactly two, sharing one implementation:
- `LARGE_FILE_THRESHOLD = 10000` (`main.py:550`) only prints advice — confirm it does not
  itself drop events.
- Both detectors now call the same module-level `sample_events_for_detection`
  (`tracker/pattern_detector.py:26-38`, uniform `np.linspace` sampling — not a head cut).
  `ParallelPatternDetector.detect_patterns` (`pattern_detector_parallel.py:47`) samples to
  `MAX_PATTERN_EVENTS = 15000` (`pattern_detector.py:16`); the sequential
  `PatternDetector.detect_patterns` (`pattern_detector.py:194-197`) samples to
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
  `pattern_detector_parallel.py:15`), but all three real entry points now consistently override
  `max_pattern_length` to the same named constants — `PATTERN_MIN_LENGTH = 3` /
  `PATTERN_MAX_LENGTH = 12` (`main.py:33-34`) — used by `run_detect_patterns`
  (`main.py:358-359`), the default parallel path (`main.py:559`), and its sequential fallback
  (`main.py:565`). This resolves the old "`detect-patterns` alone uses a default max of 32"
  drift; confirm all three call sites still reference the shared constants rather than a
  hardcoded literal before trusting this. Bounds are honored via
  `range(min, min(max, len(sequence))+1)` in both detectors — confirm a `max < min` or
  `len(sequence) < min` still can't produce a garbage/negative-range loop.
- `_find_pattern_matches` (`pattern_detector.py:291-306`, sequential detector only — the
  parallel worker no longer mirrors it; see below) intends to "skip the length of the pattern
  to avoid overlaps" (comment at `:302`) but **PAT-04 (#170, open)**: the scan for matches after
  the anchor starts at `start_pos + 1` (`:297`) instead of `start_pos + pattern_len`, so in
  self-similar runs (period < pattern length) the first found "match" can overlap the anchor
  window itself. Only *subsequent* matches correctly skip `pattern_len`. This inflates
  `exact_matches` counts (feeding `score_pattern` and `calculate_compression_stats` too high,
  PAT-03) and makes the sequential detector diverge from the parallel path on the same input
  (reproduced: 12 identical notes, length 4 → sequential `[0, 1, 5]` vs parallel `[0, 4, 8]`).
  No round-trip corruption results (overlapping windows of identical content are still
  value-consistent), but the divergence and stat inflation are real. Compare against the
  parallel detector's correct greedy in `_collect_length_candidates`
  (`pattern_detector_parallel.py:266-274`, `next_free` logic) — the two are NOT a "mirror" of
  each other as older notes claimed; they are different algorithms (O(n²) per-start scan vs
  O(n) hash-grouped windows, #114) that happen to intend the same non-overlap invariant.
  PAT-05 (#171, open, see Dimension 5) further shows the parallel algorithm's own non-overlap
  handling can lose entirely-valid later occurrences that the sequential scan would recover.
- PAT-07 (#173, open): `PatternCompressor._hash_pattern` (`pattern_detector.py:769-771`) returns
  `hash(tuple(...))` — a 64-bit int — despite its docstring/type-hint claiming a unique
  `str`. Used as the sole dedup key in `pattern_hash_map` (`compress_patterns`,
  `pattern_detector.py:745-757`) with no equality check on hit, so a hash collision between two
  different event tuples would silently merge the second pattern's `positions` into the first's
  `references` and drop its own definition. Astronomically unlikely per song, but the fix (key
  on the tuple itself) is free — flag as LOW and easy to close alongside PAT-01/PAT-04 if
  touching this file.

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
detection consumes `pattern_info['positions']` directly, PAT-01 (#168) and PAT-04 (#170) both
mean a loop can anchor on a non-exact-repeat or a self-overlapping match today — note this as
a downstream consequence rather than re-deriving it. Cross-check against
`tests/test_enhanced_loop_patterns.py`.

## Skeptical Checklist
- [ ] Did you actually run a compress→decompress round-trip on a sample and diff frame-by-frame (Dim 1)? Asserting from the docstring does not count.
- [ ] Do both real producers (`ParallelPatternDetector`, `EnhancedPatternDetector`) and the `--no-patterns` stub emit the same `stats` keys — confirmed fixed (#104) — and does the `variations` inner shape still drift (PAT-06, #172)?
- [ ] Does `references`/`patterns` stay a pure boolean switch into the exporter with zero consumption of the actual reference values (`exporter/exporter_ca65.py:866-875`, #4), or has a change started reading them without first fixing PAT-01 (#168)?
- [ ] Does the parallel detector's lack of variations + PAT-05's (#171) anchor-blocking loss change the song vs the sequential detector on the same input, beyond the documented by-design scoring equivalence (#103)?
- [ ] Does the inner serial fallback return the bare patterns dict or the full envelope — and does its caller re-wrap it (Dim 5)?
- [ ] Does large-file sampling feed the *sampled* stream to export (data loss) or only to detection (index alignment) — confirm `frames`, not the sampled sequence, still drives every exported byte?
- [ ] Is `_find_pattern_matches`'s self-overlap (PAT-04, #170) or `_hash_pattern`'s int-as-hash (PAT-07, #173) still present, or has either been fixed since this file was last refreshed?
- [ ] For each finding: re-read the code path, then try to disprove it before including it.

## Output
Write the report to: **`docs/audits/AUDIT_PATTERNS_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — finding counts by severity, the single most important round-trip result (lossless confirmed / mismatch found), and the 3 highest-leverage fixes.
2. **Findings** — base format from `_audit-common.md` plus the `Dimension` field. Lead with any CRITICAL round-trip or data-loss finding.

Then suggest:
```
/audit-publish docs/audits/AUDIT_PATTERNS_<TODAY>.md
```
