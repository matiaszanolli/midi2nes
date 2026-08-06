# Regression / Test-Hygiene Audit — 2026-08-06

Scope: the test suite itself (`tests/`, 58 `test_*.py` + `conftest.py`, 1166 collected
tests) — coverage gaps, weak assertions, round-trip/e2e gaps, stale tests, determinism,
and fixture hygiene. Per the skill's brief this run re-verifies REG-01 through REG-25
(rather than re-deriving them from scratch) and otherwise looks for regressions
introduced since `AUDIT_REGRESSION_2026-08-05.md`.

CC65 toolchain confirmed present (`ca65`/`ld65` V2.18) for this run, so the CC65-gated
suites were executed for real, not trusted from a skip.

Three fix commits landed on this branch since the 08-05 report, all touching
test-suite-relevant surface:
- `24e51d2` (#348, #355/#394, #366, #367) — root-caused and fixed REG-24 (the slow
  `test_patterns.py` test).
- `90b4582` (#302, #311, #329, #342) — removed dead `CompressionEngine` + its two test
  files, strengthened the round-trip test #311 flagged.
- `20f627e` (#136, #137, #167, #202) — extracted 8 per-channel emitter methods out of
  `export_direct_frames`, plus DPCM pattern-path and TODO fixes, each with new tests.

Full non-slow suite (`-m "not slow"`, excluding the two heaviest CC65 files which were
run separately below): **1141 passed, 1 skipped (legitimate `Windows-only test` platform
gate in `test_nes_project_builder.py:358`), 1 deselected (the `@pytest.mark.slow`-tagged
`test_patterns.py` test) in 130s.** `tests/test_rom_validation_integration.py`: 11/11
passed. `tests/test_e2e_pipeline.py`: 12/12 passed.
`tests/test_ca65_export.py::TestCA65CompilationIntegration`: 9/9 passed.

## Re-verification of prior REG items

All still hold as fixed except where noted:

- **REG-01** (`TestCA65CompilationIntegration`, `tests/test_ca65_export.py`): all 9 tests
  PASS with the toolchain present (verified directly). See **REG-26** below — a new,
  distinct finding about this same class's CC65-gating *style*, not a regression of REG-01
  itself.
- **REG-10/REG-15** (`tests/test_rom_validation_integration.py`): all 11 tests PASS
  unconditionally. No `except → pytest.skip` masking remains.
- **REG-11** (`tests/test_e2e_pipeline.py`): all 12 tests PASS, including
  `test_full_pipeline_arranger_mode` and `test_full_pipeline_no_patterns_direct_export`.
- **REG-02/REG-03** (`verify_ca65_assembly`, `test_audio_fixes.py` unskips): still correct.
- **REG-05/REG-20** (golden-bytes / weak `assertIn`): re-grepped
  `tests/test_ca65_export.py`, `tests/test_exporter_integration.py`,
  `tests/test_famistudio_export.py` — no bare `assertIn("PATTERNS"...)` remains; the two
  historical call sites are commented as deliberately avoiding it.
- **REG-06** (`tests/test_pattern_detector_parallel.py` determinism): tie-break and
  `max_workers=1/2/4` pinning intact.
- **REG-07/REG-08/REG-09** (`test_mappers.py`, `test_track_mapper.py`,
  `test_cc65_wrapper.py`): all present and passing.
- **REG-23** (`test_no_unused_imports.py` red on master): **FIXED** by `5c61c30` (#393,
  landed before this run) — `main.py` now declares an explicit `__all__` covering the
  re-exported `mappers.capacity` names. Verified: `test_no_f401_in_tracked_source` PASSES.
- **REG-24** (`test_base_detector_uniformly_samples_not_head_cuts` ~99s standalone):
  **FIXED** by `24e51d2` (#355/#394) — the test's `PatternDetector` config now matches
  what `main.py` actually passes (`max_pattern_length=12` instead of the class default
  32), and the test is now `@pytest.mark.slow`. Verified: runs in **20.4s** standalone
  (was ~99s), and correctly excluded by `-m "not slow"`.
- **REG-25** (`test_drum_engine.py::test_main_execution_success` reimplements
  `__main__` instead of invoking it): **Existing: #395, still OPEN, not re-fixed.**
  `tests/test_drum_engine.py:544-546` still has the bare `except Exception: pass` around
  hand-simulated logic rather than a real invocation of `drum_engine.py`'s CLI entry
  point. Not re-filed; tracked at #395.
- **#355/REG-22** ("`test_parser_fast.py` + `test_patterns.py` hang"): the root cause
  REG-24 identified is fixed, and #355's own tracking issue notes the same root-cause
  fix. No further action taken here since #355 is a separate open tracking issue and the
  fix commit already references it.
- **#311 (PAT-10)**: **FIXED** by `90b4582` — `test_pattern_positions_format` now
  dereferences every position back into the sequence and asserts it equals the pattern's
  stored events (`tests/test_pattern_integration.py:123-156`), plus a new sibling test
  with a transposed-decoy fixture (`test_pattern_positions_exclude_transposed_decoy`,
  `tests/test_pattern_integration.py:158+`) exercising the bare `PatternDetector` class
  directly.
- **#302 (EXP-09)**: **FIXED** by `90b4582` — dead `CompressionEngine`
  (`exporter/compression.py`) and its two dedicated test files
  (`test_compression.py`, `test_compression_integration.py`) were removed entirely, along
  with the now-empty `BaseExporter` wrapper methods. No dead-code-coverage gap remains
  because there's no dead code left to have coverage of.
- **#231** (repo-root fixture leak in `test_drum_mapping.py`): confirmed still fixed —
  the file now writes to a `tmp` dir with an explicit comment referencing #231.

## New finding

### REG-26: `TestCA65CompilationIntegration` (`tests/test_ca65_export.py`) has no `@pytest.mark.requires_cc65` gate — hard-fails (doesn't skip) when CC65 is absent
- **Severity**: MEDIUM
- **Dimension**: 6 (fixture & isolation hygiene) / 4 (inconsistent with established convention)
- **Location**: `tests/test_ca65_export.py:706-975` (`TestCA65CompilationIntegration`, all
  9 methods); compare `tests/conftest.py:19-43` (`CC65_AVAILABLE` +
  `pytest_runtest_setup`'s real `shutil.which`-based skip for `@pytest.mark.requires_cc65`)
  and its three current users (`tests/test_debug_overlay.py`,
  `tests/test_e2e_pipeline.py`, `tests/test_rom_validation_integration.py`).
- **Status**: NEW
- **Description**: Every other test class in the suite that shells out to real
  `ca65`/`ld65` is gated with `@pytest.mark.requires_cc65`, which `conftest.py`'s
  `pytest_runtest_setup` skips cleanly only when the toolchain is genuinely absent
  (`shutil.which`). `TestCA65CompilationIntegration` — the class REG-01 (#39) originally
  fixed, and the suite's oldest "does the exporter still produce a compilable ROM" gate —
  was never migrated to this convention. Its helper `_compile_and_link` (module-level,
  `tests/test_ca65_export.py:667-703`) wraps the `subprocess.run(['ca65', ...])` /
  `subprocess.run(['ld65', ...])` calls in a bare `try/except Exception as e: return
  False, f"Error during compilation: {str(e)}"`, so a missing binary (`FileNotFoundError`)
  is caught and turned into a normal `(False, ...)` return — which every test then feeds
  into `self.assertTrue(success, f"Compilation failed:\n{output}")`, producing a real,
  loud **test FAILURE** (not a skip) that reads exactly like a genuine ROM-compile
  regression.
- **Evidence**: Directly reproduced by stripping `/usr/bin` (where `ca65`/`ld65` live in
  this environment) from `PATH` and re-running one test:
  ```
  $ env PATH="<PATH without /usr/bin>" python -m pytest \
      tests/test_ca65_export.py::TestCA65CompilationIntegration::test_basic_project_compilation -v
  ...
  AssertionError: False is not true : Compilation failed:
  Error during compilation: [Errno 2] No such file or directory: 'ca65'
  FAILED tests/test_ca65_export.py::TestCA65CompilationIntegration::test_basic_project_compilation
  ```
  Confirmed by `grep -n "requires_cc65" tests/test_ca65_export.py` returning nothing,
  versus the 3 other files that do use the marker.
- **Impact**: This repository has no CI workflow (`find . -path '*/.github/workflows/*'`
  returns nothing) enforcing that CC65 is present wherever the suite runs, and CC65 is an
  external, manually-installed toolchain per `CLAUDE.md`. Any contributor without
  `ca65`/`ld65` on `PATH` who runs `tests/test_ca65_export.py` (the project's own
  documented practice of scoping `pytest` to specific files) sees 9 failures that look
  exactly like a real "ROM stopped compiling" regression, with no indication anywhere in
  the failure text that the actual cause is an absent dev-tool rather than broken
  exporter output. This is the opposite failure shape from REG-10/REG-11 (which *masked*
  real failures as skips) but is still a test-suite-health problem: it risks contributors
  either ignoring this file's output as "probably just my toolchain" (which would also
  hide a real regression the next time one occurs) or wasting time debugging a
  non-existent exporter bug. No production/ROM impact when CC65 is present — verified all
  9 tests pass correctly in that case, consistent with REG-01's original fix still holding.
- **Related**: REG-01/#39 (the original fix to this class); REG-10/REG-11/#128/#129 (the
  precedent this class should follow); `tests/conftest.py:19-43` (the shared
  `CC65_AVAILABLE` gate to reuse).
- **Suggested Fix**: Add `@pytest.mark.requires_cc65` to `TestCA65CompilationIntegration`
  (class-level, matching `TestPipelineFailureRecovery` in
  `tests/test_rom_validation_integration.py`'s pattern), so the class skips cleanly via
  the shared `conftest.py` gate when the toolchain is genuinely absent instead of failing.
  Optionally also narrow `_compile_and_link`'s `except Exception` to something that still
  surfaces a truly unexpected error distinctly from "tool not found," but the marker alone
  closes the reported gap.

## Coverage spot-checks (targeted, this run)

Full-suite `--cov=.` timed out twice in this environment even after excluding the two
heaviest CC65 files (matches the REG-22/REG-24 history of this suite being slow to run
end-to-end with coverage instrumentation); targeted `--cov` runs on the modules touched by
this branch's three fix commits confirm no regression from the `exporter_ca65.py`
extract-method refactor or the arranger/DPCM changes:

| Module | Coverage (this run) | Test module(s) |
|---|---|---|
| `exporter/exporter_ca65.py` | **97%** (601 stmts, 16 missed) | `test_ca65_export.py`, `test_exporter_integration.py` |
| `arranger/voice_allocator.py` | 98% | `test_voice_allocator.py`, `test_arranger*.py` |
| `arranger/gm_instruments.py` | 98% | same |
| `arranger/pipeline_integration.py` | 91% | same |
| `arranger/role_analyzer.py` | 81% | `test_role_analyzer.py`, `test_arranger*.py` |
| `dpcm_sampler/dpcm_sample_manager.py` | 98% | `test_dpcm_sample_manager.py` |
| `dpcm_sampler/enhanced_drum_mapper.py` | 83% | `test_enhanced_drum_mapper.py` (residual gap is mostly `DrumMapperConfig.to_file`/`from_file` JSON serialization, covered separately by `test_drum_mapper_config.py`, not included in this narrower run) |
| `dpcm_sampler/drum_engine.py` | 80% (missing 180-190) | `test_drum_engine.py` — the missing lines are the `__main__` block REG-25/#395 already tracks |

`exporter_ca65.py`'s 97% (up from being embedded, untestable, in a 750-line method before
the refactor) directly confirms the commit's own claim that the 8 extracted emitter
methods unlocked real per-method unit coverage rather than just moving code around
untested.

No subsystem in `.claude/commands/_audit-common.md`'s layout is without a test module.

## Prioritized backlog

1. **REG-26** — add `@pytest.mark.requires_cc65` to `TestCA65CompilationIntegration`.
   One-line class decorator; removes a standing false-failure trap for anyone without
   CC65 installed.
2. **#395 (REG-25)** — still open, low urgency (non-pipeline debug script): rewrite
   `test_main_execution_success`/`test_main_execution_insufficient_args` to actually
   invoke `drum_engine.py`'s `__main__` block via `runpy.run_path` or a subprocess, per
   the existing suggested fix.
3. No other action items — the suite is green, REG-23/REG-24 landed cleanly, and the
   three most recent fix commits all shipped with targeted, assertion-strong tests
   (verified by direct coverage measurement on the touched modules).

## Summary

1 new finding this run (REG-26, MEDIUM). All prior REG-01–REG-25 items re-verified:
REG-23 and REG-24 confirmed newly fixed since the 08-05 report; REG-25 confirmed still
open at #395 (not re-filed); all others hold with no regressions. Full non-slow suite
green (1141 passed / 1 legitimate skip / 1 correctly-deselected slow test), plus 11/11 and
12/12 on the two CC65-gated integration files and 9/9 on the newly-flagged
`TestCA65CompilationIntegration`.
