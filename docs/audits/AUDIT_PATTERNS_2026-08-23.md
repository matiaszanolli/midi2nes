# Pattern Detection & Compression Audit — 2026-08-23

## Summary

**Round-trip result: LOSSLESS CONFIRMED — freshly re-verified against today's tree** with a
new 208-assertion harness (`/tmp/audit/roundtrip_test.py`), run live rather than trusted from
a prior report's numbers. It exercised both real producers end to end and dereferenced **every**
persisted `positions`/`references` entry back into its source sequence, comparing window
content against stored `events` element-by-element, plus double-claim and envelope-shape checks:

1. `EnhancedPatternDetector.detect_patterns` on six fixtures — simple exact repeats, a
   transposed-decoy sequence (#168/#170 defect class), a self-similar run (period 1, the
   PAT-04/#170 probe), a 180-event mixed sequence that exceeds the now-lowered
   `DETECTOR_MAX_EVENTS = 300` (#459) and exercises internal sampling, a #365/PAT-A
   variation-vs-exact-gate probe, and edge cases (empty/1-event/2-event/`max<min`):
   **0 mismatches**, no frame double-claimed by two retained patterns, `len(events) == length`
   for every pattern.
2. `ParallelPatternDetector.detect_patterns` on both its paths — the sub-`SERIAL_EVENT_THRESHOLD`
   serial path and a 350-event `ProcessPoolExecutor` run: **0 mismatches**,
   `references == positions` for every pattern, `len(events) == length` for every pattern.
3. Both detectors' empty/4-key envelope (`patterns`/`references`/`stats`/`variations`) confirmed
   identical on every fixture including edge cases.

**This audit lands two days after `AUDIT_PATTERNS_2026-08-21.md`.** In the interim, commit
`efecc87` (2026-08-22) fixed **all four** of that report's findings as GitHub issues
**#435, #436, #437, #438**, and commit `d9feba1` (2026-08-22, #459) re-landed the
`DETECTOR_MAX_EVENTS` 1000→300 recalibration that had been closed under #352 but never reached
master. Both are verified fixed in the live tree (not just closed-by-label):
- `main.py`'s `--no-patterns` stub now sizes `direct_size` via the shared `frames_to_events`
  extractor (`main.py:1171`), no longer double-counting the `dpcm_sample_map` side table (#435).
- `parse_midi_to_frames_with_analysis` now constructs its detector with
  `max_events=len(note_on_events)` before calling `detect_patterns`, so loop-detection positions
  can no longer land in sampled-index space (#436) — confirmed via `tracker/parser_fast.py`.
- `_analyze_pattern_tempo`/`_analyze_variation_tempos` now read each event's own stamped
  `tempo` field via a new `_event_tempo` helper (`pattern_detector.py:486-498`), mirroring the
  #345/TEMPO-16 fix, instead of misusing `get_tempo_at_tick(index)` (#437).
- `_WORKER_EVENTS` and the `valid_events` parameter are fully removed from
  `_init_pattern_worker`/`initargs` (`tracker/pattern_detector_parallel.py:198-201, 366-373`) —
  `grep -n _WORKER_EVENTS` now returns nothing (#438).
- `DETECTOR_MAX_EVENTS = 300` confirmed at `tracker/pattern_detector.py:36`, consistent across
  all three call sites (`main.py:807-809`, `:1223`, `:1231`) via the shared
  `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` constants (`constants.py:18-19`).

A separate, pattern-adjacent commit `7839c4e` (#460, consolidating the velocity/volume dual-key
read into `core/events.py`) touched `tracker/pattern_detector.py`'s `DrumPatternDetector`
similarity scorer — verified it preserves the deliberate `default=100` semantics rather than
silently dropping to the new module default of `0` (see Dimension 8 notes). No other commit
since 2026-08-21 touches `tracker/pattern_detector*.py`, `tracker/loop_manager.py`, or the
`references`-is-unconsumed contract in `exporter/exporter_ca65.py` (spot-checked directly:
`export_tables_with_patterns`'s `references` parameter is still never read after the docstring,
`exporter/exporter_ca65.py:1628-1648`), and both pipeline entry points (`main.py:717-720`,
`main.py:1303-1316`) still pass the real dict rather than a hardcoded `{}` (#379 symmetry intact).

**Finding counts:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 3 · **Total 3**
(all 3 are carried forward, still-unfixed, never-filed findings from the 2026-08-21 and
2026-08-07 reports — no new defects found this cycle).

**3 highest-leverage fixes** (all cosmetic/hygiene, none blocking):
1. **PAT-2026-08-23-1 (LOW)** — `run_detect_patterns`'s on-disk JSON still omits the documented
   `variations` key; one-line addition closes the last schema gap from #104/#258's unification.
2. **PAT-2026-08-23-2 (LOW)** — `PatternDetector._optimize_patterns` is still dead code with a
   diverging, unshared scoring formula — delete it or wire it to `score_pattern`.
3. **PAT-2026-08-23-3 (LOW)** — `audit-patterns/SKILL.md`'s line citations are stale again
   (only the `_WORKER_EVENTS`-specific prose was corrected by efecc87); a fuller `/audit-sync`
   pass is still owed.

---

## Findings

### PAT-2026-08-23-1: `detect-patterns` subcommand's persisted JSON still omits the documented `variations` key
- **Severity**: LOW
- **Dimension**: Dimension 2 (`pattern_result` Schema Integrity)
- **Location**: `main.py:834-838` (`run_detect_patterns`'s `output` dict)
- **Status**: Existing — carried forward unfixed from `docs/audits/AUDIT_PATTERNS_2026-08-21.md`
  (PAT-2026-08-21-5) and `docs/audits/AUDIT_PATTERNS_2026-08-07.md` (PAT-2026-08-07-A); still
  never published as a GitHub issue, confirmed by searching `/tmp/audit/issues.json` (300 issues,
  open+closed) for "variations"/"on-disk" — no match.
- **Description**: `EnhancedPatternDetector.detect_patterns` returns the 4-key envelope
  (`patterns`/`references`/`stats`/`variations`) — confirmed live via the harness above — but
  the `detect-patterns` subcommand only persists three of the four keys to disk:
  ```python
  output = {
      'patterns': pattern_result['patterns'],
      'references': pattern_result['references'],
      'stats': pattern_result['stats']
  }
  ```
  `pattern_result['variations']` is silently discarded before `json.dumps`. This is distinct
  from the fixed #258/PAT-09 (the in-memory `--no-patterns` stub, which does now emit
  `'variations': {}`, verified at `main.py:1184-1188`) — this is the on-disk artifact written by
  the *step-by-step* `detect-patterns` subcommand.
- **Evidence**: `main.py:834-838`; contrast with `_audit-common.md`'s documented contract
  ("detect-patterns → dict with keys patterns, references, stats, variations").
- **Impact**: The on-disk stage artifact diverges from the documented inter-stage contract.
  Harmless today — `run_export`'s `load_json_stage(..., ['patterns', 'references'], ...)` only
  requires two keys and never reads `variations` from the file. A future consumer that expects
  parity with the in-memory envelope (e.g. a diagnostics tool reading a saved `detect-patterns`
  JSON) would `KeyError` only on this path, not on the `--no-patterns` stub or either detector's
  direct return value.
- **Related**: #258/PAT-09 (fixed sibling, in-memory stub), #104 (envelope unification),
  prior reports PAT-2026-08-21-5, PAT-2026-08-07-A.
- **Suggested Fix**: Add `'variations': pattern_result['variations']` to the `output` dict at
  `main.py:834-838` (or amend `_audit-common.md`'s contract to explicitly scope the 4-key
  promise to the in-memory return value, not the persisted file, if 3 keys on disk is
  intentional).

### PAT-2026-08-23-2: `PatternDetector._optimize_patterns` remains dead code with an unshared, diverging scoring formula
- **Severity**: LOW
- **Dimension**: Dimension 8 (match semantics) / tech-debt
- **Location**: `tracker/pattern_detector.py:382-419`
- **Status**: Existing — carried forward unfixed from `docs/audits/AUDIT_PATTERNS_2026-08-21.md`
  (PAT-2026-08-21-6) and `docs/audits/AUDIT_PATTERNS_2026-08-07.md` (PAT-2026-08-07-B); never
  published as a GitHub issue.
- **Description**: `_optimize_patterns` is never called by `detect_patterns` (which does its own
  inline non-overlap selection at `:324-346`, the one exercised by this audit's round-trip
  harness) or by any other live code path. It re-implements the same overlap-selection idea
  with a private, unshared score — `(exact_count + variation_count * 0.8) * pattern_length`
  (`:392-396`) — that ignores both the module-level `score_pattern` (#103, the formula the two
  real detectors share) and the #365/PAT-A exact-occurrence gate
  (`len(candidate['positions']) >= MIN_PATTERN_OCCURRENCES`) that the live selection loop now
  enforces. `grep -rn "_optimize_patterns"` (confirmed this session) matches only its own
  definition and one direct unit test (`tests/test_patterns.py:267`) that calls it in isolation
  — no integration path reaches it.
- **Evidence**: `tracker/pattern_detector.py:382` (definition) vs. `:187-346`
  (`detect_patterns`'s actual, self-contained two-pass selection, which is what the round-trip
  harness in this report exercised).
- **Impact**: None at runtime — confirmed no caller exists. Pure drift/maintainability risk: a
  future contributor grepping for "pattern optimization" or extending selection logic could
  reasonably assume this method participates in the real pipeline and patch it instead of the
  inline loop in `detect_patterns`, silently missing both fixes it lacks (#103, #365).
- **Related**: #103 (`score_pattern` unification), #365/PAT-A (exact-occurrence gate),
  #131/TD-03 (prior copy-paste drift noted in this same file), prior reports
  PAT-2026-08-21-6, PAT-2026-08-07-B.
- **Suggested Fix**: Delete `_optimize_patterns` and its isolated test, or — if it's meant as a
  documented alternate strategy — rewrite it on top of `score_pattern` and the same
  `MIN_PATTERN_OCCURRENCES` gate, with a docstring stating who is expected to call it.

### PAT-2026-08-23-3: `audit-patterns/SKILL.md` line citations have drifted again — only the `_WORKER_EVENTS`-specific prose was corrected
- **Severity**: LOW
- **Dimension**: Meta (doc-rot in the audit skill itself)
- **Location**: `.claude/commands/audit-patterns/SKILL.md` (Dimensions 1–8 line citations)
- **Status**: Existing — superset of PAT-2026-08-21-7 (itself a superset of
  PAT-2026-08-07-C); never published as a GitHub issue. `efecc87`'s commit message says it
  "Corrected stale audit-patterns/SKILL.md prose describing the removed `_WORKER_EVENTS` global
  and the renamed worker entry point" and `d9feba1` touched 1 line for the
  `DETECTOR_MAX_EVENTS` value — neither was a full line-number resync, and the broader drift
  the 2026-08-21 report catalogued is confirmed still present today.
- **Description**: Re-checked this session against the live tree — citations still wrong:
  - `main.py:36-37` (cited for `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`) → actually
    `constants.py:18-19` (imported into `main.py` at line 51).
  - `pattern_detector.py:799-829` (`compress_patterns`) → actually `:869-899`.
  - `pattern_detector.py:831-841` (`_hash_pattern`) → actually `:901-911`.
  - `pattern_detector.py:843-891` (`calculate_compression_stats`) → actually `:913+`.
  - `pattern_detector.py:305-323` (selection loop) → the loop starts at `:324`
    (`for candidate in candidate_patterns:`), with the #365 gate check at `:335`.
  - `pattern_detector.py:320-338` (`_find_pattern_matches`) → actually `:361-379`.
  - `pattern_detector_parallel.py:216-254` (`_select_best_patterns`) → actually starts `:286`.
  - `pattern_detector_parallel.py:274-283` (`_empty_result`) → actually `:344`.
  - `main.py:827-853` (pipeline fallback try/except) → actually `:1220-1255`.
  - `main.py:844` (fallback re-trim) → actually `:1238`.
  These are the same offsets (give or take a handful of lines from intervening unrelated edits)
  the 2026-08-21 report already catalogued in its own PAT-2026-08-21-7 — i.e. no drift *fix* has
  landed for these specific citations across two fix cycles, only the narrower `_WORKER_EVENTS`
  wording.
- **Evidence**: Each pair verified by direct `grep -n`/`Read` against the current tree during
  this session (see Dimension-by-Dimension notes below for the exact commands).
- **Impact**: Future audits (including this skill's own next run) chase wrong line numbers,
  costing extra grep/read round-trips to relocate each cited symbol — as this session had to do.
  No functional/runtime impact.
- **Related**: prior reports PAT-2026-08-21-7, PAT-2026-08-07-C, #334/PERF-14, #17, #104.
- **Suggested Fix**: Run `/audit-sync` over `audit-patterns/SKILL.md` for a full line-number
  resync (not just the `_WORKER_EVENTS` prose), then `.claude/commands/_audit-validate.sh`.

---

## Dimension-by-Dimension Verification Notes

- **Dim 1 (round-trip)**: LOSSLESS — see Summary. Fresh harness at `/tmp/audit/roundtrip_test.py`
  (208 checks, 0 failures this run), covering both detectors, both parallel sub-paths
  (serial-threshold and real `ProcessPoolExecutor`), transposed decoys, self-similar runs,
  the #365/PAT-A gate, edge cases, and compressor invariants (`len(events)==length`,
  `references == positions` on the parallel path, no double-claimed frame).
- **Dim 2 (schema)**: Both detectors and the `--no-patterns` stub emit the identical 4-key
  envelope (verified empirically by the harness and by direct read of `main.py:1172-1188`).
  Residual gap: PAT-2026-08-23-1 (on-disk `detect-patterns` file only, not the in-memory value).
- **Dim 3 (offsets/lengths)**: `references == positions`, exact-only, verified per position by
  the harness. `export_tables_with_patterns`'s `references` param confirmed still unread after
  its docstring (`exporter/exporter_ca65.py:1628-1648`) — `patterns` truthiness remains the sole
  direct-vs-macro-bytecode switch. Both pipeline entry points (`main.py:717-720` `run_export`,
  `main.py:1303-1316` `export_frames_and_resolve_mapper`) still pass the real `references` dict
  (#379 symmetry holds).
- **Dim 4 (stats)**: `--no-patterns` stub's `direct_size` now goes through the shared
  `frames_to_events` extractor (`main.py:1171`) instead of a raw `frames.values()` sweep,
  confirming #435's fix — the dpcm_sample_map inflation bug from the 2026-08-21 report is gone.
- **Dim 5 (parallel vs sequential + fallback)**: Inner serial fallback (`_detect_patterns_serial`,
  `pattern_detector_parallel.py:269-284`) returns the bare patterns dict via
  `_select_best_patterns`, and its only caller (`detect_patterns`, `:37-104`) re-wraps it through
  `self.compressor.compress_patterns`/`calculate_compression_stats` before returning the full
  envelope — traced directly this session. The outer `main.py` try/except fallback
  (`:1220-1255`) still constructs `EnhancedPatternDetector` with the same
  `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` and samples to the same `max_events` the sequential
  detector caps at internally.
- **Dim 6 (multiprocessing)**: `_WORKER_EVENTS` confirmed fully removed (`grep -n _WORKER_EVENTS
  tracker/pattern_detector_parallel.py` → no matches) — #438 verified fixed, not just
  closed-by-label. `initargs=(sequence,)` (`:200-201`) ships only the plain-tuple sequence;
  `_init_pattern_worker`/`_detect_window_groups_worker` remain module-level and read only
  `_WORKER_SEQUENCE`.
- **Dim 7 (sampling)**: `DETECTOR_MAX_EVENTS = 300` (`pattern_detector.py:36`, confirming #459's
  re-landed recalibration) and `MAX_PATTERN_EVENTS = 15000` (`:17`) remain the only two caps,
  both driven by the shared `sample_events_for_detection`. `parse_midi_to_frames_with_analysis`
  now sizes its detector to the full track (`max_events=len(note_on_events)`), confirming #436's
  fix — sampled-space loop-position misalignment is closed on that path.
- **Dim 8 (bounds/semantics)**: `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` confirmed shared via
  `constants.py:18-19` across all three call sites. `_find_pattern_matches`'s anchor-skip
  (`pos = start_pos + pattern_len`, `:369`) and `_hash_pattern`'s raw-tuple key (`:901-911`,
  #173) both still in place. The `#460` velocity/volume consolidation
  (`core/events.py`/`event_velocity`) touched `DrumPatternDetector`'s similarity scorer
  (`tracker/pattern_detector.py:628-633`) — verified it explicitly keeps `default=100` (not the
  new module-wide default of `0`) with a comment explaining why a missing value should read as
  "typical" for `vel_similarity` scoring rather than "silent"; this is the correct, deliberate
  choice per the commit message, not a regression. Residual: PAT-2026-08-23-2 (dead
  `_optimize_patterns`).
- **Dim 9 (loops)**: `tracker/loop_manager.py` unchanged since `d150fe3` (pre-#345, well before
  this report's window) — `loop_start = positions[-2]`/`loop_end = positions[-1] + length`
  (`:39-45`), jump-table keying on `loop_info['end']` (`:93-141`), and the
  `f"loop_{end}_{start}"` tempo-state key format (write `:141`, read `:167`) all verified
  consistent by direct read this session. No change since the prior audit's clean bill on this
  dimension.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-08-23.md
```
