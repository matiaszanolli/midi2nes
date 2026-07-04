# #179 — PL-06: `--version` combined with other arguments is swallowed and a full build runs instead

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
`python main.py --version` alone prints the version (special-cased at argv length 2). But
`python main.py --version song.mid` takes the manual default-path loop, which files
`--version` into `global_args` where nothing consumes it — the full pipeline runs (parse ->
… -> compile), overwriting/creating `song.nes`, and the version is never printed. An
argparse-handled flag would have printed-and-exited regardless of other args.

## Location
`main.py:828-830` (bare `--version` special case), `main.py:864-866` (manual loop collects
`--version` into `global_args`), `main.py:896-905` (`SimpleArgs` never reads it).

## Evidence
Live at HEAD: `python main.py --version missing.mid` prints `[ERROR] Input MIDI file not
found` — the pipeline path was reached; no version output.

## Impact
Surprising side effect (an unrequested build, possibly minutes of CC65 work and an
output-file overwrite — mitigated by the backup contract) for a query-only flag. Low
realism, no data corruption.

## Related
PL-01/PL-02 (manual-dispatch flag handling).

## Suggested Fix
In the manual loop, treat `--version` like argparse does: print `MIDI2NES {__version__}` and `sys.exit(0)` immediately.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix

---

# #170 — PAT-04: `_find_pattern_matches` lets the first match overlap the anchor

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-01.md

## Description
The scan for further occurrences starts at `start_pos + 1` instead of
`start_pos + pattern_len`, so in self-similar runs (period < pattern length) the first
"match" overlaps the anchor window. Only after a match does the code skip `pattern_len`.
The parallel `_collect_length_candidates` uses a correct `next_free` greedy, so the two
detectors return different `exact_matches` for identical input.

## Location
`tracker/pattern_detector.py:291-306` — `pos = start_pos + 1` (`:297`) contradicts the
"Skip the length of the pattern to avoid overlaps" intent (`:302`); correct greedy for
comparison: `tracker/pattern_detector_parallel.py:266-274`.

## Evidence
Reproduced. 12 identical notes, pattern length 4: sequential
`exact_matches = [0, 1, 5]` (positions 0 and 1 overlap); parallel returns `[0, 4, 8]`.
Because overlapping windows in a self-similar run have identical content, reconstruction
would still be value-consistent (no double-write corruption is possible from this alone) —
the damage is inflated occurrence counts -> inflated `score_pattern` totals and
`original_size`/`compression_ratio`, plus fallback-vs-default result divergence beyond the
documented variations difference (#103).

## Impact
Sequential path (fallback + `detect-patterns` subcommand) overstates repetition on
drones/ostinati and selects differently from the default path; stats inflate (feeds
PAT-03). No byte-level effect (#4).

## Related
#131 (open, duplication aspect), #103 (closed), PAT-01, PAT-03.

## Suggested Fix
Initialize the scan at `start_pos + pattern_len` (matching the stated intent and the
parallel greedy), and add a shared-behavior test comparing both detectors' `exact_matches`
on a constant run.

## Completeness Checks
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix

---

# #171 — PAT-05: `_collect_length_candidates` docstring overclaims equivalence with the per-start scan

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-01.md

## Description
The parallel path emits exactly one candidate per distinct window, anchored at its first
occurrence, and `_select_best_patterns` rejects a candidate wholesale if any of its
positions overlaps an already-selected pattern. The sequential path still emits per-start
candidates, so when a higher-scoring pattern overlaps only the window's first occurrence,
the sequential detector recovers the later occurrences via a later-anchored candidate while
the parallel detector loses them all. The docstring's "collapsed onto that first occurrence
anyway" equivalence claim is therefore wrong in the general case.

## Location
`tracker/pattern_detector_parallel.py:238-249` (equivalence claim: "matches the old
per-start output because duplicate starts of the same window collapsed onto that first
occurrence in `_select_best_patterns` anyway"); whole-candidate rejection at `:179-199`.

## Evidence
Reproduced. Winner pattern P (4 occurrences) overlapping only W's first occurrence:
sequential covers W's later occurrences at 18 and 30 (`covered = [True, True, False]`),
parallel covers none (`[False, False, False]`); the two detectors also select structurally
different sets on the same input (length-12 × 3 positions vs length-6 × 4).

## Impact
Metrics-only today (compression quality/stats differ between default and fallback paths);
becomes user-audible pattern-selection divergence if references ever drive bytes. Also
doc-accuracy: the docstring asserts an equivalence the code does not have.

## Related
#103 (closed), #114 (closed), #46 (closed — determinism verified intact), PAT-04.

## Suggested Fix
Correct the docstring (claim "equivalent modulo anchor-blocking") or emit
per-occurrence-suffix candidates for windows whose anchor region is contested;
alternatively make selection reject per-position rather than per-candidate in both
detectors.

## Completeness Checks
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
- [ ] **TESTS**: A regression test pins this specific fix
