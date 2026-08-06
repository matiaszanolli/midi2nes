# Regression / Test-Hygiene Audit — 2026-08-05

Scope: the test suite itself (`tests/`, 62 files, 1120 collected tests) — coverage gaps,
weak assertions, round-trip/e2e gaps, stale tests, determinism, and fixture hygiene. Per
the skill's brief, this run re-verifies REG-01 through REG-11 (and the later REG-15/REG-20/
REG-22 items referenced from prior reports) rather than re-deriving them from scratch, and
otherwise looks for newly-introduced regressions since `AUDIT_REGRESSION_2026-07-19.md`.

CC65 toolchain confirmed present (`ca65`/`ld65` V2.18) for this run, so the CC65-gated
suites were executed for real rather than trusted from a skip.

## Re-verification of prior REG items

All still hold as fixed — no regressions found:

- **REG-01** (`TestCA65CompilationIntegration`, `tests/test_ca65_export.py`): all 9 tests
  PASS (not skipped) with the toolchain present.
- **REG-10/REG-15** (`tests/test_rom_validation_integration.py`): all 11 tests PASS
  unconditionally, including the negative-path compile-failure tests
  (`test_compilation_with_invalid_assembly`, `test_compilation_failure_without_rom_output`).
  No `except → pytest.skip` masking remains in this file.
- **REG-11** (`tests/test_e2e_pipeline.py`): all 12 tests PASS, including
  `test_full_pipeline_arranger_mode` and `test_full_pipeline_no_patterns_direct_export`
  through a real `ca65`/`ld65` compile.
- **REG-02/REG-03** (`verify_ca65_assembly`, `test_audio_fixes.py` unskips): still correct;
  the macro-bytecode/pattern-compressed/direct-frame branches in
  `tests/test_midi_parser_integration.py:41-73` still match current exporter output.
- **REG-05/REG-20** (golden-bytes / weak `assertIn`): re-grepped
  `tests/test_ca65_export.py`, `tests/test_exporter_integration.py`,
  `tests/test_famistudio_export.py`, `tests/test_nsf_export.py` — no bare
  `assertIn("PATTERNS"...)` or similar section-only checks remain; the two call sites that
  used to have this are now commented as deliberately avoiding it (#339/REG-20).
- **REG-06** (`tests/test_pattern_detector_parallel.py` determinism): the `(start, length)`
  tie-break and `max_workers=1/2/4` pinning are intact; coverage on
  `tracker/pattern_detector_parallel.py` measured this run at **80%** (in line with the
  78% baseline — no regression).
- **REG-07/REG-08/REG-09** (`test_mappers.py`, `test_track_mapper.py`,
  `test_cc65_wrapper.py`): all present and passing; `mappers/base.py` at 76%,
  `mappers/factory.py` at 77% this run (residual gap is still the documented
  abstract-method stubs/capacity edge cases, not a blank spot).
- Recent fixes since the last regression audit (`#365`, `#364`, `#361`–`#363`, `#359`,
  `#360`) each shipped with dedicated tests in the same commit
  (`tests/test_pattern_exact_gate.py`, `tests/test_audio_fixes.py` updates,
  `tests/test_mapper_capacity_fixes.py`, `tests/test_arranger_audit_fixes.py`) — no gap
  there.

## Coverage map (this run)

Full-suite `--cov=.` term-missing report, split across two invocations to work around the
REG-22 hang (see REG-23 below) and combined with `coverage combine`:

| Subsystem | Test module(s) | Coverage |
|---|---|---|
| `tracker/pattern_detector.py` | `test_patterns.py`, `test_pattern_exact_gate.py`, `test_pattern_integration.py` | 89% |
| `tracker/pattern_detector_parallel.py` | `test_pattern_detector_parallel.py` | 80% |
| `tracker/parser_fast.py` | `test_parser_fast.py` | 78% |
| `tracker/parser.py` (test-only, no pipeline path) | `test_midi_parser_integration.py` | 72% |
| `tracker/track_mapper.py` | `test_track_mapper.py` | 91% |
| `tracker/tempo_map.py` | `test_tempo_map.py` | 95% |
| `tracker/loop_manager.py` | `test_loop_manager.py`, `test_enhanced_loop_patterns.py` | 91% |
| `mappers/base.py` | `test_mappers.py` | 76% |
| `mappers/factory.py` | `test_mappers.py` | 77% |
| `mappers/mmc1.py` / `mmc3.py` / `nrom.py` | `test_mappers.py` | 94% / 95% / 100% |
| `mappers/capacity.py` | `test_mapper_capacity_fixes.py` | 88% |
| `nes/emulator_core.py` | `test_frame_validation.py`, `test_envelope_integration.py`, others | 97% |
| `nes/envelope_processor.py` | `test_envelope.py`, `test_arranger_audit_fixes.py` | 99% |
| `nes/pitch_table.py` | `test_pitch_tables.py`, `test_pitch_table_integration.py` | 98% |
| `nes/project_builder.py` | `test_nes_project_builder.py` | 97% |
| `nes/song_bank.py` | `test_song_bank.py` | 93% |
| `nes/debug_overlay.py` | `test_debug_overlay.py` | 79% |
| `exporter/exporter_nsf.py` | `test_nsf_export.py`, `test_nsf_integration.py` | 100% |
| `main.py` | `test_main.py`, `test_main_pipeline.py`, `test_e2e_pipeline.py` | 93% |
| `utils/profiling.py` | `test_profiling.py` | 90% |
| `validate_rom.py` | `test_validate_rom_script.py` | 90% |

No subsystem in `docs/.claude/commands/_audit-common.md`'s layout is without a test
module. The two dead-code call sites flagged by prior audits
(`exporter/compression.py`'s `CompressionEngine`, `dpcm_sampler/drum_engine.py`'s
`DrumPatternAnalyzer` — #302, #368) are exercised only by tests, not production code; their
tests are effectively testing dead code, not a coverage gap in the live pipeline.

## Findings

### REG-23: `test_no_unused_imports.py::test_no_f401_in_tracked_source` is currently FAILING on master
- **Severity**: MEDIUM
- **Dimension**: 4 (stale/wrong-target) — the *test* is correct and doing its job; the
  source it gates has drifted and nobody has fixed it since.
- **Location**: `main.py:148-152`; gate at `tests/test_no_unused_imports.py:27-41`
- **Status**: NEW
- **Description**: `tests/test_no_unused_imports.py::TestNoUnusedImports::test_no_f401_in_tracked_source`
  fails on current master (verified directly, not from a stale report):
  ```
  main.py:148:1: 'mappers.capacity.estimate_segment_sizes' imported but unused
  ```
  This gate was added by #264 specifically to keep unused imports from re-accumulating
  after a one-time sweep. Commit `36348ce` (#361-#363, 2026-07-19 — the same sprint the
  gate itself postdates) added a deliberate backward-compat re-export block at
  `main.py:143-152`:
  ```python
  # ... Re-exported here so existing `from main import estimate_segment_sizes` /
  # `check_mapper_capacity` imports keep resolving.
  from mappers.capacity import (  # noqa: E402
      estimate_segment_sizes,
      estimate_music_data_size,
      check_mapper_capacity,
  )
  ```
  `check_mapper_capacity` and `estimate_music_data_size` are also called from within
  `main.py` itself (lines 272, 491, 1070), so pyflakes doesn't flag them. `estimate_segment_sizes`
  is referenced only externally, via `from main import estimate_segment_sizes` in
  `tests/test_main_pipeline.py:977/995/1018` — never inside `main.py`'s own body — so
  pyflakes correctly reports it unused *within this module*, even though it is a
  deliberate public re-export.
- **Evidence**: Confirmed by running `python -m pytest tests/test_no_unused_imports.py -v`
  directly: 1 failed. Also confirmed the existing `# noqa: E402` comment on the same
  import statement is inert against this gate — plain `pyflakes` (unlike `flake8`) does
  **not** honor `# noqa` comments at all (verified: `python -m pyflakes` still flags a
  `# noqa: F401`-annotated unused import). So the obvious "add `# noqa: F401` next to the
  existing `# noqa: E402`" fix would silently not work.
- **Impact**: The test suite is currently red on master for anyone who runs
  `tests/test_no_unused_imports.py` (scoped, per project convention) or a pyflakes-enabled
  full run. No runtime/ROM impact — this is a lint-level gate — but a broken guard rail
  invites either being ignored (defeating its purpose) or masking the next genuine
  unused-import accumulation.
- **Related**: #264/#227/#228 (added the gate), #361-#363 (introduced the regression).
- **Suggested Fix**: Add `estimate_segment_sizes` (and, for consistency/documentation, the
  other two re-exported names) to an explicit `__all__` in `main.py`. Confirmed by direct
  experiment that `__all__` membership suppresses pyflakes' F401 report even without any
  in-module reference — `# noqa` does not.

### REG-24: `test_base_detector_uniformly_samples_not_head_cuts` takes ~99s standalone — likely the real driver behind REG-22's "hang"
- **Severity**: MEDIUM
- **Dimension**: 5 (determinism/flakiness)
- **Location**: `tests/test_patterns.py:769-787` (`TestLargeFilePolicy::test_base_detector_uniformly_samples_not_head_cuts`); underlying cost in `tracker/pattern_detector.py:244-277` (`PatternDetector.detect_patterns`'s candidate-generation loop, self-documented "O(n^2)-ish" at line 215)
- **Status**: NEW (related to existing #355/REG-22, still open)
- **Description**: This test constructs `DETECTOR_MAX_EVENTS * 3` = 3000 events split into
  two maximally-repeating motifs (notes cycling with period 3), which `PatternDetector`
  uniformly downsamples to `DETECTOR_MAX_EVENTS` = 1000 before running its candidate-window
  scan. Because both halves are maximally repetitive, the scan's `_find_pattern_matches`/
  `_detect_pattern_variations` calls (each effectively O(n) per candidate position) never
  get the early-exit benefit typical music gives them, and the whole
  length × start-position double loop (self-documented as "O(n^2)-ish" at
  `tracker/pattern_detector.py:215`) hits close to its worst case. Directly instrumented
  (isolated from pytest/coverage overhead): `PatternDetector().detect_patterns()` on this
  exact input took **99.14 seconds** wall-clock in this environment. Running just this one
  test file with a 45-120s timeout — the range used by #355/REG-22's own repro commands —
  reproducibly looks like a hang for exactly this reason, and #355's report itself records
  "`test_patterns.py`: 77 passed in ~24.10s" alone, which does not match this run's
  measurement; either the input/environment characteristics changed since REG-22 was filed
  or the alone-timing in that report undercounted this one test. This test is not marked
  `@pytest.mark.slow`, unlike the ROM-compile tests in `test_rom_validation_integration.py`
  and `test_e2e_pipeline.py` that are ~10-20x faster and do carry the marker.
- **Evidence**:
  ```
  $ timeout 45 python -m pytest -v tests/test_patterns.py
  ...
  tests/test_patterns.py::TestLargeFilePolicy::test_base_detector_uniformly_samples_not_head_cuts
  # (times out mid-test; no PASSED line)

  $ python -c "... PatternDetector().detect_patterns(head+tail) ..."
  took 99.14071798324585 seconds, 1 patterns
  ```
- **Impact**: Any scoped run of `tests/test_patterns.py` (the project's own recommended
  practice per `MEMORY.md`/this repo's testing convention) now takes 100+ extra seconds for
  this one test. Combined with other files it very plausibly *is* (or significantly
  compounds) the hang #355/REG-22 describes — that report's own repro commands used 30-40s
  timeouts, well under this test's now-measured runtime. No production/ROM impact: this is
  purely a test-suite health and CI-budget issue, and the property under test (#100,
  uniform sampling not head-cutting) is legitimate and worth keeping.
- **Related**: #355 (REG-22) — recommend re-investigating REG-22 with this timing data;
  it may fully explain, or substantially compound, that report.
- **Suggested Fix**: Either shrink the test's input to the minimum needed to prove the
  uniform-sampling property (e.g. a few hundred events instead of `DETECTOR_MAX_EVENTS * 3`
  with a non-adversarial motif), or mark it `@pytest.mark.slow` for consistency with the
  other genuinely-slow tests in this suite so scoped fast runs (`-m "not slow"`) skip it.

### REG-25: `test_drum_engine.py::test_main_execution_success` never executes `drum_engine.py`'s actual `__main__` block
- **Severity**: LOW
- **Dimension**: 2 (weak assertions) / 4 (wrong-target)
- **Location**: `tests/test_drum_engine.py:497-546` (`TestDrumEngineMainExecution::test_main_execution_success`); target is `dpcm_sampler/drum_engine.py:168-179` (`if __name__ == "__main__":` block)
- **Status**: NEW
- **Description**: `drum_engine.py`'s CLI entry point (`if __name__ == "__main__":`, only
  reachable via `python -m dpcm_sampler.drum_engine` or direct script execution — never on
  import) is not exercised at all. `test_main_execution_success` mocks `builtins.open`,
  `json.load`, and `json.dumps`, then **reimplements the `__main__` block's logic inline**
  in the test body (`with open('test_midi.json', 'r') as f: ...`) rather than invoking the
  module, and wraps the whole thing in a blanket `try: ... except Exception: pass`. Because
  `builtins.open` is mocked, the literal `'test_midi.json'` path is never touched, and the
  bare `except Exception: pass` means the test passes even if every assertion inside it
  were wrong or the reimplemented logic diverged from the real `__main__` block. A
  companion test, `test_main_execution_insufficient_args`, has the same shape: it
  hand-simulates the argument-count check (`if len(['drum_engine.py']) < 3: ...`) rather
  than calling the module.
- **Evidence**: `tests/test_drum_engine.py:544-546`:
  ```python
          except Exception:
              # Main execution might not be directly testable
              pass
  ```
- **Impact**: Zero regression protection on `drum_engine.py`'s actual CLI entry point — a
  broken `sys.argv` handling, a wrong `map_drums_to_dpcm` call signature, or a crash on
  real file I/O there would not be caught by either test. Low impact in practice since this
  entry point is a standalone debug script, not on the `main.py` pipeline path.
- **Related**: none (distinct from #368's dead-code framing of the *class* methods in the
  same file — this finding is about the untested `__main__` block, not `DrumPatternAnalyzer`).
- **Suggested Fix**: Use `runpy.run_path(..., run_name="__main__")` or
  `subprocess.run([sys.executable, "-m", "dpcm_sampler.drum_engine", ...])` against a real
  temp-dir JSON fixture (per `tests/conftest.py`'s `temp_dir` pattern) so the test exercises
  the actual code path, and narrow the `except` (or remove it) so a real failure surfaces
  as a test failure instead of a silent pass.

### Existing / re-confirmed, not re-reported as new
- **#355 (REG-22)** — "`test_parser_fast.py` + `test_patterns.py` together hang" — still
  reproduces on current master (`timeout 45 pytest -q tests/test_parser_fast.py
  tests/test_patterns.py` → exit 124). See REG-24 above for new timing data relevant to
  investigating it further.
- **#368 (DP-DPCM-06)** — `drum_engine.py`'s `DrumPatternAnalyzer`/`optimize_dpcm_samples`
  dead-code framing; still open, not re-filed. REG-25 above is a distinct, test-focused
  angle on the same file (the `__main__` block, not the analyzer class).
- **#311 (PAT-10)** — "No test pins the exact-only round-trip invariant" — still open,
  still an accurate Dimension-3 gap.
- **#302 (EXP-09)** — `exporter/compression.py` dead code, tested but not wired into the
  pipeline; `tests/test_compression.py`/`test_compression_integration.py` coverage is
  real but of dead code, consistent with the existing issue.

## Prioritized backlog

1. **REG-23** — one-line `__all__` fix in `main.py`; restores a currently-red gate. Trivial, do first.
2. **REG-24** — shrink or `@pytest.mark.slow`-tag the offending test; directly unblocks
   fast scoped test runs and may resolve/inform #355.
3. **REG-25** — rewrite `test_main_execution_success`/`test_main_execution_insufficient_args`
   to actually invoke `drum_engine.py`'s `__main__` block. Low urgency (non-pipeline code).
4. Re-investigate **#355/REG-22** with REG-24's timing data now in hand.

## Summary

4 items total this run: 3 new findings (REG-23 MEDIUM, REG-24 MEDIUM, REG-25 LOW) plus
re-confirmation that #355/REG-22 is still open and now has a concrete lead. All 11 prior
REG-01–REG-11 items (and REG-15/REG-20) remain fixed — no regressions among them.
