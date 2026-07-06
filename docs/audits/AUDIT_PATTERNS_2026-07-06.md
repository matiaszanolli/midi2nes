# Pattern Detection & Compression Audit — 2026-07-06

Audit of the pattern-detection and compression subsystem per
`.claude/commands/audit-patterns/SKILL.md`, at HEAD `8308a63`. Severity floors from
`.claude/commands/_audit-severity.md`. Deduplicated against the pre-fetched
`/tmp/audit/issues.json` (29 open issues) and all prior reports in `docs/audits/`, in
particular `docs/audits/AUDIT_PATTERNS_2026-07-05.md`.

## Key fact established first — every prior-audit finding is now fixed in code

The 2026-07-05 pass left five open pattern findings (PAT-06/#172, PAT-07/#173, PAT-08/#257,
PAT-09/#258, P-09/#106). All five were merged **after** that audit:

- `27104cd` — recover failed pattern-detection chunk in-process, warn on real loss (#106)
- `7aeabac` — unify variation-summary shape; key pattern dedup on exact tuple (#172, #173)
- `e2cccc0` — measure coverage_ratio in analyzed event space; add variations to no-patterns
  stub (#257, #258)

None of #106/#172/#173/#257/#258 (nor the older #168/#169/#170/#171/#104/#101/#4) appears in
the open-issue snapshot → all closed. This audit therefore independently re-verified each fix
(by fresh round-trip and code re-read, not by trusting commit messages) and hunted for
regressions the rewrites may have introduced.

## What was verified (all confirmed in place)

- **Round-trip integrity — LOSSLESS (headline result).**
  - Sequential `EnhancedPatternDetector.detect_patterns`: synthetic sequence of 4× an exact
    length-3 motif + a transposed (+5) variation. Every stored `positions` entry's window
    equals the pattern's stored `events` byte-for-byte; the transposed variation is **excluded**
    from `positions`/`references` (PAT-01/#168 exact-only invariant holds —
    `tracker/pattern_detector.py:255,284`; overlap still blocked via the non-persisted
    `occupied_positions`, `:303-304,315`).
  - `_find_pattern_matches` resumes at `start_pos + pattern_len`
    (`tracker/pattern_detector.py:330`) — no self-overlap on period-<length runs (PAT-04/#170).
  - `CompressionEngine` (`exporter/compression.py`, unchanged since 2025-07-20): 2000-case
    seeded fuzz (1–30 events, mixed `note`/`volume`/`sample_id`/`duty` keys) all frame-by-frame
    `==`; the absent-key delta decoder (`compression.py:100-107`) preserves a key whose diff was
    0 (verified: constant `volume` + static `duty` across a delta block round-trips exactly).
    `_can_delta_compress`/`_create_delta_block` agree on `numeric_keys = {note, volume,
    sample_id}` (`:157,185`).
- **Schema integrity — unified across all three producers.** Both detectors and the
  `--no-patterns` stub emit the same 4-key envelope `{patterns, references, stats, variations}`
  and the identical 7-key `stats` set (`compression_ratio, original_size, compressed_size,
  unique_patterns, total_events, patterned_events, coverage_ratio`). Verified by direct dict
  inspection. `_get_variation_summary` now emits the SAME inner shape on both paths
  (`{variation_count, exact_match_count, transposition_range, volume_range}` —
  `pattern_detector.py:502-520`, `pattern_detector_parallel.py:256-272`) (PAT-06/#172). The
  `--no-patterns` stub carries `'variations': {}` (`main.py:880`) (PAT-09/#258).
- **`_hash_pattern` keys on the raw `(note, volume)` tuple**, not `hash()`
  (`pattern_detector.py:831-841`) — collision-free dedup key (PAT-07/#173).
- **Coverage stat measured in analyzed (post-sampling) space** (PAT-08/#257): `total_events`
  comes from `_last_analyzed_count` (`pattern_detector.py:418`) / post-sampling `len(valid_events)`
  (`pattern_detector_parallel.py:70`), so numerator and denominator now share the sampled space.
- **`references` is not consumed by the exporter** — `export_tables_with_patterns`
  (`exporter/exporter_ca65.py:962-971`) documents and honors this; a `grep` of `references` in
  that file shows only the parameter, docstring, and an unrelated comment (#4 contract intact).
  `patterns` truthiness is the sole direct-vs-bytecode switch.
- **Parallel path & multiprocessing hygiene** — `_init_pattern_worker`/`_detect_patterns_worker`
  module-level; `_WORKER_SEQUENCE`/`_WORKER_EVENTS` shipped once via `initargs`
  (`pattern_detector_parallel.py:146-150,289-298`); per-chunk failure recovered in-process and a
  durable end-of-run warning names lost lengths (`:171-192`) (P-09/#106). Deterministic
  `(-score, start, length)` tie-break (`:227`).
- **Loop manager** (`tracker/loop_manager.py`, unchanged) — consumes exact-only `positions`;
  `_optimize_loops` drops range-overlapping loops so no two survivors share an `end` jump-table
  key; register/read-back key `f"loop_{end}_{start}"` matches (`:130,156`).
- **Test suite** — 102/102 pattern tests pass (`test_patterns.py`, `test_compression.py`,
  `test_pattern_integration.py`, `test_compression_integration.py`,
  `test_pattern_detector_parallel.py`; 213s).

## Summary

**Round-trip result: LOSSLESS.** No CRITICAL, HIGH, or MEDIUM defect exists in the
pattern-detection/compression path today. Every finding from the prior audit has been fixed and
independently re-verified. Two NEW LOW findings were identified — both hardening/observability
gaps on paths that currently produce correct output; neither affects any emitted ROM byte
(#4).

### Finding counts
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 2 NEW (PAT-10 untested exact-only invariant; PAT-11 coverage collapse under lossy sampling)

### 3 highest-leverage fixes
1. **PAT-10 (LOW)** — add one assertion pinning the exact-only round-trip invariant (each
   referenced window `==` the pattern's stored `events`); today only `int`-typed positions are
   asserted, so a PAT-01 regression would pass CI silently.
2. **PAT-11 (LOW)** — when reporting `coverage_ratio` on a sampled (large) song, surface that the
   number describes the *sampled* sequence; uniform `np.linspace` sampling can put the sample
   points out of phase with a song's period and collapse reported coverage to ~1% on a genuinely
   ~100%-periodic song.
3. Nothing else outstanding in this subsystem.

---

## Findings

### PAT-10: No test pins the exact-only round-trip invariant (referenced window == pattern events)
- **Severity**: LOW (missing/weak coverage on a path that currently works — `_audit-severity.md`)
- **Dimension**: 1 (Round-Trip Integrity)
- **Location**: `tests/test_pattern_integration.py:120-137` (`test_pattern_positions_format`)
- **Status**: NEW (called out as an untested invariant in the SKILL, Dimension 1; not
  previously filed)
- **Description**: The PAT-01/#168 fix guarantees each persisted `positions` entry anchors a
  window whose `(note, volume)` content equals the pattern's stored `events`. This invariant
  holds in code (independently re-verified this audit), but the closest test only asserts that
  positions are `list`s of `int` — it never dereferences a position back into the sequence to
  confirm the window matches `events`. A regression that re-admitted variation/self-overlap
  positions into `positions` (the exact defect #168/#170 fixed) would leave this test green.
- **Evidence**:
  ```python
  # tests/test_pattern_integration.py:129-137
  for pos in base_pattern['positions']:
      self.assertIsInstance(pos, int)
  ...
  for pos in enhanced_pattern['positions']:
      self.assertIsInstance(pos, int)
  ```
  No assertion compares `sequence[pos:pos+length]` against `pattern['events']`. Manual
  round-trip this audit (motif×4 + transposed variation) confirmed the invariant currently
  holds — but nothing in the suite would catch its loss.
- **Impact**: None today (invariant holds). Latent: a regression of the highest-risk property in
  this subsystem (positions must be true exact repeats — the CRITICAL round-trip guarantee)
  would not be caught by the test named for exactly this check.
- **Related**: #168/PAT-01 (the invariant this would guard), #170/PAT-04 (self-overlap, same
  class), PAT-11 below.
- **Suggested Fix**: In `test_pattern_positions_format`, for each pattern assert
  `[(e['note'], e['volume']) for e in pattern['events']] ==
  [sequence[p+k] for k in range(pattern['length'])]` for every `p` in `positions`, on a fixture
  with a known transposed/self-similar decoy so the assertion has teeth.

---

### PAT-11: `coverage_ratio` can collapse to ~1% on a fully-periodic song once uniform sampling triggers
- **Severity**: LOW (metrics-only; documented lossy behavior; ROM bytes unaffected per #4 —
  below the MEDIUM "inaccurate stat" floor because the number is *truthful for the analyzed
  sequence* and is accompanied by a sampling warning)
- **Dimension**: 4 (Compression-Ratio & Stats Accuracy) / 7 (Large-File Sampling)
- **Location**: `tracker/pattern_detector.py:26-38` (`sample_events_for_detection`, `np.linspace`),
  consumed via `pattern_detector.py:204-207` (sequential) and
  `pattern_detector_parallel.py:60` (parallel); coverage computed at
  `pattern_detector.py:879-881`.
- **Status**: NEW (distinct mechanism from the now-fixed PAT-08/#257 space-mismatch; not
  previously reported)
- **Description**: PAT-08 fixed the numerator/denominator *space* mismatch — coverage is now
  measured against the post-sampling analyzed count, which is correct. But a second, separate
  effect remains: uniform `np.linspace(0, n-1, cap)` sampling of a song whose musical period
  does not divide the sampling stride puts the retained samples **out of phase** with the
  period, destroying the exact repeats the detector keys on. A genuinely ~100%-periodic song
  can therefore report near-zero `coverage_ratio` after sampling.
- **Evidence**: Direct repro — a 4000-event, period-3 song (`(60,100),(62,90),(64,80)` repeated),
  sequential cap `DETECTOR_MAX_EVENTS = 1000`:
  ```
  total_events=1000 patterned_events=12 coverage_ratio=1.2
  num patterns: 1  ->  pattern_0 len=12 npos=1
  ```
  The stride ≈ 3999/999 ≈ 4.003 slips phase against period 3, so almost no length-≥3 window
  repeats exactly in the sampled sequence; the banner would print "Pattern coverage: 1.2% of
  1000 events" for an essentially fully-repetitive song. Fires only for songs exceeding the cap
  (>1000 events sequential, >15000 parallel); both paths print a sampling warning first
  (`pattern_detector.py:205`, `pattern_detector_parallel.py:62`).
- **Impact**: Metrics/observability only — every exported ROM byte still derives from `frames`,
  not from the sampled detection sequence (#4), so playback is unaffected. Direction is
  conservative (understates coverage, never over-claims a compression win). A user inspecting the
  banner or the `detect-patterns` JSON for a large, highly-repetitive song could wrongly conclude
  it is unpatterned.
- **Related**: #257/PAT-08 (the space-mismatch coverage fix this sits adjacent to), #100/#21
  (uniform-sampling policy), #176/PL-03 (approximate-stats warning already printed on the
  sequential-fallback path only).
- **Suggested Fix**: When sampling triggered, label the coverage line as measured "over the N
  sampled events (lossy — detection quality reduced)" so the number is not read as a property of
  the full song; the same approximate-stats note the sequential-fallback path already emits
  (`main.py:846-852`) could be surfaced on the primary parallel path too. No behavior change to
  detection or export is warranted — the sampling itself is a documented, intentional
  performance trade-off.

---

## Conclusion

The pattern-detection/compression subsystem is in its healthiest state across the audit history.
Since 2026-07-05 all five remaining open findings were fixed (#106/#172/#173/#257/#258), and
this audit independently re-verified every one by fresh round-trip and code re-read rather than
trusting commit messages: positions are exact-only and each round-trips byte-for-byte, both
detectors and the `--no-patterns` stub share one schema, `_hash_pattern` keys on the raw tuple,
the parallel pool recovers and durably warns on failed chunks, and the `CompressionEngine`
remains lossless under a 2000-case fuzz. 102/102 pattern tests pass. No CRITICAL, HIGH, or
MEDIUM defect exists today.

The two NEW findings are both LOW hardening gaps that do not affect any emitted ROM byte: an
untested exact-only invariant that would let a round-trip regression pass CI (PAT-10), and a
metrics-only coverage collapse when uniform sampling falls out of phase with a song's period
(PAT-11).

Suggested next step:
```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-07-06.md
```
