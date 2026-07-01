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
  produces `compressed_data` + `pattern_refs`. (The former `PatternExporter`/`exporter.py`
  FamiTracker reconstruction path was deleted as dead + frame-space-buggy, #101 — the
  `references` are analysis-only and no exporter consumes them, #4.) Build a small synthetic
  event list with known repeats, run `EnhancedPatternDetector.detect_patterns`
  (`tracker/pattern_detector.py`), and confirm every detected pattern's occurrences are exact
  repeats of its events. Any note/volume mismatch = CRITICAL.
- The RLE/delta path: `exporter/compression.py` `CompressionEngine.compress_pattern` ↔
  `decompress_pattern`. Round-trip a pattern that exercises RLE runs, delta runs, and raw
  events together. Watch the delta decoder (`compression.py:93-107`): it mutates a running
  event and only sums keys present in the delta — confirm a key that is *absent* from a delta
  (because its diff was 0) is preserved, not reset. Confirm `_can_delta_compress`
  (`compression.py:154-177`) and `_create_delta_block` (`compression.py:179-200`) agree on the
  `numeric_keys` set so no field silently drifts.
- Existing coverage to check (and distrust if thin): `tests/test_compression.py`,
  `tests/test_compression_integration.py`,
  `tests/test_pattern_integration.py`. A round-trip with no asserted frame-by-frame equality
  is not coverage.

### Dimension 2: `pattern_result` Schema Integrity
The detect-patterns contract is a dict with `patterns`, `references`, `stats`, `variations`
(see `_audit-common.md`). Verify every producer returns all four with consistent shapes:
- `ParallelPatternDetector.detect_patterns` (`tracker/pattern_detector_parallel.py:27`),
  its `_empty_result` (`pattern_detector_parallel.py:249`), and the no-events early return
  (`pattern_detector_parallel.py:31-37`).
- `EnhancedPatternDetector.detect_patterns` (`tracker/pattern_detector.py:318`) and its
  no-events return (`pattern_detector.py:320-326`).
  (The dead `ThreadedPatternDetector` was removed, #102 — only the parallel and
  sequential detectors remain.)
- The `--no-patterns` stub built inline in `run_full_pipeline` (`main.py:332-341`): confirm
  its `stats` keys (`original_events`, `compressed_size`, `patterns_found`,
  `compression_ratio`) match what downstream and `run_detect_patterns` read. The detectors emit
  `original_size`/`unique_patterns`/`patterns_found`-absent stats while the stub emits
  `original_events`/`patterns_found` — a stats-key drift between producers is at least MEDIUM
  (misleading), HIGH if a consumer KeyErrors on it. grep `stats[` and `['stats']` across
  `main.py` and `debug/` to find every reader.

### Dimension 3: Reference Offsets & Length Correctness
A wrong offset corrupts playback, not just space. Trace position→frame mapping end to end:
- `PatternCompressor.compress_patterns` (`pattern_detector.py:715-728`) fills `pattern_refs`
  with pattern **start positions** (sequence indices). These are analysis-only — no exporter
  consumes them (#4), and the one path that did (`PatternExporter`) was deleted as
  frame-space-buggy (#101). Still confirm `len(compressed_data[pattern_id]['events'])` equals
  the pattern `length` — a mismatch would misalign any future consumer.
- The CA65 conversion in `run_full_pipeline` (`main.py:352-361`): it iterates
  `enumerate(positions)` and passes the loop index `i` as the pattern offset
  (`ca65_references[str(actual_frame)] = (pattern_id, i)`). `i` is the *occurrence index*, not
  the within-pattern offset — verify what `CA65Exporter.export_tables_with_patterns`
  (`exporter/exporter_ca65.py`) expects in that tuple slot. If the exporter reads it as an
  intra-pattern offset, this is a correctness bug (CRITICAL if it changes playback, HIGH if it
  only mis-indexes references). Re-read both sides before concluding.
- Overlap accounting: `_select_best_patterns` (`pattern_detector_parallel.py:175-203`) and the
  selection loop in `pattern_detector.py:234-249` mark `range(pos, pos+length)` used. Confirm
  no two retained patterns can claim the same frame (double-write) and no frame between the
  last pattern end and the song end is silently dropped.

### Dimension 4: Compression-Ratio & Stats Accuracy
Cosmetic but must not mislead (MEDIUM floor when wrong).
`PatternCompressor.calculate_compression_stats` (`tracker/pattern_detector.py:736-755`)
computes `original_size = Σ len(events)*len(positions)` and
`compressed_size = Σ len(events)`. Check: does this count un-patterned frames at all (frames
covered by no pattern contribute nothing to either side, so the ratio describes only the
patterned subset, not the whole song)? Is `compression_ratio` a percentage here but printed
with an `x` suffix elsewhere (`main.py:484` prints `...:.2f}x`; `main.py:157` prints raw)?
A ratio that reads "95.86x" in one place and "95.86%" in another is a misleading-stat finding.
Confirm the `--no-patterns` ratio of `1.0` (`main.py:336`) is coherent with the percentage
convention the detectors use (they would emit `0`, not `1.0`, for no compression).

### Dimension 5: Parallel vs Sequential Equivalence + Documented Fallback
The two detectors must produce equivalent results, and the fallback must actually fire.
- **Equivalence**: `ParallelPatternDetector` (`tracker/pattern_detector_parallel.py`) scores
  with `_score_pattern` (`pattern_detector_parallel.py:221-237`) and the inline worker copy
  (`pattern_detector_parallel.py:294-302`); `EnhancedPatternDetector` uses a *different*
  `score_pattern` with extra length tiers and an `exact_bonus` (`pattern_detector.py:127-166`).
  The parallel path also does **not** detect variations (`_select_best_patterns` sets
  `'variations': []`) while the sequential path does. Flag any claim that the two are
  interchangeable — divergent pattern selection between detectors is at least MEDIUM, HIGH if
  it means the default pipeline (parallel) silently produces worse/different music than the
  documented sequential behavior. The scoring duplication itself is a tech-debt cross-ref.
- **Fallback firing**: `run_full_pipeline` wraps `ParallelPatternDetector` in `try/except`
  and falls back to `EnhancedPatternDetector` (`main.py:314-327`), and inside the parallel
  detector `_detect_patterns_parallel` catches a pool failure and calls
  `_detect_patterns_serial` (`pattern_detector_parallel.py:139-142`). Verify the inner serial
  fallback returns the raw `patterns` dict (`_select_best_patterns`) — NOT the full
  `{patterns,references,stats,variations}` envelope — and that its caller still wraps it via
  the compressor (`pattern_detector_parallel.py:62-80`). If the serial fallback's return shape
  bypasses compression/stats, the fallback "fires" but yields a malformed result (HIGH). Also
  confirm the per-chunk `except` (`pattern_detector_parallel.py:134-137`) that `continue`s on a
  failed chunk cannot silently drop a whole pattern length without surfacing it.
- The outer-`main.py` fallback also re-trims events to **2000** (`main.py:324-326`) — confirm
  this conservative limit is documented and that the resulting smaller pattern set is still a
  correct (if less compressed) round-trip, not a corrupt one.

### Dimension 6: Multiprocessing Safety (pickle-ability, shared state, pool hygiene)
`ParallelPatternDetector` submits `work_chunk` dicts to a `ProcessPoolExecutor`
(`pattern_detector_parallel.py:118-147`). Each chunk embeds the **entire** `sequence` and
`events` lists (`pattern_detector_parallel.py:104-111`) — confirm everything in a chunk is
picklable (plain dicts/tuples/ints here; flag if any non-picklable object — a `tempo_map`,
a closure, a numpy array — leaks into a chunk). Check the memory blow-up of copying the full
sequence into every chunk × every pattern length (this is a perf cross-ref, but a chunk too
large to pickle is a correctness failure that should hit the fallback). Confirm
`_detect_patterns_worker` (`pattern_detector_parallel.py:259`) is module-level (picklable) and
mutates no shared state. (The thread-based `ThreadedPatternDetector` was removed as dead,
#102, so there is no longer a shared-`patterns`-dict thread-race to check here.)

### Dimension 7: Large-File Sampling Not Dropping Musical Content
Sampling must not silently change the song.
- `LARGE_FILE_THRESHOLD = 10000` (`main.py:307`) only prints advice — confirm it does not
  itself drop events.
- `ParallelPatternDetector` hard-samples to `MAX_EVENTS = 15000` via `np.linspace`
  (`pattern_detector_parallel.py:51-59`). This *decimates* the event stream used for pattern
  detection. Trace whether the sampled `valid_events` is what later feeds `references`/frame
  reconstruction: if the export uses the sampled stream, the song is permanently altered
  (potential CRITICAL data loss); if patterns are detected on the sample but applied back to
  the full stream, verify the position indices still line up (off-by-many).
- `EnhancedPatternDetector` (via `PatternDetector.detect_patterns`) uniformly samples to
  `DETECTOR_MAX_EVENTS = 1000` via `sample_events_for_detection` (`pattern_detector.py`, #100)
  — the O(n^2) sequential cap, lower than the parallel 15000 by design. Post-#102 there are
  exactly TWO caps (15000 parallel / 1000 sequential), one per detector complexity class —
  they don't shadow, they bound different algorithms; the old third limit (the removed
  `ThreadedPatternDetector` 2000-stride) is gone. Any path that drops events it then claims
  to have compressed losslessly is CRITICAL.

### Dimension 8: Pattern-Length Bounds & Match Semantics
- `min_pattern_length` / `max_pattern_length` defaults differ by entry point: detectors
  default `3..32` (`pattern_detector.py:8`, `pattern_detector_parallel.py:18`) but the pipeline
  constructs them with `max_pattern_length=12` (`main.py:316`, `main.py:322`) and
  `run_detect_patterns` uses only `min_pattern_length=3` (`main.py:130`, default max 32).
  Confirm the bounds are honored (`range(min, min(max, len)+1)`) and that a `max < min` or
  `len(sequence) < min` can't produce an empty/garbage loop.
- `_find_pattern_matches` (`pattern_detector.py:254-269`, mirrored in the parallel worker and
  `_find_matches`) advances `pos += pattern_len` on a hit to avoid overlaps — verify this can't
  miss a legitimately-overlapping repeat in a way that changes which frames get patterned
  (affects round-trip coverage, not just compression).

### Dimension 9: Loop Detection Correctness
`tracker/loop_manager.py` derives loop points from `pattern_info['positions']`/`length`.
Check `LoopManager.detect_loops` (`loop_manager.py:11-50`): `loop_start = positions[-2]` and
`loop_end = positions[-1] + length` — confirm this can't produce `end <= start` (the jump
table guards it at `loop_manager.py:98`, `149`, but a malformed loop dict elsewhere may not).
Verify `generate_jump_table` keys on `loop_info['end']` (`loop_manager.py:103`, `152`): two
loops sharing an end frame would clobber each other in the jump table. Confirm
`EnhancedLoopManager` (`loop_manager.py:115`) registers tempo state on a key
(`f"loop_{end}_{start}"`) that matches what `generate_jump_table` reads back
(`loop_manager.py:156`) — a key-format drift yields `None` tempo_state silently. Cross-check
against `tests/test_enhanced_loop_patterns.py`.

## Skeptical Checklist
- [ ] Did you actually run a compress→decompress round-trip on a sample and diff frame-by-frame (Dim 1)? Asserting from the docstring does not count.
- [ ] Do all four producers (`Parallel`, `Enhanced`, `Threaded`, `--no-patterns` stub) emit the same `stats` keys, or did you grep every reader to prove a drift is harmless?
- [ ] Is the `i` passed as the CA65 offset (`main.py:357`) the within-pattern offset the exporter expects, or the occurrence index? Read `exporter/exporter_ca65.py` to confirm.
- [ ] Does the parallel detector's lack of variations + different scoring change the song vs the sequential detector on the same input?
- [ ] Does the inner serial fallback return the bare patterns dict or the full envelope — and does its caller re-wrap it?
- [ ] Does large-file sampling feed the *sampled* stream to export (data loss) or only to detection (index alignment)?
- [ ] For each finding: re-read the code path, then try to disprove it before including it.

## Output
Write the report to: **`docs/audits/AUDIT_PATTERNS_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — finding counts by severity, the single most important round-trip result (lossless confirmed / mismatch found), and the 3 highest-leverage fixes.
2. **Findings** — base format from `_audit-common.md` plus the `Dimension` field. Lead with any CRITICAL round-trip or data-loss finding.

Then suggest:
```
/audit-publish docs/audits/AUDIT_PATTERNS_<TODAY>.md
```
