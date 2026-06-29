# Pattern Detection & Compression Audit — 2026-06-29

Audit of the pattern-detection and compression subsystem per
`.claude/commands/audit-patterns/SKILL.md`. Severity floors from
`.claude/commands/_audit-severity.md`; dedup against `/tmp/audit/issues.json`
(22 open) and `docs/audits/` prior reports.

## Summary

**Round-trip result: LOSSLESS confirmed on both live-relevant compression paths.**
I ran real compress → decompress round-trips with frame-by-frame diffs:

- `exporter/compression.py` `CompressionEngine.compress_pattern`/`decompress_pattern`
  round-trips **losslessly** across RLE runs, delta runs (including the absent-key
  case the SKILL flags — a key whose diff was 0 is preserved, not reset), mixed
  raw/delta, and extra-non-numeric-key events. No CRITICAL.
- The detector → `PatternExporter.expand_to_frames()` path round-trips correctly
  **when frame numbers equal sequence indices**, but reconstructs in *index space*,
  not *frame space*, for sparse frames. This is a latent contract bug — but that
  path is **dead** in the live pipeline (`references` are analysis-only; CA65 export
  ignores them; the only consumer is the never-called FamiTracker exporter), so it
  is MEDIUM, not CRITICAL.

There is **no** CRITICAL round-trip or data-corruption finding. The headline risk
the SKILL was written against (Dim 3: `references`/CA65-offset corrupting playback)
has been **closed by design** — `export_tables_with_patterns` no longer consumes
`references` (issue #4, now closed; verified in place at `exporter_ca65.py:832-844`
and `main.py:516-528`).

### Finding counts
- CRITICAL: 0
- HIGH: 1
- MEDIUM: 4
- LOW: 4

### 3 highest-leverage fixes
1. **P-01 (HIGH)** — Remove or raise the hard `MAX_EVENTS = 1000` *head-truncation*
   in `PatternDetector.detect_patterns` (`pattern_detector.py:143-147`). It silently
   drops the song's entire tail and defeats the shared 15000 `np.linspace` sampling
   that issues #21/#10 added — and the pipeline's own INCOMPLETE warning understates
   the loss (claims "2,000", detector actually uses 1,000).
2. **P-04 (MEDIUM)** — `parser_fast.py:128-159` runs full O(n²) pattern + loop
   detection on every parse, but the resulting `metadata` (patterns/loops/jump_table)
   is **never read** by the full pipeline; delete or gate it.
3. **P-02 (MEDIUM)** — `PatternExporter` treats `pattern_refs` values as frame numbers
   though the detector emits sequence indices; fix the index→frame mapping (or delete
   the dead FamiTracker path that is its only consumer).

---

## Findings

### P-01: `EnhancedPatternDetector` hard-truncates to the first 1000 events, defeating the shared 15000-event sampling and understating the loss
- **Severity**: HIGH
- **Dimension**: 7 (Large-File Sampling) / 5 (Fallback)
- **Location**: `tracker/pattern_detector.py:142-147`; pipeline fallback `main.py:482-495`; subcommand `main.py:295-304`
- **Status**: NEW (partial regression-gap of #21 / #10, both CLOSED)
- **Description**: Issues #21 (F-09) and #10 (F-04) were fixed by routing every entry
  point through `sample_events_for_detection` (uniform `np.linspace` to
  `MAX_PATTERN_EVENTS = 15000`) and emitting a "ROM is INCOMPLETE" warning. But
  `PatternDetector.detect_patterns` — the shared base reached by **every**
  `EnhancedPatternDetector` path (the `detect-patterns` subcommand, the pipeline's
  sequential fallback, and `parser_fast`) — still does an internal, *unconditional*
  `sequence = sequence[:MAX_EVENTS]` with `MAX_EVENTS = 1000`. This is a **head cut**,
  not a uniform sample, so the back half of the song is dropped. The 15000-event
  shared sampling is therefore a no-op for `EnhancedPatternDetector` (1000 < 15000),
  and the pipeline's `pattern_loss_warning` (`main.py:489-493`) tells the user it
  sampled "down to 2,000 events" while the detector actually keeps only the first
  1,000 — the warning understates the true loss and reports a wrong figure.
- **Evidence**: Reproduced. Feeding 2000 events to
  `EnhancedPatternDetector(max_pattern_length=12)` prints
  `Warning: Large sequence (2000 events), limiting to 1000 for performance`; the
  progress bar runs `9935` iterations (== Σ(1000−L+1) for L∈3..12, i.e. 1000 events),
  and the max sequence index covered by any detected pattern is **996** — indices
  1000–1999 are entirely absent. The pipeline banner would have said "2,000".
- **Impact**: For any track/song with >1000 detection events, pattern detection (and
  the loop detection that feeds off it) sees only the head. On the default macro path
  the *frames* are still exported in full (so the ROM is not truncated today, because
  `patterns` is only a boolean switch — #4), but: (a) compression quality silently
  collapses on long songs, (b) the user-facing INCOMPLETE warning is numerically
  wrong, and (c) the moment anyone wires `references`→bytes (the documented intended
  design) this becomes silent song loss. Blast radius: every long MIDI, all three
  `EnhancedPatternDetector` callers.
- **Related**: #21 (F-09, closed), #10 (F-04, closed), #46 (REG-06), P-04, P-05.
- **Suggested Fix**: Replace the bare `sequence[:1000]` head-cut with the shared
  `sample_events_for_detection` (uniform) and a single, accurate limit; or raise it
  to match the 15000 policy. Make the pipeline's `pattern_loss_warning` print the
  detector's *actual* retained count, not the pre-detector sample size.

---

### P-02: `PatternExporter` maps `pattern_refs` values as frame numbers, but the detector emits sequence indices (index-space vs frame-space mismatch)
- **Severity**: MEDIUM
- **Dimension**: 3 (Reference Offsets) / 1 (Round-Trip)
- **Location**: `exporter/pattern_exporter.py:12-20,36-46`; producer `tracker/pattern_detector.py:715-751`
- **Status**: NEW
- **Description**: `_create_pattern_map` lays each pattern's events at
  `start_pos + offset` and `expand_to_frames` iterates `range(max_frame + 1)`, i.e. it
  reconstructs a *contiguous index-space* frame stream keyed by the `positions` values.
  Those `positions` come from `compress_patterns` and are **sequence indices** (0,3,6,…),
  not the original `frame` numbers (which can be sparse, e.g. 0,10,20,… at 60 fps with
  rests). A round-trip therefore reproduces the original notes/volumes but at the wrong
  frame keys whenever frames are not densely packed from 0.
- **Evidence**: Reproduced. With events at frames `0,10,20,…110`, the detector returns
  `references = {'pattern_0': [0,3,6,9]}` and `expand_to_frames()` yields keys
  `0..11`, while the input frames were `0,10,…110`. The existing test
  `tests/test_pattern_exporter.py:105-127` *encodes* this index-space assumption
  (refs `[0,5]` → frames `0,1,5,6`), so it passes while masking the contract gap.
- **Impact**: Latent. The only consumer of `PatternExporter` is
  `exporter/exporter.py:generate_famitracker_txt_with_patterns`, which is **imported
  but never invoked** (the `export --format` choices are `nsf`/`ca65` only; the
  FamiTracker text path is dead). So no live ROM is affected today. If the FamiTracker
  exporter were ever wired up, every note would land on the wrong row for sparse input.
- **Related**: #4 (F-01, closed — references made analysis-only), P-08.
- **Suggested Fix**: Either (a) delete the dead `PatternExporter`/`exporter.py`
  FamiTracker path, or (b) carry the original `frame` numbers in `positions`/events and
  key `expand_to_frames` on real frames. Add a round-trip test with sparse frame numbers.

---

### P-03: Three inconsistent event limits across detectors (1000 / 2000 / 15000), only one of which actually binds
- **Severity**: MEDIUM
- **Dimension**: 7 (Large-File Sampling consistency)
- **Location**: `tracker/pattern_detector.py:13` (15000) & `:143` (1000); `tracker/pattern_detector_parallel.py:49` (15000) & `:379-382` (2000)
- **Status**: NEW
- **Description**: The SKILL flags three different limits. Current state:
  `sample_events_for_detection` = 15000 (shared, uniform); `PatternDetector` internal
  hard cut = 1000 (head); `ThreadedPatternDetector` stride = 2000; pipeline fallback
  `FALLBACK_MAX_EVENTS` = 2000. Because the 1000 head-cut (P-01) sits *below* the 15000
  sample and runs on the same `EnhancedPatternDetector`, the effective binding limit for
  the sequential path is 1000, not the documented 15000 — the limits don't compose, they
  shadow each other.
- **Evidence**: `MAX_PATTERN_EVENTS = 15000` (`pattern_detector.py:13`) vs
  `MAX_EVENTS = 1000` (`:143`); `ParallelPatternDetector` samples to 15000
  (`:49`) but its sequential fallback runs unbounded on the already-sampled set;
  `ThreadedPatternDetector` strides to 2000 (`:379-382`).
- **Impact**: Confusing, undocumented decimation behavior; the "15000 shared policy"
  comment (`pattern_detector.py:8-13`) is misleading because 1000 wins. Inconsistent
  results between the parallel default (15000) and the sequential fallback / subcommand
  (effectively 1000).
- **Related**: P-01, #21 (closed).
- **Suggested Fix**: Pick one policy (the shared `sample_events_for_detection`) and route
  all three detectors through it; delete the per-detector hard caps.

---

### P-04: `parser_fast` runs full pattern + loop detection on every parse, but the result is discarded by the full pipeline
- **Severity**: MEDIUM
- **Dimension**: 9 (Loop Detection) / cross-ref performance
- **Location**: `tracker/parser_fast.py:128-159`; consumer check `main.py:419-445`
- **Status**: NEW
- **Description**: `parse_midi_to_frames` constructs an `EnhancedPatternDetector` and
  `EnhancedLoopManager` and computes `patterns`, `pattern_refs`, `compression_stats`,
  `loops`, and `jump_table` per track, returning them under `metadata`. The full
  pipeline (`run_full_pipeline`) consumes only `midi_data["events"]` and re-runs pattern
  detection from scratch on the frames (`main.py:474-478`). A grep of every downstream
  reader shows nothing reads `midi_data["metadata"]` in the ROM path — the loop and
  jump-table computation never reaches the ROM.
- **Evidence**: `main.py:431,440` use only `midi_data["events"]`; no
  `["metadata"]`/`jump_table`/`loops` reader exists outside `parser_fast` itself. The
  "120x faster parser" therefore pays an O(n²) pattern-detection tax it throws away.
- **Impact**: Wasted compute on every conversion (the slowest stage, run twice — once
  discarded). Also moots the Dim-9 loop-correctness concerns (jump_table keyed on
  `loop_info['end']` could clobber on a shared end, but it never affects a ROM).
- **Related**: P-01 (the discarded detection also hits the 1000 cap), P-05.
- **Suggested Fix**: Gate the pattern/loop block in `parser_fast` behind a flag (off for
  the ROM pipeline), or remove it and have the `parse` subcommand request metadata
  explicitly. Until then, the loop/jump_table code is effectively dead for ROM output.

---

### P-05: Parallel and sequential detectors are not equivalent — different scoring and no variation detection in the parallel (default) path
- **Severity**: MEDIUM
- **Dimension**: 5 (Parallel vs Sequential Equivalence)
- **Location**: `tracker/pattern_detector_parallel.py:218-234` & worker `:290-309` (no variations, simpler score) vs `tracker/pattern_detector.py:150-189` (length tiers + `exact_bonus` + variation detection)
- **Status**: NEW
- **Description**: The default pipeline uses `ParallelPatternDetector`, which scores with
  a simplified `_score_pattern` (linear `length*2.0` bonus, no length tiers, no
  `exact_bonus`) and sets `'variations': []` unconditionally in `_select_best_patterns`
  (`:196`). `EnhancedPatternDetector` (the fallback and `detect-patterns` subcommand)
  uses a richer score with exponential length bonuses and full variation detection. For
  the same input the two select **different** pattern sets. The `_get_variation_summary`
  in the parallel path reports `variation_count: 0` for every pattern.
- **Evidence**: Compare `_score_pattern` (`pattern_detector_parallel.py:218-234`) with
  `score_pattern` (`pattern_detector.py:150-189`); parallel `variations: []` at `:196`;
  variation summary at `:236-244`.
- **Impact**: Because `patterns` is only a boolean switch in CA65 export (#4), neither
  scoring nor variations change the emitted bytes today — so this is metrics-only
  divergence (different `compression_ratio`/variation counts between a default run and a
  `detect-patterns` run on the same data), not wrong music. MEDIUM (misleading stats /
  scoring duplication), would rise to HIGH if `references`→bytes is ever wired.
- **Related**: #46 (REG-06, open — parallel path untested), #4 (closed), P-09.
- **Suggested Fix**: Either share a single scoring function between the two detectors
  (the duplication is also a tech-debt cross-ref) or document that the parallel path is
  intentionally coarser and variation-free.

---

### P-06: No-patterns stub `stats` keys drift from the detectors' keys (dead keys, but a latent KeyError trap)
- **Severity**: LOW
- **Dimension**: 2 (Schema Integrity)
- **Location**: stub `main.py:500-509`; detectors `tracker/pattern_detector.py:773-778`, `tracker/pattern_detector_parallel.py:34,251`
- **Status**: NEW
- **Description**: The `--no-patterns` stub emits `stats` with keys
  `compression_ratio, original_events, compressed_size, patterns_found`; the detectors
  emit `compression_ratio, original_size, compressed_size, unique_patterns`. The
  `original_events`/`patterns_found` keys exist nowhere else and `original_size`/
  `unique_patterns` are absent from the stub. A grep of every reader
  (`main.py`, `debug/`, `nes/`) shows only `compression_ratio` is ever read, so the
  drift is currently harmless — but the divergent shapes are a trap for any future
  consumer that assumes one schema.
- **Evidence**: Reader grep returns only `pattern_result['stats']['compression_ratio']`
  (`main.py:314,626`); stub keys at `main.py:505-507` are written but never read.
- **Impact**: None today (dead keys). LOW maintainability/consistency risk.
- **Related**: F-07/#17, P-07.
- **Suggested Fix**: Make the stub emit the same four keys as the detectors
  (`original_size`, `unique_patterns`), dropping the bespoke `original_events`/
  `patterns_found`.

---

### P-07: `compression_ratio` is a percentage but printed with an `x` suffix; `--no-patterns` stub uses `1.0`
- **Severity**: LOW
- **Dimension**: 4 (Compression-Ratio & Stats Accuracy)
- **Location**: `tracker/pattern_detector.py:769-771` (×100 percentage); printed `main.py:626` (`{…:.2f}x`) and `main.py:314` (raw); stub `main.py:504` (`1.0`)
- **Status**: **Existing: #17** (F-07, OPEN)
- **Description**: `calculate_compression_stats` returns `compression_ratio` as a
  reduction percentage in [0,100], but the success banner prints it with an `x`
  multiplier suffix, so "75% reduction" displays as "75.00x". The `--no-patterns` stub's
  `1.0` reads as "1.00x" (≈ no compression) which is incoherent with the percentage
  convention (a detector would emit `0` for no compression). Confirmed still present and
  unchanged from the issue text.
- **Evidence**: `pattern_detector.py:771` `* 100`; `main.py:626` `…:.2f}x`;
  round-trip test above printed `compression_ratio: 75.0` for a 75%-reduction case.
- **Impact**: Cosmetic but misleading (CLAUDE.md's "95.86x" is really ≈96% reduction).
  Display-only.
- **Related**: #17 (open, dedup — not re-reporting), P-06.
- **Suggested Fix**: Already specified in #17 (print `%` or convert to a true
  `original/compressed` multiplier; fix both print sites + the stub's `1.0`).

---

### P-08: `ThreadedPatternDetector` is dead code with an unlocked `len(patterns)` ID race and unconditional empty `variations`
- **Severity**: LOW
- **Dimension**: 6 (Multiprocessing Safety) / 2 (Schema)
- **Location**: `tracker/pattern_detector_parallel.py:314-441` (esp. `:396` `f"pattern_{len(patterns)}_{start}"` read outside `pattern_lock`, `:361` `'variations': {}`)
- **Status**: NEW
- **Description**: `ThreadedPatternDetector` builds pattern IDs from `len(patterns)`
  read *before* acquiring `pattern_lock`, so concurrent threads can derive colliding
  base IDs (mitigated only by the appended `_{start}`/per-length differences, not
  guaranteed unique). It also returns `'variations': {}` unconditionally where the other
  producers return a per-pattern dict. However, a grep shows **no non-test caller** of
  `ThreadedPatternDetector` anywhere in the live tree — it is dead.
- **Evidence**: `grep ThreadedPatternDetector` outside its class/tests returns nothing.
- **Impact**: None today (dead). LOW.
- **Related**: P-05, #46.
- **Suggested Fix**: Delete `ThreadedPatternDetector` (and its test) or, if retained,
  move the `len(patterns)` read inside the lock and return a real `variations` shape.

---

### P-09: Per-chunk `except … continue` in the parallel pool can silently drop a length's candidates with only a transient tqdm note
- **Severity**: LOW
- **Dimension**: 5 (Fallback) / 6 (Pool hygiene)
- **Location**: `tracker/pattern_detector_parallel.py:125-134`
- **Status**: NEW
- **Description**: A failed/timed-out chunk (`future.result(timeout=30)`) is caught,
  written to the tqdm bar via `pbar.write`, and `continue`d — its candidate patterns are
  dropped while the run reports success. Unlike the *whole-pool* failure (`:136-139`,
  which falls back to serial), a single-chunk failure has no fallback and no persistent
  warning. Because patterns are metrics-only in export (#4), this degrades compression
  quality but does not corrupt frames; still, a transient stderr line is not a durable
  signal that detection was partial.
- **Evidence**: `:131-134` `except Exception … pbar.write(…) … continue`; no
  re-raise, no fallback, no summary count of failed chunks.
- **Impact**: Silent partial pattern detection on chunk failure; LOW today (no byte-level
  effect), would matter once references drive output.
- **Related**: P-05, #46 (REG-06 — parallel path untested).
- **Suggested Fix**: Count failed chunks and surface a single end-of-run warning; if any
  chunk for a given length fails, consider re-running that length serially.

---

## Dimensions checked with no new finding

- **Dim 1 (round-trip)**: `CompressionEngine` lossless on all tested cases (RLE, delta,
  absent-key, mixed, extra-key) — see Summary. The detector→`PatternExporter` path's only
  issue is index-vs-frame (P-02), and it is dead.
- **Dim 3 (CA65 offset)**: The `enumerate(positions)`/`i`-as-offset concern in the SKILL
  no longer exists — that code was removed; CA65 export passes `{}` references and never
  reads them (`main.py:516-528`, `exporter_ca65.py:832-844`; #4 closed, verified).
- **Dim 6 (pickle-ability)**: work chunks contain only plain dicts/tuples/ints/lists;
  `_detect_patterns_worker` is module-level and mutates no shared state. The full-sequence
  copy per chunk is a known perf cost (cross-ref), not a correctness bug.
- **Dim 8 (bounds)**: `range(min, min(max, len)+1)` is safe for `len < min` (empty) and
  `max < min` (empty); no garbage loop. Match advance `pos += pattern_len` is consistent
  across all four detectors.
- **Dim 9 (loops)**: tempo-key format matches between write (`loop_manager.py:130`) and
  read (`:156`); `end <= start` guarded (`:98,149`). Jump-table end-key clobber is real
  but moot — the table is discarded (P-04).

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-06-29.md
```
