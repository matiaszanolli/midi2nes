# Pattern Detection & Compression Audit — 2026-07-05

Audit of the pattern-detection and compression subsystem per
`.claude/commands/audit-patterns/SKILL.md`, at HEAD `a7de0d4`. Severity floors from
`.claude/commands/_audit-severity.md`. Dedup against the pre-fetched `/tmp/audit/issues.json`
(open-issue snapshot, 36 entries) and all prior reports in `docs/audits/`, in particular
`docs/audits/AUDIT_PATTERNS_2026-07-03.md`.

**Key fact established first — this subsystem CHANGED since the last audit.** Unlike the
2026-07-03 pass (which found the code byte-for-byte unchanged), two commits since then
directly rewrote the pattern paths:

- `84955f3` — *exact-only pattern positions, honest coverage metric* (#168 PAT-01, #169 PAT-03)
- `69a75b9` — *pattern-matcher overlap divergence* (#170 PAT-04, #171 PAT-05)

All four of #168/#169/#170/#171 are **absent from the open-issue snapshot** → closed. This
audit's job was therefore real verification of those fixes (by independent round-trip, not by
trusting the commit messages) plus a hunt for regressions the rewrites may have introduced.

## What was verified (fixes confirmed in place)

- **PAT-01 / #168 (positions exact-only) — CONFIRMED FIXED.** `PatternDetector.detect_patterns`
  now stores `positions = sorted(set(exact_matches))` (`tracker/pattern_detector.py:247,276`)
  and a separate `occupied_positions` (exact + variation starts) drives non-overlap selection
  (`:295-296`). Independent round-trip: synthetic sequence `motif×3 + filler + transposed-var`,
  detected `pattern_0` positions `[0, 2, 6]` (sequence-index space) — the transposed variation
  at index 8 is **excluded** — and every stored position's window equals the stored `events`
  byte-for-byte. The 2026-07-03 defect (`positions [0,7,14]` with a content mismatch at 14) no
  longer reproduces.
- **PAT-04 / #170 (self-overlap) — CONFIRMED FIXED.** `_find_pattern_matches` now resumes at
  `pos = start_pos + pattern_len` (`tracker/pattern_detector.py:322`). Repro: 12 identical
  notes, length 4, anchor 0 → `[0, 4, 8]` (was `[0, 1, 5]`); period-2 self-similar run, length
  4 → `[0, 4, 8]`. No anchor overlap; matches the parallel `next_free` greedy.
- **PAT-03 / #169 (honest coverage) — CONFIRMED FIXED.** `calculate_compression_stats` gained a
  `total_events` param and emits `coverage_ratio` / `patterned_events`
  (`tracker/pattern_detector.py:816-864`); the ROM banner (`main.py:558-561`) and success line
  (`main.py:929-932`) now print **two** distinctly-labelled numbers ("Pattern dedup ratio" and
  "Pattern coverage") instead of one ambiguous "Compression ratio". (But see PAT-08 below — the
  coverage number is understated under sampling.)
- **PAT-05 / #171 (false equivalence docstring) — CONFIRMED FIXED (doc-only).**
  `_collect_length_candidates`' docstring now states the weaker, correct guarantee
  (`tracker/pattern_detector_parallel.py:278-287`); the commit correctly notes this is a
  metrics-only divergence with no behavior change.
- **CompressionEngine round-trip — CONFIRMED LOSSLESS.** `exporter/compression.py` unchanged.
  Re-ran absent-key delta (note changes, volume constant), a 10-event RLE run, and a 300-case
  seeded fuzz (1–30 events each): all frame-by-frame `==`. The delta decoder still preserves a
  key absent from a delta block (`compression.py:100-107`).
- **Dead code / multiprocessing hygiene — CONFIRMED.** `ThreadedPatternDetector` still gone
  (`grep` matches only a doc comment and the `tests/test_patterns.py:1111-1117` regression
  guard). `_WORKER_SEQUENCE`/`_WORKER_EVENTS` globals + `_init_pattern_worker` /
  `_detect_patterns_worker` remain module-level, picklable, no shared mutable state
  (`pattern_detector_parallel.py:253-346`). `initargs` still ships plain lists of tuples/dicts.
- **Loop manager — CONFIRMED unchanged and now benefits from exact-only positions.**
  `tracker/loop_manager.py` derives loop points from `positions` (now exact-only). The
  jump-table end-key clobber the SKILL flags is guarded: `_optimize_loops` drops any loop whose
  range intersects an already-kept loop (`loop_manager.py:84-89`), so no two survivors can share
  an `end`. Register/read-back key `f"loop_{end}_{start}"` matches (`:130`, `:156`).
- **Test suite — 90/90 pattern tests pass** (`test_patterns.py`, `test_compression.py`,
  `test_pattern_integration.py`, `test_pattern_detector_parallel.py`; 225s).

## Summary

**Round-trip result: LOSSLESS, and materially improved since 2026-07-03.** The sequential
detector's `positions`/`references` are now exact-only, closing the PAT-01 latent-CRITICAL. The
default parallel path + `CompressionEngine` remain exact/lossless. No CRITICAL or HIGH defect
was found. One NEW MEDIUM (a coverage-stat accuracy regression introduced by the #169 fix
itself under sampling) and one NEW LOW (stub schema drift) were identified; three prior findings
remain open.

### Finding counts
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 1 NEW (PAT-08 coverage understated under sampling)
- LOW: 1 NEW (PAT-09 `--no-patterns` stub omits `variations`) + 3 existing (PAT-06 #172,
  PAT-07 #173, P-09 #106)

### 3 highest-leverage fixes
1. **PAT-08 (NEW, MEDIUM)** — `coverage_ratio` divides sampled-space `patterned_events` by
   full-song `total_events`, understating coverage by the sampling ratio on any song past the
   cap (repro: 60→20 sampled, fully-patterned song reports **20%**). Undermines the honesty the
   #169 fix was meant to deliver.
2. **PAT-07 (#172/#173, LOW)** — `_hash_pattern` still returns `hash()` (an int, docstring says
   `str`) with no equality check on collision; free to fix by keying on the tuple itself.
3. **P-09 (#106, LOW)** — per-chunk `except…continue` in the parallel pool still drops a failed
   length's candidates with only a transient `pbar.write`; wants a durable end-of-run warning.

---

## Findings

### PAT-08: `coverage_ratio` divides sampled-space patterned count by full-song total, understating coverage under sampling
- **Severity**: MEDIUM (stat reported inaccurately / misleadingly — `_audit-severity.md` floor)
- **Dimension**: 4 (Compression-Ratio & Stats Accuracy) / 7 (Large-File Sampling)
- **Location**: `tracker/pattern_detector.py:404` (`total_events = len(events)` captured
  pre-sampling), `:847-854` (`patterned_events` / `coverage_ratio` computed over the sampled
  sequence); parallel twin at `tracker/pattern_detector_parallel.py:48,77-79`. Trigger site:
  `main.py:745` passes the full `events` list straight into `detector.detect_patterns` with no
  pre-sampling on the default parallel path.
- **Status**: NEW (introduced by the #169/PAT-03 fix in `84955f3`; not previously reported)
- **Description**: `coverage_ratio = patterned_events / total_events * 100`. `total_events` is
  captured as `len(events)` **before** the detector's internal uniform sampling
  (`pattern_detector.py:200-203` seq, `pattern_detector_parallel.py:61` par), while
  `patterned_events` (`== original_size`) is summed over the **sampled** sequence's positions.
  The two operands live in different spaces: for any song exceeding the cap (`DETECTOR_MAX_EVENTS
  = 1000` sequential, `MAX_PATTERN_EVENTS = 15000` parallel), the numerator can be at most the
  sampled size while the denominator is the full song, so the reported coverage is scaled down by
  ~`(sampled / total)`.
- **Evidence**: Direct repro — a 60-event, period-4 (i.e. ~fully patterned) sequence with the
  cap forced to 20:
  ```
  Warning: Large sequence (60 events), uniformly sampling to 20 for performance
  total_events= 60  patterned_events= 12  coverage_ratio= 20.0
  ```
  The song is essentially 100% patterned, but the banner would print "Pattern coverage: 20.0% of
  60 events". `main.py:745` confirms the default parallel path does not pre-sample, so this fires
  in production for songs > 15000 events. (The `detect-patterns` subcommand and the sequential
  *fallback* pre-sample before calling `detect_patterns`, so `total_events` already equals the
  retained count there and the mismatch does not occur on those two paths.)
- **Impact**: Metrics-only (no ROM byte — every emitted byte still derives from `frames`, #4).
  Direction is conservative (understates, never over-claims a compression win), so it is not the
  "96% on an unpatterned song" over-claim #169 fixed — but it is the same class of misleading
  number the `coverage_ratio` field was *added* to prevent, now wrong for large songs on the
  default path. A user could wrongly conclude a large, highly-repetitive song is barely
  compressible.
- **Related**: #169/PAT-03 (the fix this regresses), #21/#100 (sampling policy), #176/PL-03
  (approximate-stats warning already printed on the fallback path only).
- **Suggested Fix**: Compute `coverage_ratio` against the size of the sequence actually analyzed
  (`len(sampled_sequence)`), not the pre-sampling `total_events`; or scale `patterned_events` by
  `total_events / sampled_len`; or, minimally, when sampling triggered, relabel the banner as
  "of N sampled events" and surface the same approximate-stats note the fallback path already
  prints (`main.py:760-766`).

---

### PAT-09: `--no-patterns` direct-export stub omits the top-level `variations` key both detectors always emit
- **Severity**: LOW (schema drift, currently unread — defense-in-depth)
- **Dimension**: 2 (`pattern_result` Schema Integrity)
- **Location**: `main.py:779-791`
- **Status**: NEW as a filed finding (documented as "LOW/doc-only" in the SKILL; no tracking
  issue exists — the #104 fix aligned the `stats` sub-keys but left the top-level `variations`
  key off the stub)
- **Description**: Both real producers return a 4-key envelope `{patterns, references, stats,
  variations}` (`pattern_detector.py:427-432`, `pattern_detector_parallel.py:84-89`). The
  `--no-patterns` stub returns only `{patterns, references, stats}` — no `variations`. The
  `stats` sub-schema was reconciled with the detectors by #104 (all 7 keys present here,
  verified), but the top-level key set still drifts by one.
- **Evidence**: `grep -rn "\['variations'\]" main.py exporter/ nes/` finds **no consumer** of
  `pattern_result['variations']` outside the detectors/tests, so nothing `KeyError`s today; the
  stub dict at `main.py:779-791` has keys `patterns`, `references`, `stats` only.
- **Impact**: None today (unread). Latent: the exact same latent-trap class as the #104 bug that
  *was* fixed — the first consumer to do `pattern_result['variations']` unconditionally would
  `KeyError` only on the `--no-patterns` path, i.e. only under a flag combination tests may not
  cover.
- **Related**: #104 (closed, fixed the sibling `stats` drift), PAT-06/#172 (the *inner* variation
  shape also drifts between the two detectors).
- **Suggested Fix**: Add `'variations': {}` to the stub dict so all three producers emit an
  identical top-level key set.

---

### Existing open findings (re-verified present, unchanged)

- **PAT-06 / #172** (LOW) — `_get_variation_summary` inner shape still drifts:
  `pattern_detector.py:491-501` emits `{variation_count, transposition_range, volume_range}`;
  `pattern_detector_parallel.py:231-239` emits `{variation_count, exact_matches}`. Unread today.
  Still OPEN.
- **PAT-07 / #173** (LOW) — `_hash_pattern` (`pattern_detector.py:812-814`) still returns
  `hash(tuple(...))` (a 64-bit int) despite the `-> str` hint / docstring, used as the sole
  dedup key in `compress_patterns` (`:790-800`) with no equality check on a hit. Collision would
  silently merge two different patterns' positions. Astronomically unlikely; free fix. Still OPEN.
- **P-09 / #106** (LOW) — the per-chunk `except Exception … continue`
  (`pattern_detector_parallel.py:159-162`) inside the whole-pool-succeeded path still drops a
  failed length's candidates with only a transient `pbar.write` and no durable end-of-run
  warning (unlike the whole-pool failure, which has a serial fallback). Metrics-only (#4). Still
  OPEN.

### Existing findings resolved-by-code but OPEN on the tracker

- **P-08 / #105** — `ThreadedPatternDetector` dead-code race. The class no longer exists; only a
  doc comment and a regression guard (`tests/test_patterns.py:1111-1117`) remain. The GitHub
  issue should be closed as fixed-by-code; not re-filed.

---

## Conclusion

Since 2026-07-03, this subsystem received real fixes: the sequential detector's
`positions`/`references` are now exact-only (PAT-01 closed — the biggest latent risk), the
self-overlapping matcher is corrected (PAT-04 closed), and honest coverage reporting was added
(PAT-03 closed). All four were independently verified by fresh round-trip reproduction, not by
trusting the commit messages; the compression engine remains lossless; 90/90 pattern tests pass.

The rewrites introduced one MEDIUM accuracy regression — the new `coverage_ratio` understates on
sampled (large) songs because its numerator and denominator are measured in different event
spaces (PAT-08) — plus one LOW schema-drift (PAT-09). Three prior LOW findings (PAT-06/#172,
PAT-07/#173, P-09/#106) remain open and unchanged. No CRITICAL or HIGH defect exists in the
pattern-detection/compression path today.

Suggested next step:
```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-07-05.md
```
