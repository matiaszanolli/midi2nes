# Pattern Detection & Compression Audit — 2026-08-07

## Summary

**Round-trip result: LOSSLESS CONFIRMED (empirically re-verified today, three independent
paths, not just re-read from a prior report).**

1. `EnhancedPatternDetector.detect_patterns` was run on a fresh synthetic sequence
   (`ABCD`×4 exact repeats, a *transposed decoy* of `ABCD` immediately after them, 5 filler
   events, then `EFG`×3 exact repeats). Every stored `positions` entry was dereferenced back
   into the source sequence and compared byte-for-byte against the pattern's stored
   `events`: **0 mismatches**, and the decoy's start index (16) did **not** leak into either
   pattern's `positions` — PAT-01/#168's exact-only guarantee holds.
2. `ParallelPatternDetector.detect_patterns` was run on a 235-event sequence (above
   `SERIAL_EVENT_THRESHOLD=200`, so a real `ProcessPoolExecutor` spawned and 6 work chunks
   were processed across multiple pattern lengths): **0 mismatches** across all 9 detected
   patterns' dereferenced positions.
3. `PatternCompressor.compress_patterns`'s hash-based duplicate-pattern merge path was
   exercised directly with two distinct pattern IDs constructed to share identical `events`
   content but disjoint positions — confirmed they merge into one compressed entry with a
   correctly unioned/sorted `positions` list, and every merged position still dereferences to
   the exact stored `events` (**0 mismatches**). `_hash_pattern` still returns the raw
   `(note, volume)` tuple, not `hash()` of it (#173).

`export_tables_with_patterns` (`exporter/exporter_ca65.py:1432-1441`) still documents and
implements `references` as **not consumed** — `patterns` truthiness is the sole switch
between direct-frame export and the MMC3 macro-bytecode serializer (#4) — confirmed by
direct code read, not docstring trust.

**No code in `tracker/pattern_detector.py`, `tracker/pattern_detector_parallel.py`, or
`tracker/loop_manager.py` has changed since the prior audit**
(`docs/audits/AUDIT_PATTERNS_2026-08-06.md`) — the most recent commit touching any of the
three is `24e51d2` (2026-07-xx), well before that report. `exporter/exporter_ca65.py`'s line
numbers shifted (now `:1432` vs the prior report's `:962-971`) purely from unrelated file
growth (the new `song bank → ROM` "jukebox" feature, `c864426`/#30/F-13, which — confirmed by
grep — imports nothing from `tracker/pattern_detector*` or `loop_manager` and deliberately
bypasses pattern detection for jukebox builds); the contract text itself is unchanged.

**The two prior report's headline items are now resolved.** The 2026-08-06 audit found that
issues #378 and #379 were closed on GitHub but their fixes existed only on unmerged local
branches. This is no longer true: PR #420 (`fix/issues-376-378-379-385`, commit `4c9f0b4`)
merged both fixes into `master`, and `git merge-base --is-ancestor` confirms both fix commits
(`0f2d5e1` for #378, `3315f39` for #379) are now ancestors of `HEAD`. Verified directly in
today's `main.py`:
- The `coverage_lossy_note` gate now reads `detector.was_sampled or fallback_sampled`
  (`main.py:1168`), not just `detector.was_sampled` — the #378 fix.
- `run_full_pipeline`'s `export_tables_with_patterns` call now passes
  `pattern_result['references']` (`main.py:1225`), not a literal `{}` — the #379 fix. (The
  remaining literal `{}` at `main.py:1087` is the `--no-patterns` stub, where `patterns` is
  also `{}`, so `references: {}` is correct there — not the divergence #379 described.)

**Finding counts:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 3 · **Total 3**.

**3 highest-leverage items** (all LOW / hardening, no functional bug found this cycle):
1. `run_detect_patterns`'s persisted `detect-patterns` output JSON omits the `variations` key
   that `_audit-common.md`'s own documented 4-key contract promises — harmless today (no
   consumer reads it) but worth closing so the on-disk file matches its documented shape.
2. `PatternDetector._optimize_patterns` (`tracker/pattern_detector.py:369-406`) is fully dead
   code — never called by `detect_patterns` (which builds and returns its own selection
   inline), only referenced by one test — and it silently duplicates the overlap-selection
   idea with a *different*, unshared scoring formula, which is a drift trap if anyone assumes
   it's live.
3. This skill file's own Dimension 7/8 prose has drifted from the code: `PATTERN_MIN_LENGTH`/
   `PATTERN_MAX_LENGTH` moved from `main.py:36-37` to `constants.py:18-19`, and
   `LARGE_FILE_THRESHOLD`'s value changed from a hardcoded `10000` to `MAX_PATTERN_EVENTS`
   (15000) at `main.py:44` (was `main.py:818`) back in commit `07819ce`/#334 (2026-07-18) —
   worth an `/audit-sync` pass on this SKILL.md.

---

## Findings

### PAT-2026-08-07-A: `detect-patterns` subcommand's persisted JSON omits the documented `variations` key
- **Severity**: LOW
- **Dimension**: Dimension 2 (`pattern_result` Schema Integrity)
- **Location**: `main.py:777-781` (`run_detect_patterns`'s `output` dict)
- **Status**: NEW (distinct from #258/PAT-09, which fixed the *in-memory* `--no-patterns`
  stub's `variations` omission inside `run_full_pipeline` — this is the on-disk file the
  `detect-patterns` subcommand itself writes, a different code path, still missing the key)
- **Description**: `_audit-common.md`'s documented inter-stage contract states
  `detect-patterns → dict with keys patterns, references, stats, variations`. Both real
  detectors' `detect_patterns()` return all four keys in memory. But `run_detect_patterns`
  (the `detect-patterns` subcommand's entry point) builds its persisted JSON as:
  ```python
  output = {
      'patterns': pattern_result['patterns'],
      'references': pattern_result['references'],
      'stats': pattern_result['stats']
  }
  Path(args.output).write_text(json.dumps(output, separators=(',', ':')))
  ```
  dropping `pattern_result['variations']` entirely. This is not a regression — `git log -S`
  shows this line has never included `variations` — but it means the file a user gets from
  `python main.py detect-patterns ...` does not match the 4-key envelope the project's own
  audit protocol documents for that stage.
- **Evidence**: `grep -n "'patterns': pattern_result\['patterns'\]" -A3 main.py` shows the
  3-key dict above. `run_export`'s consumer-side `load_json_stage(args.patterns,
  ['patterns', 'references'], 'detect-patterns')` only requires `patterns`/`references`, and
  never accesses `pattern_data['variations']` anywhere in `run_export`. The existing test
  `tests/test_main.py::TestMainDetectPatterns::test_run_detect_patterns_success` mocks
  `detect_patterns.return_value` **without** a `variations` key at all and only asserts
  `'patterns' in content`, `'references' in content`, `'stats' in content` — it cannot catch
  this because it doesn't even feed the field in.
- **Impact**: None on ROM output — no code path in this repo reads `variations` back out of
  the persisted `detect-patterns` JSON file. Purely a documented-contract/actual-output
  mismatch: any future consumer (a downstream tool, a test asserting the documented shape, a
  user script) that expects the file to match `_audit-common.md`'s stated 4-key contract
  would `KeyError` on `variations`.
- **Related**: #258/PAT-09 (fixed the in-memory `--no-patterns` stub's `variations` omission —
  a different code path from this one), #4 (references itself already documented as
  analysis-only/unconsumed, same spirit).
- **Suggested Fix**: Add `'variations': pattern_result.get('variations', {})` to the `output`
  dict in `run_detect_patterns` (`main.py:777-781`) so the persisted file matches the
  documented contract, and extend `test_run_detect_patterns_success` to assert
  `'variations' in content`.

### PAT-2026-08-07-B: `PatternDetector._optimize_patterns` is dead code with a diverging, unshared scoring formula
- **Severity**: LOW
- **Dimension**: Dimension 8 (Pattern-Length Bounds & Match Semantics)
- **Location**: `tracker/pattern_detector.py:369-406`
- **Status**: NEW
- **Description**: `PatternDetector.detect_patterns` (`:174-346`) builds its own
  non-overlapping pattern selection inline (candidate scoring via the shared module-level
  `score_pattern`, then a sort + greedy `used_positions` loop, `:305-343`) and returns
  `patterns` directly at `:346` — it never calls `self._optimize_patterns`.
  `EnhancedPatternDetector.detect_patterns` calls `super().detect_patterns(events)` (the same
  method) and likewise never calls it. `_optimize_patterns` (`:369-406`) is therefore
  unreachable from any real entry point; `grep -rn "_optimize_patterns\b" .` shows its only
  other reference is `tests/test_patterns.py:267`, which calls it directly on a detector
  instance purely to unit-test the orphaned method itself. Its own local `pattern_score`
  closure (`:380-384`, `(exact_count + variation_count * 0.8) * pattern_length`) is a
  *different formula* from the shared `score_pattern` (`:52-91`) the live path uses — so if
  a future refactor ever wired this method back in (e.g. "let's optimize the selection
  further"), it would silently re-diverge the two detectors' scoring that #103 unified.
- **Evidence**:
  ```
  $ grep -n "_optimize_patterns(" tracker/pattern_detector.py tests/test_patterns.py
  tracker/pattern_detector.py:369:    def _optimize_patterns(self, patterns: Dict) -> Dict:
  tests/test_patterns.py:267:        optimized = self.pattern_detector._optimize_patterns(patterns)
  ```
  No call site inside `pattern_detector.py` itself invokes `self._optimize_patterns(...)`.
- **Impact**: None today (unreachable code, confirmed dead by grep across the whole repo).
  Pure maintainability/drift-trap risk: a future contributor could plausibly assume this
  method is part of the active selection pipeline (it reads as if it should be, sitting
  right in the class whose `detect_patterns` "should" call it) and either rely on it being
  live or "fix" it under that false assumption.
- **Related**: #103 (closed — unified `score_pattern` across both detectors; this dead method
  is the one place that formula unification never reached, because it's unreachable), #352/
  REG-21 (documents the bare `PatternDetector` class itself as test-only/production-dead;
  this finding is a narrower point about one of its own methods being dead even to its own
  class's live method).
- **Suggested Fix**: Delete `_optimize_patterns` (and migrate or drop the one test exercising
  it) unless there's a concrete plan to wire it in — in which case first rewrite its scoring
  to call the shared `score_pattern` instead of the local closure, per the #103 precedent.

### PAT-2026-08-07-C: This skill's Dimension 7/8 prose has drifted from `main.py`'s actual constant locations/values
- **Severity**: LOW
- **Dimension**: Dimension 7 (Large-File Sampling) / Dimension 8 (Pattern-Length Bounds)
- **Location**: `.claude/commands/audit-patterns/SKILL.md` (Dimension 7 and Dimension 8 text)
  vs. `constants.py:18-19` and `main.py:44`
- **Status**: NEW (self-referential: a doc-rot finding about this audit skill's own prose,
  not about `tracker/pattern_detector*.py`)
- **Description**: Two claims in this SKILL.md no longer match the live code:
  1. Dimension 8 states `PATTERN_MIN_LENGTH = 3` / `PATTERN_MAX_LENGTH = 12` are defined at
     `main.py:36-37`. They now live in `constants.py:18-19` and are *imported* into `main.py`
     (`from constants import PATTERN_MIN_LENGTH, PATTERN_MAX_LENGTH`, `main.py:39`) — the
     values (3, 12) are unchanged and all three call sites (`run_detect_patterns`,
     `detect_patterns_or_direct_export`'s parallel path, and its sequential fallback) still
     reference the shared constants correctly, but the cited definition location is stale.
  2. Dimension 7 states `LARGE_FILE_THRESHOLD = 10000 (main.py:818)`. The live code is
     `LARGE_FILE_THRESHOLD_DEFAULT = MAX_PATTERN_EVENTS` at `main.py:44` — i.e. the value is
     now `15000` (aliased to `MAX_PATTERN_EVENTS`, not a standalone hardcoded `10000`), and it
     moved from line 818. `config/default_config.yaml:16` independently confirms this:
     `large_file_threshold: 15000  # ... aligned with max_pattern_events by default`. This
     changed in commit `07819ce` (#334, 2026-07-18) — before even the 2026-07-19 audit — so
     the SKILL.md prose has been stale for multiple audit cycles without being caught, since
     the behavior itself (advisory-only, doesn't drop events) is still correct even though the
     cited value/location aren't.
- **Evidence**:
  ```
  $ grep -n "PATTERN_MIN_LENGTH\|PATTERN_MAX_LENGTH" main.py constants.py
  main.py:39:from constants import PATTERN_MIN_LENGTH, PATTERN_MAX_LENGTH
  constants.py:18:PATTERN_MIN_LENGTH = 3
  constants.py:19:PATTERN_MAX_LENGTH = 12

  $ git blame -L 44,44 main.py
  07819ce0 (Matias Zanolli 2026-07-18 ...) LARGE_FILE_THRESHOLD_DEFAULT = MAX_PATTERN_EVENTS
  ```
- **Impact**: None on ROM output or pipeline behavior — this is purely about the audit skill
  file's own accuracy, which affects how reliably *future* audits (including this one) can
  trust their own dimension checklist without re-deriving locations from scratch each time.
- **Related**: None filed under this exact wording; adjacent to the general pattern of
  `/audit-sync` passes that already exist in this repo's workflow for exactly this drift
  class.
- **Suggested Fix**: Run `/audit-sync` (or a manual edit) against `audit-patterns/SKILL.md`
  Dimension 7/8 to update the citations to `constants.py:18-19` and `main.py:44`, and to
  state `LARGE_FILE_THRESHOLD` as "aliased to `MAX_PATTERN_EVENTS` (15000 by default)" rather
  than a standalone hardcoded `10000`.

---

## Dimensions verified clean (no finding)

- **Dim 1 (round-trip):** LOSSLESS CONFIRMED via three independent, freshly-run empirical
  checks today (sequential detector with a transposed-decoy trap, parallel detector under a
  real multi-chunk `ProcessPoolExecutor` run, and the compressor's hash-merge path) — see
  Summary. `tests/test_patterns.py`, `tests/test_pattern_integration.py`,
  `tests/test_pattern_exact_gate.py`, `tests/test_pattern_detector_parallel.py`, and
  `tests/test_enhanced_loop_patterns.py` (112 tests total, `-m "not slow"`) all pass on
  current `HEAD` (`f4c2283`).
- **Dim 2 (schema):** Both real detectors' in-memory 4-key envelope (`patterns`,
  `references`, `stats`, `variations`) and the `--no-patterns` stub inside
  `detect_patterns_or_direct_export` (`main.py:1085-1101`) are unchanged and consistent.
  (The one gap found — `run_detect_patterns`'s *on-disk* projection dropping `variations` —
  is reported as PAT-2026-08-07-A above, LOW/cosmetic.)
- **Dim 3 (offsets/length):** `export_tables_with_patterns` still does not consume
  `references` (confirmed by direct read of `exporter/exporter_ca65.py:1432-1441`, not
  docstring trust); `PatternCompressor.compress_patterns`'s length/positions bookkeeping
  verified correct via the direct hash-merge round-trip test in Dim 1. Both
  `run_full_pipeline` and `run_export` now pass the real `references` dict (the #379 fix,
  confirmed merged — see Summary).
- **Dim 4 (compression-ratio/stats):** `calculate_compression_stats` unchanged;
  `coverage_lossy_note` gate now correctly ORs `detector.was_sampled` with the fallback's own
  local `fallback_sampled` flag (`main.py:1168`, the #378 fix, confirmed merged). Both
  "% reduction" banners (`main.py:787`, `:1409`) stay consistent with the patterned-subset-
  only framing (#17, #169/PAT-03).
- **Dim 5 (parallel/serial + fallback):** Shared `score_pattern` confirmed still called by
  both paths; the non-equivalence caveat in `_collect_length_candidates`'s docstring
  (`pattern_detector_parallel.py:446-455`) is intact and matches observed behavior (the
  self-similar-run test — 12 identical notes, length 4 — gave identical `[0, 4, 8]` on both
  detectors, confirming the shared non-overlap discipline). The inner serial fallback returns
  the raw `patterns` dict via `_select_best_patterns`, and its one caller (`detect_patterns`)
  still wraps it through the compressor before returning — traced end-to-end today, not
  assumed.
- **Dim 6 (multiprocessing safety):** `_init_pattern_worker`/`_detect_window_groups_worker`
  remain module-level; `initargs=(sequence, valid_events)` are plain lists of tuples/dicts
  with no closures, tempo maps, or non-picklable objects added. Verified live with a real
  235-event, 6-work-chunk `ProcessPoolExecutor` run (Dim 1) — no pickling errors, correct
  merge-by-window-value across sub-chunks.
- **Dim 7 (sampling):** Exactly two caps (`DETECTOR_MAX_EVENTS=1000`,
  `MAX_PATTERN_EVENTS=15000`), both config-validated to be positive integers
  (`config/config_manager.py:280-286`), shared `sample_events_for_detection`. The advisory
  `large_file_threshold` gate (`main.py:1128`) only guards a `print`, confirmed by reading
  every call site — it cannot drop events. (The SKILL.md's own stale citation of this value
  is PAT-2026-08-07-C above, not a code defect.)
- **Dim 8 (bounds/match semantics):** `MIN_PATTERN_OCCURRENCES=3` exact-occurrence gate
  (#365/PAT-A) re-verified empirically today: a constructed 1-exact/3-variation candidate was
  correctly skipped (not selected, not marking its region used), and did not block a
  genuinely-repeating shorter pattern elsewhere in the same sequence. `_find_pattern_matches`'s
  non-self-overlap discipline (#170/PAT-04) and `DrumPatternDetector`'s mirrored fix (#366/
  PAT-B, `tracker/pattern_detector.py:696-712`) both still present. (The one dead-code gap
  found in this dimension's territory — `_optimize_patterns` — is PAT-2026-08-07-B above.)
- **Dim 9 (loops):** `LoopManager.detect_loops` still guards `len(positions) > 1` before
  indexing `positions[-2]`; `EnhancedLoopManager`'s tempo-key format matches between write
  (`loop_manager.py:141`) and read (`:167`). Additionally verified today: two loop candidates
  sharing an `end` frame cannot both survive `_optimize_loops`'s overlap filter — any two
  ranges with the same `end` on a single linear timeline necessarily overlap (share at least
  frame `end-1`), so the jump-table key-collision scenario the SKILL.md's Dimension 9 flags as
  a risk is actually **structurally impossible**, not just untested, by the time
  `generate_jump_table` runs. Separately: `tracker/loop_manager.py` (all of it, including this
  guard logic) remains reachable only from `tracker/parser_fast.py`'s
  `parse_midi_to_frames_with_analysis` (its own `__main__` CLI block only, not
  `run_full_pipeline`) and the production-dead `tracker/parser.py` (#346/TD-26) — this
  "production-dead but tested" status is **Existing: #97** (TEMPO-05, closed as
  documented-and-kept, not deleted) and unchanged since; not re-reported here.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-08-07.md
```
