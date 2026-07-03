# Pattern Detection & Compression Audit — 2026-07-03

Audit of the pattern-detection and compression subsystem per
`.claude/commands/audit-patterns/SKILL.md`, at HEAD `9cfa0e2` ("Refactor audit
documentation for tech debt, tempo handling, and issue fixing"). Severity floors from
`.claude/commands/_audit-severity.md`. Dedup against `/tmp/audit/issues.json` (47
issues, open+closed) and all prior reports in `docs/audits/`, in particular
`docs/audits/AUDIT_PATTERNS_2026-07-01.md` (two days prior).

**Key fact established first**: `git log --since="2026-07-01" -- tracker/pattern_detector.py
tracker/pattern_detector_parallel.py exporter/compression.py tracker/loop_manager.py
main.py exporter/exporter_ca65.py` returns **no commits**. Every commit since the
2026-07-01 audit (`e62abe8` through `9cfa0e2`) touches other subsystems (APU pulse/noise,
song-bank parsing, DPCM sample IDs, emulator core dedup, drum mapping, cc65 wrapper
tests, dead-script removal). The pattern-detection/compression code this audit covers is
**byte-for-byte unchanged** since the last audit ran.

Given that, this audit's job was to independently re-verify — not re-derive — the prior
findings, and to look for anything the prior pass missed. I re-ran real round-trip checks
(not docstring reading) rather than trusting the previous report at face value:

- **`EnhancedPatternDetector` round-trip** (motif × 2 exact + 1 transposed copy, plus a
  self-similar filler run): reproduced the exact same defect shape as PAT-01 — pattern_1
  positions `[0, 7, 14]` for events `(40,20),(60,100)`; position 14 actually contains
  `(41,21),(60,100)`, an exact content mismatch. Also incidentally reproduced PAT-04 in
  the same run: pattern_0 (a length-4 filler window) got positions `[2, 3, 9, 10]` —
  positions 2 and 3 overlap the same 4-length window, the exact self-overlap PAT-04
  describes.
- **`CompressionEngine.compress_pattern` / `decompress_pattern` round-trip**: ran the
  absent-key delta case, a 200-event random fuzz (seeded), and a 10-event RLE run — all
  three reproduced frame-by-frame `==` (lossless), matching the 2026-07-01 result.
- **Dead-code / multiprocessing spot checks**: `grep -rn ThreadedPatternDetector` still
  matches only the doc comment (`pattern_detector.py:12`) and the regression test
  (`tests/test_patterns.py:930-936`) — confirmed still gone. `_WORKER_SEQUENCE`/
  `_WORKER_EVENTS` module globals and `_init_pattern_worker`/`_detect_patterns_worker`
  are still module-level in `pattern_detector_parallel.py:226-235,300-308` (picklable,
  no shared mutable state).
- **Test suite**: all 87 pattern-related tests pass
  (`test_patterns.py`, `test_compression.py`, `test_compression_integration.py`,
  `test_pattern_integration.py`, `test_enhanced_loop_patterns.py`,
  `test_pattern_detector_parallel.py`, `test_loop_manager.py` — 213.64s, 0 failures).
- **Issue tracker cross-check**: PAT-01 through PAT-07 (#168–#173, PAT-02 folded into
  PL-03/#176) are all still **OPEN** in `gh issue list`. None have been closed or
  regressed since filing.

## Summary

**Round-trip result: unchanged from 2026-07-01 — MOSTLY LOSSLESS.** The default pipeline
path (`ParallelPatternDetector` + `CompressionEngine`) remains exact/lossless. The
sequential fallback / `detect-patterns` subcommand path (`EnhancedPatternDetector`)
still mixes non-exact variation positions into `positions`/`references` (PAT-01,
still analysis-only per #4, still not CRITICAL). No new round-trip defect was found.

### Finding counts
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0 new (2 existing: PAT-01 #168, PAT-03 #169)
- LOW: 0 new (4 existing: PAT-04 #170, PAT-05 #171, PAT-06 #172, PAT-07 #173)
- **NEW findings this cycle: 0**

All findings from `AUDIT_PATTERNS_2026-07-01.md` remain accurate and unresolved. This
audit did not surface any additional defect beyond what is already filed. No report
content is duplicated below beyond what's needed to record the re-verification; see the
2026-07-01 report for full per-finding detail (Evidence/Impact/Suggested Fix), which
still applies verbatim since the code has not moved.

### 3 highest-leverage fixes (unchanged from 2026-07-01, still the priority order)
1. **PAT-01 (#168)** — Separate exact matches from variations in
   `positions`/`references` (or tag variation refs with their transform) so the
   sequential detector's reference table stops asserting non-repeats as repeats.
2. **PAT-04 (#170)** — Fix `_find_pattern_matches`'s off-by-anchor scan
   (`start_pos + 1` → `start_pos + pattern_len`) to stop self-overlapping matches and
   the resulting stat inflation / divergence from the parallel matcher.
3. **PAT-03 (#169)** — Stop printing the detector's `compression_ratio` in the ROM
   success banner as if it described the ROM; it measures only the patterned subset of
   a metrics-only analysis with no relationship to emitted bytes.

---

## Findings

### PAT-01-recheck: Sequential detector's `positions`/`references` still include non-exact variation positions
- **Severity**: MEDIUM (escalates to CRITICAL if `references` ever drive output bytes)
- **Dimension**: 1 (Round-Trip Integrity) / 3 (Reference Offsets)
- **Location**: `tracker/pattern_detector.py:227` and `:253` (unchanged line numbers),
  stored `:279-286`
- **Status**: Existing: #168 (OPEN, unregressed — code identical to 2026-07-01)
- **Description**: Unchanged from the 2026-07-01 report. Independently re-reproduced
  in this audit (see Summary) with a fresh synthetic input rather than re-using the
  prior audit's numbers.
- **Evidence**: New repro run: `pattern_1` positions `[0, 7, 14]`, stored events
  `(40,20),(60,100)`; window at position 14 is `(41,21),(60,100)` — content mismatch
  confirmed independently.
- **Impact**: Same as #168 — no ROM byte today (`references` analysis-only, #4
  closed), but inflates `compression_ratio` and is a latent CRITICAL the moment any
  consumer reconstructs from `references`.
- **Related**: #168, #4 (closed), #101 (closed), PAT-03/#169, PAT-04/#170.
- **Suggested Fix**: See #168 — unchanged.

---

### PAT-04-recheck: `_find_pattern_matches` self-overlap still present
- **Severity**: MEDIUM
- **Dimension**: 8 (Match Semantics) / 5 (Parallel vs Sequential Equivalence)
- **Location**: `tracker/pattern_detector.py:291-306`, `pos = start_pos + 1` at `:297`
  (unchanged)
- **Status**: Existing: #170 (OPEN, unregressed)
- **Description**: Unchanged. Independently reproduced in this audit's own repro run
  (see Summary): `pattern_0` (a length-4 self-similar filler window) got positions
  `[2, 3, 9, 10]` — positions 2 and 3 describe overlapping occurrences of the same
  4-length window, exactly the self-overlap the SKILL and #170 describe.
- **Evidence**: See above; independent of the 2026-07-01 audit's own repro (12
  identical notes → `[0, 1, 5]`).
- **Impact**: Same as #170 — inflates `exact_matches`/scores/stats on the sequential
  path; no round-trip corruption (overlapping windows of identical content stay
  value-consistent).
- **Related**: #170, #103 (closed), PAT-01/#168, PAT-03/#169.
- **Suggested Fix**: See #170 — unchanged (`start_pos + pattern_len`).

---

### Dimensions re-checked with no change from 2026-07-01

All other dimensions (2 schema, 3 reference/length correctness beyond the repro above,
4 stats accuracy, 5 parallel/sequential equivalence, 6 multiprocessing safety, 7
large-file sampling, 9 loop detection) were spot-checked against the specific line
numbers and mechanisms cited in the 2026-07-01 report and found unchanged:

- **Dim 1 (`CompressionEngine`)**: re-ran round-trip on absent-key delta, 200-event
  fuzz, and RLE-run cases — all lossless, matching prior result.
- **Dim 2/6 (schema, dead code)**: `ThreadedPatternDetector` still fully absent except
  in the doc comment and the regression test guarding its absence (#105 remains OPEN
  on GitHub despite being fixed-by-code since `2bcb780` — still a housekeeping item,
  not re-filed).
- **Dim 6 (multiprocessing)**: `_WORKER_SEQUENCE`/`_WORKER_EVENTS` globals and
  `_init_pattern_worker`/`_detect_patterns_worker` module-level and picklable, no
  shared mutable state — unchanged from 2026-07-01's verification.
- **Dim 3 (exporter consumption of `references`)**: `exporter/exporter_ca65.py:866-875`
  still documents and structurally enforces that `references` is never read — confirmed
  by grep, unchanged.
- **Test suite**: 87/87 pattern-related tests pass, same set as 2026-07-01.

No new findings were identified in these dimensions; re-stating the prior report's
per-dimension detail here would duplicate `AUDIT_PATTERNS_2026-07-01.md` without adding
information, so it is not repeated verbatim (see that report for full text).

---

## Conclusion

Because zero commits touched the pattern-detection/compression code paths between the
2026-07-01 audit and this one, this audit's function was verification, not discovery.
All six previously-filed issues (PAT-01/#168, PAT-03/#169, PAT-04/#170, PAT-05/#171,
PAT-06/#172, PAT-07/#173) remain open, accurate, and unregressed, confirmed via fresh
independent round-trip reproductions rather than re-trusting the prior write-up. No new
CRITICAL/HIGH/MEDIUM/LOW findings were identified. Recommended next action is the same
as 2026-07-01: land the PAT-01/PAT-04/PAT-03 fixes (all still open, low-risk,
self-contained) rather than re-auditing this subsystem again until it changes.

Suggested next step:
```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-07-03.md
```
(Note: since all findings are "Existing" with no new issues to file, `/audit-publish`
should find nothing new to create — this report exists as a dated verification record.)
