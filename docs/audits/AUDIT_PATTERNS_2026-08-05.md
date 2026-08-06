# Pattern Detection & Compression Audit — 2026-08-05

## Summary

**Round-trip result: LOSSLESS CONFIRMED (empirically, freshly re-verified).** I built new
synthetic inputs and ran actual compress→decompress round-trips on both compression paths,
diffing frame-by-frame (not trusting docstrings):

- **Pattern-dedup path** (`EnhancedPatternDetector` → `PatternCompressor`): a sequence with two
  distinct exact-repeat regions (`ABCD`×4 + filler + `EFG`×3) detected `pattern_0` (len 4,
  positions `[0,4,8,12]`) and `pattern_1` (len 3, positions `[21,24,27]`). Every referenced
  window matches its pattern's stored `events` exactly — **0 mismatches**.
- **RLE/delta path** (`exporter/compression.py` `CompressionEngine.compress_pattern` ↔
  `decompress_pattern`): a pattern exercising an RLE run, a delta run (including a numeric key
  — `volume` — whose diff was 0 and is therefore absent from every delta block), and raw events
  with an extra non-numeric key round-tripped to an exact match — **0 mismatches**, confirming
  the 0-diff-key-preservation behavior the skill flags as a risk is correct.

No code in `tracker/pattern_detector.py`, `tracker/pattern_detector_parallel.py`,
`exporter/compression.py`, or the `main.py` pattern-detection stage has changed since the prior
audit (`docs/audits/AUDIT_PATTERNS_2026-07-19.md`, 2026-07-19) except for the fix landed the same
day: commit `398891f` ("require >=3 exact occurrences before selecting a sequential pattern",
closing **#365/PAT-A**). This audit re-verified that fix directly (see below) and re-ran the full
dimension checklist against current code; no regressions and no new issues were found.

**Finding counts:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 0 · **NEW 0**. Two previously-filed
issues remain open and were reproduced live (not new findings, no action needed beyond what's
already tracked): **#366 (PAT-B)** and **#311 (PAT-10)**.

**3 highest-leverage items** (none new — reprioritizing existing open work):
1. **#365/PAT-A is verified CLOSED.** The sequential selection loop now requires
   `len(candidate['positions']) >= MIN_PATTERN_OCCURRENCES` (exact-only) before persisting a
   candidate, and skips (does not mark used) any candidate that only clears the total
   exact+variation gate. Reproduced the old failure scenario from the prior audit
   (`ABCD`×4 + filler) and it now selects the real repeating `pattern_0` with
   `compression_ratio 72.0` instead of a single-occurrence window with ratio `0.0`.
2. **#366 (PAT-B, still OPEN):** `DrumPatternDetector.detect_drum_patterns`'s emergent-pattern
   scan (`tracker/pattern_detector.py:690`) still doesn't skip by `length` after a match, unlike
   the fixed `_find_pattern_matches`. Reproduced live: a period-2, length-6 self-similar run
   yields overlapping "matches" `[0, 2, 4, 6, 8]` (window 0 covers frames 0–5, window 2 covers
   2–7 — they overlap). No ROM-correctness impact (drum-pattern *heuristics* only), but still
   worth fixing per #366.
3. **#311 (PAT-10, still OPEN):** `tests/test_pattern_integration.py:123-140`
   (`test_pattern_positions_format`) still only asserts `positions` are `int`s; nothing in CI
   pins the exact-only round-trip invariant this audit (and the last one) verified by hand.

---

## Findings

No NEW or regressed findings. Verification detail for the two open, previously-filed issues and
the one fix this audit re-confirmed follows.

### Verification: #365/PAT-A fix confirmed correct and complete
- **Severity**: N/A (verifying a closed fix, not a new finding)
- **Dimension**: Dimension 1 (Round-Trip Integrity) / Dimension 4 (Compression-Ratio Accuracy) /
  Dimension 8 (Match Semantics)
- **Location**: `tracker/pattern_detector.py:41-52` (`MIN_PATTERN_OCCURRENCES`),
  `tracker/pattern_detector.py:309-322` (selection loop gate)
- **Status**: Existing: #365 — CLOSED, fix verified in place
- **Description**: `score_pattern` gates a candidate on exact+variation occurrence count, but
  only exact positions are persisted (#168/PAT-01). Before the fix, a candidate could clear the
  `>=3` gate almost entirely on variations while persisting a single exact position (0%
  compression) and still block a genuinely-repeating shorter exact pattern via its
  `occupied_positions`. The fix adds a second, exact-only gate
  (`len(candidate['positions']) >= MIN_PATTERN_OCCURRENCES`) in the selection loop, and skips
  (via `continue`, not marking `used_positions`) any candidate that fails it.
- **Evidence**: Reran the exact repro used in the prior audit (`ABCD`×4 followed by 5 filler
  events, min/max length 3–12). Result: `patterns: {'pattern_0': {'length': 4, 'positions':
  [0, 4, 8, 12]}}`, `stats: {'compression_ratio': 72.0, 'coverage_ratio': 83.3, ...}`. Under the
  pre-fix code this selected a single-occurrence length-10 window with `compression_ratio 0.0`
  (per the 2026-07-19 report). Also ran the full `tests/test_pattern_exact_gate.py` (the
  regression suite added with the fix) plus `tests/test_compression.py`,
  `tests/test_compression_integration.py`, `tests/test_pattern_integration.py` (26 tests, all
  pass) and `tests/test_patterns.py` (77 tests, all pass — slow at ~197s standalone but not
  hanging; consistent with #355/REG-22's note that it passes alone).
- **Impact**: N/A — confirms no further action needed on #365.
- **Related**: #168/PAT-01, #170/PAT-04, #103.
- **Suggested Fix**: None — closed.

### Existing (reproduced, not re-filed): #366/PAT-B — DrumPatternDetector emergent scan still self-overlaps
- **Severity**: LOW (per prior audit's assessment — heuristic quality only, no ROM/round-trip impact)
- **Dimension**: Dimension 8 (Pattern-Length Bounds & Match Semantics)
- **Location**: `tracker/pattern_detector.py:690` (`detect_drum_patterns` emergent-pattern loop)
- **Status**: Existing: #366 (OPEN) — reproduced live, unchanged since 2026-07-19 audit
- **Description**: The `_find_pattern_matches` self-overlap fix (#170/PAT-04: scan resumes at
  `start_pos + pattern_len`) was never mirrored in `DrumPatternDetector.detect_drum_patterns`'s
  emergent-pattern scan, which still does `for pos in range(start + 1, len(sequence) - length +
  1):` with no skip-by-`length` after a match.
- **Evidence**: Built a period-2, note-alternating sequence (14 events, notes 50/55) that does
  not match any of the three hardcoded `drum_patterns` templates, forcing the emergent path.
  With `min_pattern_length=max_pattern_length=6`: `emergent_pattern_0 matches=[0, 2, 4, 6, 8]` —
  windows at positions 0 and 2 overlap (window 0 spans frames 0–5, window 2 spans 2–7), and this
  overlap count feeds directly into `score_drum_pattern`'s `total_occurrences` and the
  `_optimize_drum_patterns` overlap math.
- **Impact**: Confirmed live-reproducible. `DrumPatternDetector` is used by
  `dpcm_sampler/enhanced_drum_mapper.py` — affects drum-pattern selection quality in the DPCM
  drum mapper, not lossless music data (this detector's output does not feed the exporter's
  emitted bytes). Blast radius unchanged from the 2026-07-19 assessment.
- **Related**: #170/PAT-04 (closed, for the sequential melodic detector only).
- **Suggested Fix**: (per #366) mirror the `_find_pattern_matches` non-overlap discipline in the
  emergent drum scan.

### Existing (reproduced, not re-filed): #311/PAT-10 — exact-only round-trip invariant still untested
- **Severity**: LOW
- **Dimension**: Dimension 1 (Round-Trip Integrity)
- **Location**: `tests/test_pattern_integration.py:123-140` (`test_pattern_positions_format`)
- **Status**: Existing: #311 (OPEN) — unchanged since 2026-07-19 audit
- **Description**: The test still only asserts `positions` values are `int`s; it never asserts
  the referenced window equals `[(e['note'], e['volume']) for e in events]`. This audit (like the
  last) re-verified the invariant by hand with a fresh synthetic sample (0 mismatches, see
  Summary), but nothing pins it in CI, so a regression of the #168/PAT-01 exact-only guarantee
  would pass silently.
- **Evidence**: Read `tests/test_pattern_integration.py:123-140` directly; confirmed no
  frame-window equality assertion exists anywhere in the file.
- **Impact**: Coverage gap only — no current bug. If `positions` regressed to include
  non-exact/variation entries (as it did pre-#168), no test would catch it.
- **Related**: #168/PAT-01 (closed), #365/PAT-A (closed, this audit).
- **Suggested Fix**: (per #311) add
  `assert sequence[pos:pos+length] == [(e['note'], e['volume']) for e in events]` for every `pos`
  in each detected pattern's `positions`.

---

## Dimensions verified clean (no finding)

- **Dim 1 (round-trip):** Both paths lossless — freshly diffed with new synthetic inputs, 0
  mismatches. RLE + delta (including 0-diff-key absence) + raw events all preserved exactly.
- **Dim 2 (schema):** `ParallelPatternDetector.detect_patterns`'s no-events return
  (`pattern_detector_parallel.py:41-48`), its `_empty_result` (`:344-354`),
  `EnhancedPatternDetector`'s no-events return, and the `--no-patterns` stub
  (`main.py:924-940`) all emit the identical 7-key `stats` set
  (`original_size, compressed_size, compression_ratio, unique_patterns, total_events,
  patterned_events, coverage_ratio`) and the same 4-key `variations` envelope
  (`'variations': {}`).
- **Dim 3 (offsets/length):** `PatternCompressor.compress_patterns`
  (`pattern_detector.py:827-857`) fills `pattern_refs` from exact-only `positions`;
  `export_tables_with_patterns` (`exporter/exporter_ca65.py:996-1008`) still documents and
  enforces that `references` is not consumed — `patterns` truthiness is a pure boolean switch
  (direct frames vs. MMC3 macro-bytecode). Contract intact, re-read directly.
- **Dim 5 (parallel/serial + fallback):** Confirmed the `#332/PERF-12` sub-chunking rework
  (`_build_work_chunks`, `_collect_window_groups`, `_select_candidates_from_groups`,
  `pattern_detector_parallel.py:280-434`) preserves every invariant this dimension checks:
  the inner serial fallback (`_detect_patterns_serial`) returns the bare patterns dict via
  `_select_best_patterns`, and its callers (`detect_patterns`, and the pool-wide-failure
  except at `:234-236`) re-wrap it through the compressor into the full envelope. The
  in-process per-sub-chunk retry (`:215-231`) and the durable end-of-run partial-detection
  warning (`:253-257`, #106) are both present and unchanged. `score_pattern` is still the sole,
  shared scoring function (`_select_candidates_from_groups:421` calls it with
  `variation_count=0`); the PAT-05/#171 non-equivalence caveat is still documented in
  `_collect_length_candidates`'s docstring (`:437-450`).
- **Dim 6 (multiprocessing):** `sequence`/`valid_events` still shipped once via
  `ProcessPoolExecutor(initializer=_init_pattern_worker, initargs=(sequence, valid_events))`
  (`:199-202`), stashed as module globals (`:363-368`). Work chunks now carry
  `{'pattern_length', 'start_range'}` (further sub-chunked per length since #332/PERF-12,
  beyond what the skill's dimension text describes verbatim — a documentation-currency note,
  not a code defect) but remain small, picklable dicts with no embedded sequence copy.
  `_detect_window_groups_worker`/`_init_pattern_worker` are module-level. `ThreadedPatternDetector`
  confirmed still absent (`grep -rn ThreadedPatternDetector` → only the doc comment and the
  regression test asserting it's gone).
- **Dim 7 (sampling):** Two caps only, `MAX_PATTERN_EVENTS=15000` /
  `DETECTOR_MAX_EVENTS=1000`, shared `sample_events_for_detection`. `main.py`'s full-pipeline
  path keeps `frames` alive and only `del events` after pattern detection
  (`main.py:910-913`) — export still derives every byte from `frames`, confirmed unchanged.
- **Dim 8 (bounds/match semantics):** `_select_candidates_from_groups`'s greedy
  `next_free`-based selection (`pattern_detector_parallel.py:406-411`) reproduces the documented
  non-overlap invariant exactly. `_hash_pattern` (`pattern_detector.py:859-867`) still returns
  the raw `(note, volume)` tuple, not `hash()`. `MIN_PATTERN_OCCURRENCES=3` is shared between
  `score_pattern`'s total-occurrence gate and the sequential selector's exact-occurrence gate
  (#365, confirmed above). (Drum-detector exception → #366/PAT-B above, unchanged.)
- **Dim 9 (loops):** `LoopManager.detect_loops` (`tracker/loop_manager.py:20-46`) still guards
  `len(positions) > 1` before touching `positions[-2]`, so a single-exact-position pattern (which
  #365's fix now prevents from being selected at all) cannot reach an `IndexError` either way.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-08-05.md
```
