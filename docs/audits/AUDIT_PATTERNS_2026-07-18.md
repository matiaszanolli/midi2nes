# Pattern Detection & Compression Audit — 2026-07-18

Audit of the pattern-detection and compression subsystem per
`.claude/commands/audit-patterns/SKILL.md`, at HEAD `b562e1d`. Severity floors from
`.claude/commands/_audit-severity.md`. Deduplicated against the pre-fetched
`/tmp/audit/issues.json` (27 open issues, none labeled `patterns`) and all prior reports in
`docs/audits/`, in particular `docs/audits/AUDIT_PATTERNS_2026-07-06.md`.

## Key fact established first — the subsystem is unchanged since the last audit

`git log 8308a63..HEAD` (the 16 commits since the 2026-07-06 pattern audit's HEAD) touches
none of `tracker/pattern_detector.py`, `tracker/pattern_detector_parallel.py`,
`exporter/compression.py`, `tracker/loop_manager.py`, or the pattern-detection sections of
`main.py`. The only change anywhere near this subsystem is `c1b52d9` (#298/EXP-10), which adds
tone-channel note-clamp reporting to `CA65Exporter.export_tables_with_patterns` — an
exporter-domain fix that derives entirely from `frames` (loops over
`frames[channel]`/`channel_frames`, not `patterns`/`references`) and does not touch the
`references`-is-unconsumed contract. This audit therefore re-verified the 2026-07-06 findings
independently (fresh round-trip, fresh code read) rather than assuming carry-forward, and
confirmed no regression and no new defect.

## What was verified (all confirmed in place, independently)

- **Round-trip integrity — LOSSLESS (headline result).** Built a fresh synthetic sequence (4×
  exact length-3 motif, one +5-transposed variation, a 10-note period-1 self-similar run) and
  ran it through `EnhancedPatternDetector.detect_patterns`. For every detected pattern, dereferenced
  every entry in both `patterns[id]['positions']` and the returned `references[id]` back into the
  source sequence and diffed against `patterns[id]['events']` — all matched byte-for-byte; the
  transposed variation was correctly excluded from both `positions` and `references` (PAT-01/#168
  exact-only invariant holds, `tracker/pattern_detector.py:255,284`). `stats` and `variations`
  came back in the unified 7-key / 4-key shape (see below).
- **`_find_pattern_matches` resumes at `start_pos + pattern_len`**
  (`tracker/pattern_detector.py:330`) — confirmed no self-overlap match against the period-1 run
  in the synthetic test (PAT-04/#170).
- **Delta-compression decoder preserves absent keys.** Re-read `exporter/compression.py:100-107`:
  the decoder copies `current_event` forward each step and only mutates keys present in a delta
  dict; since `_create_delta_block` (`:184-200`) only emits a key when `diff != 0`, a key whose
  diff was 0 for a step is simply never touched, so its previous value survives. `_can_delta_compress`
  (`:154-177`) and `_create_delta_block` agree on `numeric_keys = {note, volume, sample_id}`.
- **Schema integrity — unified across all three producers.** Re-read
  `EnhancedPatternDetector.detect_patterns` (`pattern_detector.py:396-443`),
  `ParallelPatternDetector.detect_patterns` (`pattern_detector_parallel.py:31-94`, plus its
  no-events/`_empty_result` returns), and the `--no-patterns` stub in `run_full_pipeline`
  (`main.py:886-914`): all three emit the identical top-level `{patterns, references, stats,
  variations}` envelope and the identical 7-key `stats` set (`compression_ratio, original_size,
  compressed_size, unique_patterns, total_events, patterned_events, coverage_ratio`).
  `_get_variation_summary` emits the same inner shape on both detector paths
  (`{variation_count, exact_match_count, transposition_range, volume_range}` —
  `pattern_detector.py:502-520`(names may shift line-to-line but shape confirmed),
  `pattern_detector_parallel.py:256-272`).
- **`_hash_pattern` keys on the raw `(note, volume)` tuple**, not `hash()`
  (`pattern_detector.py:831-841`) — collision-free dedup key (PAT-07/#173).
- **`references` is not consumed by the exporter.** Re-read `export_tables_with_patterns`
  (`exporter/exporter_ca65.py:962-971`): the docstring states and the body honors that
  `references` is unused; `patterns` truthiness is the sole direct-vs-bytecode switch
  (`:973-974`). A full `grep -n references exporter/exporter_ca65.py` shows only the parameter
  and the docstring — zero read sites (#4 contract intact, including through the new #298
  clamp-reporting code, which reads only `frames`).
- **Parallel path & multiprocessing hygiene** — `_init_pattern_worker`/`_detect_patterns_worker`
  are module-level (picklable); `_WORKER_SEQUENCE`/`_WORKER_EVENTS` are shipped once via
  `ProcessPoolExecutor(initializer=..., initargs=(sequence, valid_events))`
  (`pattern_detector_parallel.py:146-150`) rather than per chunk; a single work chunk skips pool
  construction entirely (`:130-132`, #218); the pool is capped to
  `min(max_workers, len(work_chunks))` (`:139`, #218); a per-chunk failure is recovered
  in-process via `_collect_length_candidates` and only a length that also fails the serial retry
  is recorded in `failed_lengths` and surfaced by a durable end-of-run warning (`:161-192`,
  P-09/#106); a pool-wide exception falls back to `_detect_patterns_serial`, which reuses the
  same `_select_best_patterns` wrapper as the parallel path (`:182-185`, `:214`) — so the fallback
  never bypasses compression/stats. Deterministic `(-score, start, length)` tie-break (`:227`,
  #46).
- **Loop manager** (`tracker/loop_manager.py`, unchanged) — consumes exact-only `positions`;
  `_optimize_loops` removes range-overlapping loops so no two survivors share an `end` jump-table
  key (`:84-90`); `EnhancedLoopManager`'s register key `f"loop_{end}_{start}"` (`:130`) matches
  what `generate_jump_table` reads back (`:156`).
- **Sampling caps stay non-shadowing and configurable.** `MAX_PATTERN_EVENTS = 15000` (parallel)
  and `DETECTOR_MAX_EVENTS = 1000` (sequential), both overridable per-instance since #219, both
  fed through the same `sample_events_for_detection` (uniform `np.linspace`, not head-cut).
  Confirmed the exported song still derives solely from `frames`, never from the
  sampled detection sequence (#4) — sampling only degrades pattern-detection *quality* and the
  `coverage_ratio`/`compression_ratio` metrics, never ROM bytes.

## Summary

**Round-trip result: LOSSLESS (independently re-confirmed).** No CRITICAL, HIGH, or MEDIUM
defect exists in the pattern-detection/compression path today. Nothing in this subsystem has
changed since the 2026-07-06 audit, and every finding from that audit re-verified clean. The two
LOW findings from that report remain outstanding (unfiled as GitHub issues — no `patterns`-labeled
issue exists in the current open set) and are restated here for continuity; no new defect was
found.

### Finding counts
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 2 (PAT-10, PAT-11 — both carried forward from `AUDIT_PATTERNS_2026-07-06.md`, still unfiled)

### 3 highest-leverage fixes
1. **PAT-10 (LOW)** — add one assertion pinning the exact-only round-trip invariant (each
   referenced window `==` the pattern's stored `events`) to `test_pattern_positions_format`; today
   only `int`-typed positions are asserted, so a PAT-01 regression would pass CI silently.
2. **PAT-11 (LOW)** — label `coverage_ratio` as measured over the *sampled* sequence when
   sampling triggers, since uniform `np.linspace` sampling can fall out of phase with a song's
   period and collapse reported coverage to ~1% on a genuinely ~100%-periodic song.
3. Nothing else outstanding in this subsystem — consider filing PAT-10/PAT-11 as GitHub issues
   via `/audit-publish` so they stop being re-derived by every subsequent pass.

---

## Findings

### PAT-10: No test pins the exact-only round-trip invariant (referenced window == pattern events)
- **Severity**: LOW (missing/weak coverage on a path that currently works — `_audit-severity.md`)
- **Dimension**: 1 (Round-Trip Integrity)
- **Location**: `tests/test_pattern_integration.py:120-137` (`test_pattern_positions_format`)
- **Status**: NEW (restates the same finding from `docs/audits/AUDIT_PATTERNS_2026-07-06.md`,
  which was never filed as a GitHub issue — no `patterns`-labeled issue exists in the current
  open-issue snapshot. Independently re-confirmed unfixed this pass: `git diff 8308a63 HEAD --
  tests/test_pattern_integration.py` is empty.)
- **Description**: The PAT-01/#168 fix guarantees each persisted `positions` entry anchors a
  window whose `(note, volume)` content equals the pattern's stored `events`. This invariant
  holds in code (independently re-verified this audit via a fresh round-trip — see Summary), but
  the closest test only asserts that positions are `list`s of `int` — it never dereferences a
  position back into the sequence to confirm the window matches `events`. A regression that
  re-admitted variation/self-overlap positions into `positions` (the exact defect #168/#170 fixed)
  would leave this test green.
- **Evidence**:
  ```python
  # tests/test_pattern_integration.py:129-137
  for pos in base_pattern['positions']:
      self.assertIsInstance(pos, int)
  ...
  for pos in enhanced_pattern['positions']:
      self.assertIsInstance(pos, int)
  ```
  No assertion compares `sequence[pos:pos+length]` against `pattern['events']`. This audit's own
  round-trip script (motif×4 + transposed variation + self-similar run) confirmed the invariant
  currently holds for both `positions` and `references` — but nothing in the suite catches its
  loss.
- **Impact**: None today (invariant holds). Latent: a regression of the highest-risk property in
  this subsystem (positions must be true exact repeats — the CRITICAL round-trip guarantee) would
  not be caught by the test named for exactly this check.
- **Related**: #168/PAT-01 (the invariant this would guard), #170/PAT-04 (self-overlap, same
  class), PAT-11 below, `AUDIT_PATTERNS_2026-07-06.md` (original report of this gap).
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
- **Status**: NEW (restates the same finding from `docs/audits/AUDIT_PATTERNS_2026-07-06.md`,
  which was never filed as a GitHub issue. Independently re-confirmed unfixed this pass: `git
  diff 8308a63 HEAD -- tracker/pattern_detector.py` is empty.)
- **Description**: PAT-08/#257 fixed the numerator/denominator *space* mismatch — coverage is
  correctly measured against the post-sampling analyzed count. A separate effect remains:
  uniform `np.linspace(0, n-1, cap)` sampling of a song whose musical period does not divide the
  sampling stride puts the retained samples out of phase with the period, destroying the exact
  repeats the detector keys on. A genuinely ~100%-periodic song can therefore report near-zero
  `coverage_ratio` after sampling triggers.
- **Evidence**: Code re-read confirms the mechanism is unchanged from the prior audit's repro
  (a 4000-event, period-3 song sampled to the sequential detector's 1000-event cap; stride
  ≈3999/999≈4.003 slips phase against period 3, collapsing detected coverage to ~1%). Fires only
  for songs exceeding the cap (>1000 events sequential, >15000 parallel); both paths print a
  sampling warning first (`pattern_detector.py:205`, `pattern_detector_parallel.py:62`).
- **Impact**: Metrics/observability only — every exported ROM byte still derives from `frames`,
  not from the sampled detection sequence (#4), so playback is unaffected. Direction is
  conservative (understates coverage, never over-claims a compression win). A user inspecting the
  banner or the `detect-patterns` JSON for a large, highly-repetitive song could wrongly conclude
  it is unpatterned.
- **Related**: #257/PAT-08 (the space-mismatch coverage fix this sits adjacent to), #100/#21
  (uniform-sampling policy), #176/PL-03 (approximate-stats warning already printed on the
  sequential-fallback path only), `AUDIT_PATTERNS_2026-07-06.md` (original report of this gap).
- **Suggested Fix**: When sampling triggered, label the coverage line as measured "over the N
  sampled events (lossy — detection quality reduced)" so the number is not read as a property of
  the full song; the same approximate-stats note the sequential-fallback path already emits
  (`main.py:846-852`) could be surfaced on the primary parallel path too. No behavior change to
  detection or export is warranted — the sampling itself is a documented, intentional performance
  trade-off.

---

## Conclusion

The pattern-detection/compression subsystem remains in its healthiest state across the audit
history: nothing in `tracker/pattern_detector.py`, `tracker/pattern_detector_parallel.py`,
`exporter/compression.py`, or `tracker/loop_manager.py` has changed since the 2026-07-06 audit,
and this pass independently re-verified — by fresh round-trip and fresh code read, not by
trusting the prior report — that positions are exact-only and round-trip byte-for-byte through
both `positions` and `references`, both detectors and the `--no-patterns` stub share one schema,
`_hash_pattern` keys on the raw tuple, the parallel pool recovers and durably warns on failed
chunks, the serial fallback re-wraps through the same compression/stats path, the delta decoder
preserves zero-diff keys, and the exporter still never reads `references`. No CRITICAL, HIGH, or
MEDIUM defect exists today.

The two LOW findings (PAT-10, PAT-11) are unchanged carry-overs from the prior audit — neither
has been filed as a GitHub issue yet, so both are restated here rather than silently dropped.
Both are hardening/observability gaps that do not affect any emitted ROM byte.

Suggested next step:
```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-07-18.md
```
