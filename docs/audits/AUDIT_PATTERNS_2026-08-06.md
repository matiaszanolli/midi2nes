# Pattern Detection & Compression Audit — 2026-08-06

## Summary

**Round-trip result: LOSSLESS CONFIRMED (empirically, freshly re-verified today).** A new
synthetic sequence (`ABCD`×4 exact repeats, a *transposed decoy* of `ABCD` immediately
following them, 5 filler events, then `EFG`×3 exact repeats) was run through
`EnhancedPatternDetector.detect_patterns` and every stored `positions` entry was
dereferenced back into the source sequence and compared byte-for-byte against the
pattern's stored `events`. Result: **0 mismatches**, and the transposed decoy's start
index did not leak into either pattern's `positions` — confirming PAT-01/#168's
exact-only guarantee still holds. `PatternCompressor._hash_pattern` still returns the raw
`(note, volume)` tuple (not `hash()` of it, #173) and `export_tables_with_patterns` still
does not consume `references` (#4) — verified by direct code read, not docstring trust.

**No code in `tracker/pattern_detector.py`, `tracker/pattern_detector_parallel.py`, or
`tracker/loop_manager.py` has changed since the prior audit**
(`docs/audits/AUDIT_PATTERNS_2026-08-05.md`). `exporter/exporter_ca65.py` changed
substantially (commit `20f627e`, #136) but only as a verbatim extraction of
`export_direct_frames`'s per-channel emitters into standalone methods — the
`patterns`-truthiness / `references`-is-inert contract this audit's Dimension 3 checks is
unchanged and still documented at `exporter/exporter_ca65.py:1064-1073`.

**However, this audit found that the fixes for two issues the tracker shows as CLOSED are
not actually present in this branch's `main.py`.** Both fix commits exist in the repo's
git history, but only on local branches (`fix/issue-378-fallback-coverage-lossy-note`,
`fix/issue-379-unify-references-shape`) that were never opened as PRs or merged — `git
merge-base --is-ancestor` confirms neither commit is an ancestor of `HEAD`. Both issues
show `state: CLOSED` via `gh issue view`, which would lead anyone trusting issue status to
believe these are fixed. They are not, in the code actually checked out:

1. **#378 (MEDIUM, NEW as a regression against a closed issue)** — the sequential-fallback
   path's `coverage_ratio` banner still omits the "(lossy)" qualifier when `main.py` itself
   pre-samples events to `max_events` before handing them to `EnhancedPatternDetector`,
   because the check only reads `detector.was_sampled` (which is `False` once the input is
   already at the cap), never the fallback's own local `was_sampled`. Reproduced live below
   — this is a real, current mislabeling of a stats banner, not a hypothetical.
2. **#379 (LOW, NEW as a regression against a closed issue)** — `run_full_pipeline` still
   passes a bare literal `{}` for `references` to `export_tables_with_patterns`
   (`main.py:1087`), while `run_export` passes `pattern_data['references']` verbatim
   (`main.py:668`, `698`). Confirmed still inert today (`references` is not consumed, #4),
   so no ROM output is affected — but the two call sites remain structurally divergent
   despite the issue being closed as fixed.

**Finding counts:** CRITICAL 0 · HIGH 0 · MEDIUM 1 · LOW 1 · **Total 2**.

**3 highest-leverage items:**
1. Merge (or re-apply) `fix/issue-378-fallback-coverage-lossy-note` into this branch/master
   — a one-line `or` fix, already written and tested on that branch, closes a live
   misleading-stats bug (MEDIUM, Dimension 4/7).
2. Merge (or re-apply) `fix/issue-379-unify-references-shape` — inert today, but keeps the
   two export call sites from silently diverging if `references` is ever wired up (LOW,
   Dimension 3).
3. Process gap, not a code bug: two issues were closed on GitHub before their fix branches
   were merged. Worth a note to whatever closes issues (manual or automation) that "fix
   committed on a branch" and "fix merged to master" are being conflated — this is the
   second time in this audit's history a closed-vs-merged gap has been the deciding factor
   for a finding, so it's worth flagging as a workflow risk beyond just these two issues.

---

## Findings

### PAT-2026-08-06-A: `coverage_ratio` "(lossy)" label omitted when the sequential fallback pre-samples (fix for #378 not in this branch)
- **Severity**: MEDIUM
- **Dimension**: Dimension 4 (Compression-Ratio & Stats Accuracy) / Dimension 7 (Sampling)
- **Location**: `main.py:990-1013` (fallback branch + `coverage_lossy_note` gate)
- **Status**: Regression of #378 — issue is CLOSED on GitHub, but its fix commit
  (`0f2d5e1`, branch `fix/issue-378-fallback-coverage-lossy-note`) is **not an ancestor of
  HEAD** (`git merge-base --is-ancestor 0f2d5e1 HEAD` → false) and was never opened as a PR
  (`gh pr list --search 378` → empty). The code on this branch is the pre-fix version #378
  itself described.
- **Description**: When `ParallelPatternDetector` raises and `run_full_pipeline` falls back
  to `EnhancedPatternDetector`, it pre-samples `events` down to `max_events` itself
  (`main.py:993-994`, `sample_events_for_detection`) before calling
  `detector.detect_patterns(events)`. Since the events handed to the detector are already at
  (or under) its internal cap, the detector's own internal
  `sample_events_for_detection` call never triggers, so `detector.was_sampled` stays
  `False`. The `coverage_lossy_note` gate at `main.py:1005` reads only
  `detector.was_sampled`, so it misses the fact that the *pre-sample* already made the
  coverage number lossy — the "Pattern coverage" banner line prints without the `(lossy —
  measured over the sampled subset...)` qualifier even though the number genuinely was
  computed over a reduced subset.
- **Evidence**: Reproduced live by driving the exact code path directly:
  ```python
  from tracker.pattern_detector import sample_events_for_detection, EnhancedPatternDetector, DETECTOR_MAX_EVENTS
  from tracker.tempo_map import EnhancedTempoMap

  events = [{'note': i % 5, 'volume': 100} for i in range(5000)]
  max_events = DETECTOR_MAX_EVENTS
  sampled_events, was_sampled = sample_events_for_detection(events, max_events)   # main.py's own pre-sample
  detector = EnhancedPatternDetector(EnhancedTempoMap(initial_tempo=500000),
                                      min_pattern_length=3, max_pattern_length=4,
                                      max_events=max_events, analyze_tempo=False)
  detector.detect_patterns(sampled_events)
  # was_sampled            -> True   (main.py's local flag: pre-sample DID trim events)
  # detector.was_sampled   -> False  (the only flag main.py's banner actually checks)
  ```
  Output: `main.py local was_sampled: True`, `detector.was_sampled (used for
  coverage_lossy_note): False`, `BUG CONFIRMED: True`. This exactly matches the mechanism
  #378's (closed) description attributes to the bug, and the fix commit's diff (`0f2d5e1`)
  is a straightforward `fallback_was_sampled` OR-in that current `main.py` does not have.
- **Impact**: Cosmetic-but-misleading stats output only (per `_audit-severity.md`'s MEDIUM
  floor for "compression ratio/stats reported inaccurately") — no ROM bytes are affected
  (export still derives every byte from `frames`, unaffected by pattern-detection
  sampling). Affects any full-pipeline run on a MIDI large enough to make
  `ParallelPatternDetector` fail (falling back to the sequential detector) and long enough
  to exceed `DETECTOR_MAX_EVENTS` (1000) — a realistic combination for large/complex songs,
  which is precisely when the lossy caveat matters most to a user reading the banner.
- **Related**: #378 (closed but unmerged), #312/PAT-11 (the original lossy-labeling
  mechanism this gate implements), #100 (uniform-sampling policy).
- **Suggested Fix**: Merge branch `fix/issue-378-fallback-coverage-lossy-note` (or
  re-apply commit `0f2d5e1`) into master/this branch: track `main.py`'s own pre-sample in a
  `fallback_was_sampled` flag set only inside the `except` branch, and OR it with
  `detector.was_sampled` when deciding whether to append the `(lossy)` note.

### PAT-2026-08-06-B: `run_full_pipeline` and `run_export` still pass structurally divergent `references` shapes (fix for #379 not in this branch)
- **Severity**: LOW
- **Dimension**: Dimension 3 (Reference Offsets & Length Correctness)
- **Location**: `main.py:1087` (`run_full_pipeline`'s `export_tables_with_patterns` call,
  literal `{}`) vs. `main.py:666-668`/`698` (`run_export` forwarding
  `pattern_data['references']` verbatim)
- **Status**: Regression of #379 — issue is CLOSED on GitHub, but its fix commit
  (`3315f39`, branch `fix/issue-379-unify-references-shape`) is **not an ancestor of HEAD**
  (`git merge-base --is-ancestor 3315f39 HEAD` → false) and was never opened as a PR. `git
  blame` on `main.py:1087` attributes the literal `{}` to the original 2026-06-29 commit
  (`368f5c0`), not to the #379 fix — i.e., the pre-fix code is what's actually checked out.
- **Description**: `run_full_pipeline` passes a bare literal `{}` for the `references`
  argument to `export_tables_with_patterns` regardless of what pattern detection produced,
  while `run_export` passes the detector's native `{'pattern_id': [positions]}` shape
  through unmodified from `pattern_data['references']`. `export_tables_with_patterns`
  documents (and this audit re-confirmed by reading `exporter/exporter_ca65.py:1064-1073`
  directly) that `references` is **not consumed** at all today — `patterns` truthiness is
  the sole boolean switch between direct-frame export and the MMC3 macro-bytecode
  serializer — so this divergence is currently inert and produces byte-identical ROMs
  either way. The risk is purely forward-looking: if a future change ever makes
  `export_tables_with_patterns` read `references`, these two entry points would silently
  diverge and break the "same ROM from both paths" guarantee the rest of this audit
  relies on.
- **Evidence**:
  ```
  $ git blame -L 1078,1092 -- main.py
  368f5c04 ... 1087)                 {},
  $ git merge-base --is-ancestor 3315f39 HEAD && echo yes || echo no
  no
  $ gh pr list --repo matiaszanolli/midi2nes --search 379 --state all
  []
  ```
  `tests/test_main_pipeline.py:508` still only pins the `--no-patterns` direct-export path
  (`assert call_args[2] == {}  # Empty references`), where `{}` is correct either way since
  the stub's own `references` is `{}` too — this existing test cannot and does not catch
  the divergence for the patterns-non-empty case the #379 fix targeted.
- **Impact**: None on current ROM output (confirmed inert, matches the issue's own
  "currently inert" framing). Purely a latent-defect / consistency-drift risk that the
  closed issue's fix was meant to close off but hasn't actually landed.
- **Related**: #379 (closed but unmerged), #4 (references-not-consumed, closed), #368f5c0
  (original dead-code removal that left this divergence).
- **Suggested Fix**: Merge branch `fix/issue-379-unify-references-shape` (or re-apply
  commit `3315f39`): change `main.py:1087`'s literal `{}` to `pattern_result['references']`,
  matching `run_export`'s derivation.

---

## Dimensions verified clean (no finding)

- **Dim 1 (round-trip):** Freshly re-verified today with a new synthetic input including a
  transposed-decoy trap (not reused from a prior audit's fixture) — 0 mismatches, decoy
  correctly excluded from `positions`. `tests/test_pattern_integration.py` (15 tests),
  `tests/test_pattern_exact_gate.py`, `tests/test_pattern_detector_parallel.py`, and
  `tests/test_enhanced_loop_patterns.py` (20 tests combined) all pass on current `HEAD`.
- **Dim 2 (schema):** `--no-patterns` stub (`main.py:1024-1041`) still emits the same 7-key
  `stats` set and 4-key top-level `variations: {}` envelope both real detectors produce;
  unchanged since 2026-08-05.
- **Dim 3 (offsets/length):** Contract intact **except** for the `run_full_pipeline`/
  `run_export` `references`-shape divergence reported as PAT-2026-08-06-B above (LOW,
  inert). `PatternCompressor.compress_patterns` and `_hash_pattern` unchanged and correct.
- **Dim 5 (parallel/serial + fallback):** `tracker/pattern_detector_parallel.py` unchanged
  byte-for-byte since 2026-08-05 (confirmed via `git diff` against the master merge-base);
  the #332/PERF-12 sub-chunking rework, shared `score_pattern`, and the documented
  non-equivalence caveat in `_collect_length_candidates`'s docstring are all still present.
- **Dim 6 (multiprocessing):** No changes to `pattern_detector_parallel.py`; `sequence`/
  `valid_events` still shipped once via `ProcessPoolExecutor(initializer=...)`, module-level
  worker functions confirmed unchanged.
- **Dim 7 (sampling):** Two caps only (`MAX_PATTERN_EVENTS=15000`, `DETECTOR_MAX_EVENTS=
  1000`), shared `sample_events_for_detection`; `frames` (not the sampled detection
  sequence) still drives every exported byte. The one sampling-related defect found this
  cycle (PAT-2026-08-06-A) is a mislabeled banner, not data loss.
- **Dim 8 (bounds/match semantics):** `_find_pattern_matches`'s non-self-overlap discipline
  (#170/PAT-04) and `DrumPatternDetector`'s emergent-scan mirror of that discipline
  (#366/PAT-B, fixed in merged commit `24e51d2`, confirmed present at
  `tracker/pattern_detector.py:676-706` with the exact "pos = start + length ... pos +=
  length" pattern) are both intact. `MIN_PATTERN_OCCURRENCES = 3` exact-occurrence gate
  (#365/PAT-A) still present at `tracker/pattern_detector.py:41-52` and the selection loop.
- **Dim 9 (loops):** `LoopManager.detect_loops` still guards `len(positions) > 1` before
  indexing `positions[-2]`; unchanged since 2026-08-05.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-08-06.md
```
