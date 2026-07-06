# Regression / Test-Hygiene Audit — MIDI2NES

- **Date**: 2026-07-06
- **Scope**: The test suite itself (`tests/`) — coverage gaps, weak assertions, round-trip/e2e gaps,
  stale/wrong-target tests, determinism/flakiness, fixture hygiene. Delta audit over
  `AUDIT_REGRESSION_2026-07-05.md` (and the `-07-03` / `-06-29` / `-06-28` baselines).
- **Skill**: `/audit-regression`
- **Suite state at audit time**: **985 passed, 1 skipped** (`python -m pytest -q`, 230s). `ca65`/`ld65`
  both present at `/usr/bin`. Collected count grew from 900 → **986** since 07-05. The single remaining skip
  is the legitimate platform gate `test_nes_project_builder.py:358` (`Windows-only test`, skipped on Linux).
  **The 5 REG-10 ROM-compile skips seen at 07-05 are gone** — those tests now compile real ROMs and assert
  unconditionally. Suite is green and materially healthier than the last run.
- **Dedup basis**: pre-fetched `/tmp/audit/issues.json` (29 **OPEN** issues; verified MIDI2NES — carries the
  `REG-`/`PAT-`/`NH-`/`TD-`/`SAFE-`/`ARR-`/`D-`/`TEMPO-`/`PERF-`/`PL-` prefixes matching this repo's audit
  scheme). Prior reports scanned: `AUDIT_REGRESSION_2026-07-05.md`, `-07-03.md`, `-06-29.md`, `-06-28.md`.

> **Headline**: **One NEW finding (MEDIUM).** All five previously-open regression findings (REG-10…REG-14 /
> #128, #129, #230, #231, #232) were **closed and verified fixed** this sprint. The one new finding is a
> residual of the same `except → pytest.skip("CC65 not installed")` masking shape REG-10/REG-11 removed —
> left behind on two *error-handling* (negative-path) tests in the very same file, where it is compounded by
> toothless assertions that pass for any `compile_rom` return value.

## Status of prior regression findings (all now CLOSED — re-verified in code)

The prefetched OPEN-issue list no longer contains #128/#129/#230/#231/#232, so each was closed since 07-05.
Per the dedup protocol (CLOSED → verify the fix is in place), each was re-verified against live code:

| Prior | Issue | Verdict now (2026-07-06) |
|-------|-------|--------------------------|
| **REG-10** (5 ROM-compile tests silently SKIP; stale `music.asm` fixture) | #128 | **FIXED, verified.** `tests/test_rom_validation_integration.py` now uses `@pytest.mark.requires_cc65` (real `shutil.which` gate in `conftest.py:pytest_runtest_setup`) and asserts `compile_rom(...)` unconditionally at `:78, :116, :150, :188, :255`. The shared `minimal_music_asm` fixture is used; suite run shows **0 skips** in this file with cc65 present (was 5). |
| **REG-11** (e2e anchor masks failures; no arranger/no-patterns real compile) | #129 | **FIXED, verified.** `tests/test_e2e_pipeline.py` `_run_pipeline` sets `skip_validation=False` (`:167`), `_assert_valid_rom` asserts unconditionally, all under `@pytest.mark.requires_cc65`. New `test_full_pipeline_arranger_mode` (`:196`) and `test_full_pipeline_no_patterns_direct_export` (`:204`) each drive a real `ca65`/`ld65` compile. No `try/except → skip` / `if rom_path.exists()` guards remain on the anchor. |
| **REG-12** (`RoleAnalyzer._assign_channels` contention/drop untested) | #230 | **FIXED, verified.** New `tests/test_role_analyzer.py` drives `_assign_channels` directly across the contention branches (`role_analyzer.py:335-385`): Pulse1-full→Pulse2 (`:53`), Pulse2-full→Pulse1 (`:62`), `ANY_PULSE` fill (`:67`), and `dropped_tracks` (`:84, :113`). |
| **REG-13** (`test_drum_mapping.py` bare-relative fixture + `invalid.json` leak) | #231 | **FIXED, verified.** `test_index_path` now points at the checked-in `tests/fixtures/test_dpcm_index.json` (`:21`); `invalid.json` is written under a `tmp` dir (`:76`). No repo-root leak on this run (`git status` clean of `invalid.json`). |
| **REG-14** (FamiStudio export tests shape-only) | #232 | **FIXED, verified.** New `TestFamiStudioGoldenBytes` (`tests/test_famistudio_export.py:89`) pins exact pulse1/triangle/noise/DPCM pattern-row text (`:116, :127, :138, :149`) — the FamiStudio equivalent of `TestCA65GoldenBytes`. |

REG-01…REG-09 (issues #39, #40, #42, #44, #45, #46, #47, #48, #49) remain fixed and holding — re-confirmed
via the suite passing (`TestCA65CompilationIntegration`, `test_pattern_detector_parallel.py`, etc. all green).

## Interim sprint: every fix shipped with a test (Dimension 1 spot-check)

The ~20 fixes landed since 07-05 each carry accompanying coverage — verified by locating the test for each:
- `#267` (reject missing `--config` path) → `test_config_manager.py`, `test_main.py`.
- `#268` (arranger pulse volume floor ≥1) → `test_voice_allocator.py::TestPulseVolumeFloor`.
- `#291` (MMC3 CODE_8000 fixed-$8000 bank) → `test_mappers.py`, `test_ca65_export.py`.
- `#41` (clamp `note_to_timer` instead of raising) → `test_pitch_tables.py`, `test_pitch_table_integration.py`.
- `#106` (parallel chunk-failure in-process recovery) → `test_pattern_detector_parallel.py` (`test_pool_failure_falls_back_to_serial`, `test_detected_occurrences_reconstruct_original` round-trip — solid, value-asserting).
- `#257/#258`, `#163/#164`, `#172/#173`, `#252/#253`, `#281-285` → all with tests in the suite.

No new untested subsystem, no coverage regression on a high-blast-radius path (NES-register, exporters,
mappers, compiler) was found.

---

## 1. Coverage Map (delta vs 07-05)

| Subsystem | Test module(s) | Status |
|-----------|-----------------|--------|
| ROM-compile e2e | `test_rom_validation_integration.py`, `test_e2e_pipeline.py` | **REG-10/#128 + REG-11/#129 now FIXED** (0 skips w/ cc65). **NEW REG-15** on the two error-handling *negative* tests in the same file (see §2). |
| Arranger role analysis | `test_role_analyzer.py` (new), `test_arranger*.py` | REG-12/#230 FIXED — contention/drop branches covered. |
| Exporters (FamiStudio) | `test_famistudio_export.py` (`TestFamiStudioGoldenBytes` new) | REG-14/#232 FIXED — golden-bytes pins added. |
| DPCM/drums | `test_drum_mapping.py`, `test_dpcm_*.py`, `test_drum_*.py` | REG-13/#231 FIXED — fixture path + tmp `invalid.json`. |
| Patterns (parallel) | `test_pattern_detector_parallel.py` | OK — #106 recovery + determinism (`test_results_identical_across_worker_counts`) held. |
| Mappers + `--mapper` | `test_mappers.py`, `test_ca65_export.py`, `test_main.py` | OK — #291 fixed-bank covered. |
| Config | `test_config_manager.py`, `test_main.py` | OK — #267 missing-path covered. |
| Pitch/timer clamp | `test_pitch_tables.py`, `test_pitch_table_integration.py` | OK — #41 clamp covered. |
| Everything else | per `_audit-common.md` §Layout | OK — 985 passing, no new gap. |

---

## 2. Findings

### REG-15: `compile_rom` error-handling tests are toothless and re-mask real exceptions as "CC65 not installed"
- **Severity**: MEDIUM
- **Dimension**: Weak assertions (Dim 2); Round-trip/e2e masking (Dim 3)
- **Location**: `tests/test_rom_validation_integration.py:216-237` (`test_compilation_with_invalid_assembly`) and `:305-322` (`test_compilation_failure_without_rom_output`)
- **Status**: NEW
- **Description**: The REG-10/#128 fix removed the `except → pytest.skip("CC65 may not be installed")` masking
  from the five compile-*success* tests in this file, but the same shape survives on the two compile-*failure*
  (negative-path) tests. Both are additionally toothless:
  - `test_compilation_with_invalid_assembly` is under `@pytest.mark.requires_cc65` (class
    `TestROMCompilationErrorHandling`, `:199`), so the conftest gate guarantees `ca65`/`ld65` are present
    whenever it runs. Its body is `if result: pass  else: assert result == False` — it passes for **any**
    return value of `compile_rom` (truthy → `pass` with a "should fail" comment but no assertion; falsy →
    `assert result == False` is trivially true). It therefore cannot catch a regression where invalid
    assembly wrongly "compiles", and any exception from `compile_rom` is swallowed as
    `pytest.skip("CC65 not installed")` — a misleading reason, since cc65 is provably present under the marker.
  - `test_compilation_failure_without_rom_output` (`TestPipelineFailureRecovery`, not cc65-gated) has the same
    `if result: assert rom_output.exists()  else: pass` toothless shape plus the same `except → skip`.
- **Evidence**:
  ```python
  # :228-237, inside a @pytest.mark.requires_cc65 class -> cc65 guaranteed present
  try:
      result = compile_rom(project_dir, rom_output)
      if result:
          # CC65 might be lenient, but this should fail
          pass                       # <-- no assertion
      else:
          assert result == False     # <-- trivially true
  except Exception:
      pytest.skip("CC65 not installed")   # <-- masks a real exception; cc65 IS installed
  ```
- **Impact**: These two tests give the appearance of guarding the compiler's failure path (bad/missing asm →
  no broken ROM) but assert nothing that can fail, and convert a genuine `compile_rom` crash into a green-ish
  skip under a false "CC65 not installed" reason. This is the exact failure shape this audit exists to catch —
  left in the same file the REG-10 fix cleaned up. Blast radius: the `compiler/` negative path (silent broken
  ROM detection) has no real regression net. Lower than REG-10 because the *positive* compile+validate path is
  now genuinely covered; this is the residual negative-path sibling.
- **Related**: REG-10 (#128), REG-11 (#129) — same masking idiom, now removed from the positive-path tests.
- **Suggested Fix**: Drop the `try/except → pytest.skip` from both (the `@requires_cc65` gate already handles
  cc65 absence for the first; add the marker to the second). Replace the pass-either-way bodies with a real
  assertion: `assert compile_rom(project_dir, rom_output) is False` for invalid/missing asm, and
  `assert not rom_output.exists()` to pin that a failed compile leaves no partial ROM.

---

## 3. Prioritized Backlog

| Rank | Finding | Status | Action | Why |
|------|---------|--------|--------|-----|
| 1 | REG-15 | NEW | De-mask + tighten the two `compile_rom` error tests (assert `is False` + no partial ROM; drop `except→skip`) | Only remaining `except→skip` masking + toothless assertions in the file the REG-10 sprint cleaned; the compiler's failure path has no real net |

Everything else previously flagged is fixed. No coverage regression, no new untested subsystem, no new
flakiness, no repo-root write leak (the sole `open('test_midi.json')` in `test_drum_engine.py:534` is inside
`@patch('builtins.open')` — mocked, not a real file), and no new unconditional skip/xfail were found.

Negative results worth recording (checked, found clean — do not re-investigate next run):
- **Dim 1**: every interim fix (#41, #106, #163/#164, #172/#173, #252/#253, #257/#258, #267/#268, #281-285,
  #291) shipped with a locatable test; no new blank module.
- **Dim 5**: `test_pattern_detector_parallel.py` worker-invariance + `#106` in-process-recovery
  round-trip (`test_detected_occurrences_reconstruct_original`) both assert values, not shape — determinism held.
- **Dim 6**: `git status` shows no `invalid.json`/`test_dpcm_index.json` repo-root litter after a full run;
  REG-13's leak is gone.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-07-06.md
```
