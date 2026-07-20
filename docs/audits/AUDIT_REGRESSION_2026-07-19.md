# Regression / Test-Hygiene Audit — 2026-07-19

Audit of the **test suite itself**: coverage gaps on breakable code, weak assertions,
stale/flaky/mis-targeted tests. Scope per `.claude/commands/audit-regression/SKILL.md`,
severity per `.claude/commands/_audit-severity.md`.

- **Toolchain**: `ca65`/`ld65` present at `/usr/bin` — CC65-gated suites run for real.
- **Collection**: 1085 tests across 55 `test_*.py` + `conftest.py`.
- **Dedup source**: `/tmp/audit/issues.json` (18 open issues) + `docs/audits/` prior reports
  (notably `AUDIT_REGRESSION_2026-07-18.md`, `-06-28`, `-06-29`).

## Executive Summary

The test suite is in strong post-sprint condition. **Every previously-fixed REG item
(REG-01…REG-21) re-verified as still holding** — no regressions of prior fixes. Yesterday's
three findings (REG-18/19/20) are all now resolved in-tree. Coverage on the high-blast-radius
NES-register path is uniformly high. Three findings this run: one confirmed-still-open flaky
hang (HIGH, existing #355), one round-trip coverage gap (MEDIUM, existing #311, now
partially covered), and one new LOW gap on a dev-only overlay helper.

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 1 |
| LOW | 1 |
| **Total** | **3** |

New: 1 · Existing: 2

---

## 1. Coverage Map

Whole-suite `--cov` measured by running the full suite **minus the #355 hang combo**
(`--ignore=tests/test_patterns.py --ignore=tests/test_performance_suite.py`): 987 passed,
1 skipped. Per-module figures below from targeted `--cov` runs.

| Subsystem | Module | Test module(s) | Cov | Note |
|-----------|--------|----------------|-----|------|
| NES core | `nes/emulator_core.py` | test_core, test_frame_validation, test_enhanced_drum_mapper, test_arranger* | **97%** | DPCM branch (181-239) covered by drum-mapper tests |
| NES core | `nes/pitch_table.py` | test_pitch_tables, test_pitch_table_integration | **96%** | |
| NES core | `nes/envelope_processor.py` | test_envelope, test_envelope_integration | **99%** | |
| NES core | `nes/project_builder.py` | test_nes_project_builder, test_ca65_export | **80%** | |
| NES core | `nes/song_bank.py` | test_song_bank | **93%** | |
| NES core | `nes/debug_overlay.py` | *(none dedicated)* | **52%** | **REG-24** — helper untested |
| Exporters | `exporter/exporter_ca65.py` | test_ca65_export, test_exporter_integration | **94%** | golden-bytes class present |
| Exporters | `exporter/exporter_famistudio.py` | test_famistudio_export | good | REG-20 hardened |
| Exporters | `exporter/base_exporter.py` | *(via subclasses)* | 44% | dead helpers — #302 EXP-09 (existing) |
| Exporters | `exporter/compression.py` | test_compression_integration | 84% | partial dead code — #302 |
| Mappers | `mappers/factory.py` | test_mappers | **75%** | up from 74% baseline |
| Mappers | `mappers/base.py` | test_mappers | **75%** | up from 59% baseline |
| Compiler | `compiler/compiler.py` | test_e2e_pipeline, test_rom_validation_integration | **92%** | |
| Compiler | `compiler/cc65_wrapper.py` | test_cc65_wrapper | **86%** | holding |
| Tracker | `tracker/track_mapper.py` | test_track_mapper | **76%** | up from 71% baseline |
| Tracker | `tracker/pattern_detector.py` | test_patterns, test_pattern_integration | **89%** | |
| Tracker | `tracker/pattern_detector_parallel.py` | test_pattern_detector_parallel | **79%** | up from 78% baseline |
| Tracker | `tracker/tempo_map.py` | test_tempo_map, test_enhanced_loop_patterns | **95%** | |
| Tracker | `tracker/loop_manager.py` | test_loop_manager, test_enhanced_loop_patterns | **91%** | |
| Arranger | `arranger/role_analyzer.py` | test_role_analyzer, test_arranger | **81%** | |
| Arranger | `arranger/voice_allocator.py` | test_voice_allocator, test_arranger | **97%** | |
| Arranger | `arranger/gm_instruments.py` | test_arranger | **98%** | |
| Arranger | `arranger/pipeline_integration.py` | test_arranger, test_arranger_frame_contract | **80%** | |
| DPCM | `dpcm_sampler/dpcm_converter.py` | test_dpcm_converter | **89%** | REG-18 now FIXED (was 0%) |
| DPCM | `dpcm_sampler/drum_engine.py` | test_drum_engine, test_dpcm_index_resolution | **80%** | precise count assertions |
| DPCM | `dpcm_sampler/generate_dpcm_index.py` | test_dpcm_index_resolution | **91%** | REG-19 now FIXED |
| Core | `core/dto.py` | *(via core/types importers)* | 86% | |

**No subsystem is without a test module.** Every source dir in `_audit-common.md`
§ Project Layout maps to at least one `test_*.py`.

## 2. Re-Verification of Prior Fixes (all HOLDING)

Per the skill's mandate to re-verify every run — a landed fix is not guaranteed to stay
landed. All confirmed green with the CC65 toolchain **present** (compile, not skip):

- **REG-01/#39** (out-of-range `bcc` in `nes/audio_engine.asm`): `TestCA65CompilationIntegration`
  — 9/9 PASS, no skips.
- **REG-10/#128 + REG-11/#129 + REG-15/#299** (skip-masking removed from ROM-validation +
  e2e gates): `tests/test_rom_validation_integration.py` (11 tests) + `tests/test_e2e_pipeline.py`
  (12 tests incl. `test_full_pipeline_arranger_mode`, `test_full_pipeline_no_patterns_direct_export`)
  — all PASS, **0 skips** (verified with `-rs`). No `except → pytest.skip("CC65 not installed")`
  masking remains.
- **REG-04/#44…REG-09/#49** (arranger + track_mapper + cc65_wrapper + parallel-detector +
  mappers coverage): all re-measured at or above their documented baselines (see map).
- **REG-18/19/20** (yesterday's findings): **all resolved** — `test_dpcm_converter.py` gives
  `dpcm_converter.py` 89% (was 0%); `generate_dpcm_index.py` at 91%; no live bare
  `assertIn("PATTERNS", …)` remains in `test_famistudio_export.py` / `test_exporter_integration.py`
  (both now carry `#339/REG-20` guard comments + value assertions).

Skipped-test census: the only `pytest.skip` calls are legitimate environmental gates
(`dpcm_index.json` absence, OS-specific `main.asm` path tests, `pyflakes` absent, the real
`shutil.which` CC65 gate in `conftest.py:pytest_runtest_setup`). **No stale/untracked
skip-masking found.**

---

## 3. Findings

### REG-22: `test_parser_fast.py` + `test_patterns.py` hang when run together (default invocation)
- **Severity**: HIGH
- **Dimension**: 5 — Determinism / flakiness
- **Location**: `tests/test_parser_fast.py`, `tests/test_patterns.py` (interaction)
- **Status**: Existing: #355
- **Description**: Running the two files together in a single pytest process hangs
  indefinitely; each passes alone. **Confirmed still reproducing this run**: `python -m pytest
  tests/test_parser_fast.py tests/test_patterns.py` timed out at 120 s (never reached a
  summary line). New diagnostic: the hang **does not occur** with `-p no:cacheprovider`
  (same two files completed and passed) — implicating an interaction between the pytest
  cacheprovider plugin and state left by these modules (test_patterns exercises
  `ParallelPatternDetector`'s `ProcessPoolExecutor`; a worker-pool / fork-after-cache
  interaction is the likely culprit).
- **Evidence**: `timeout 120 python -m pytest tests/test_parser_fast.py tests/test_patterns.py`
  → killed at timeout (exit 143); with `-p no:cacheprovider` → all pass, exit 0.
- **Impact**: A single-pass full `pytest` (and therefore whole-suite `--cov`) cannot complete
  in the default invocation — the entire regression safety net can't be measured or gated in
  CI in one run. This audit had to `--ignore` both files to measure coverage. Blast radius:
  CI reliability + coverage observability for the whole project.
- **Related**: #355; `tracker/pattern_detector_parallel.py` (ProcessPoolExecutor).
- **Suggested Fix**: Root-cause the pool/cache interaction (e.g. ensure the detector uses a
  `spawn` context or tears the pool down deterministically at test teardown), rather than
  papering over it. Interim: pin `-p no:cacheprovider` for CI's full run, or add a
  session-scoped fixture that closes lingering pools between the two modules.

### REG-23: Exact-only round-trip invariant (referenced window == pattern events) not fully pinned
- **Severity**: MEDIUM
- **Dimension**: 3 — Round-trip / end-to-end gaps
- **Location**: `tests/test_patterns.py` (matcher round-trip coverage)
- **Status**: Existing: #311 (PAT-10)
- **Description**: #311 asks for a test pinning that every referenced pattern window equals
  the pattern's stored events (the exact-repeats-only invariant). **Partial coverage now
  exists**: `test_detected_patterns_are_real_repeats` (`tests/test_patterns.py:863`) asserts
  that every detected pattern's occurrences reconstruct identical *content* from the source
  sequence — a real round-trip check on the parallel detector's output. What remains
  unpinned is the tighter contract that the pattern's own stored `events`/`pattern` field
  equals the referenced window (the detector produces analysis-only `references`; per
  `exporter_ca65` #4 the exporter does not consume them, so this is a metrics-integrity
  guard, not a ROM-correctness guard).
- **Evidence**: `test_patterns.py:863-881` covers occurrence-content equality; no test asserts
  `patterns[pid]['pattern'] == sequence[first_pos:first_pos+length]` directly.
- **Impact**: A drift between a pattern's stored value and its referenced window would go
  uncaught — currently cosmetic (references are analysis-only), but MEDIUM because it guards
  the CRITICAL "lossy where it claims lossless" failure mode should the export path ever
  begin consuming references.
- **Related**: #311; #4 (references are analysis-only); REG-06/#46.
- **Suggested Fix**: Add one assertion to `test_detected_patterns_are_real_repeats` (or a
  sibling test) pinning `info['pattern'] == tuple(sequence[positions[0]:positions[0]+length])`
  for each detected pattern, closing the exact wording of #311.

### REG-24: `nes/debug_overlay.py` has no dedicated test module; `create_debug_rom_variant` + CLI entry unexercised
- **Severity**: LOW
- **Dimension**: 1 — Untested subsystems / modules
- **Location**: `nes/debug_overlay.py:634-672` (`create_debug_rom_variant` + `__main__`)
- **Status**: NEW
- **Description**: `debug_overlay.py` sits at 52% coverage with no dedicated `test_*.py`. The
  actually-used `--debug` path (`generate_full_debug_system`, injected via `NESProjectBuilder`)
  IS smoke-tested for compile by `tests/test_rom_validation_integration.py::TestDebugModeROMGeneration::test_debug_mode_rom_generation`.
  The uncovered block is the **standalone** `create_debug_rom_variant(music_asm, output)`
  helper — it reads a `music.asm`, appends the debug system, and writes a combined `.asm` —
  plus the `if __name__ == "__main__"` CLI. Nothing exercises it, so a regression in its
  file-combination logic (e.g. dropping the original `music.asm` body, or malforming the
  concatenation so `ca65` chokes) is silent.
- **Evidence**: `grep -rl create_debug_rom_variant tests/` → no match; `--cov=nes.debug_overlay`
  reports lines 634-662 (function body) and 666-672 (`__main__`) uncovered across the full suite.
- **Impact**: LOW — dev-only overlay helper off the main `--debug` pipeline; a break here does
  not affect a normally-generated ROM.
- **Related**: `nes/project_builder.py` (the live `--debug` path).
- **Suggested Fix**: Add `tests/test_debug_overlay.py` with a test that feeds a small
  `minimal_music_asm` (the shared `conftest.py` fixture) through `create_debug_rom_variant`,
  then asserts the output file (a) contains the original music body verbatim, (b) contains the
  `DEBUG OVERLAY INJECTED BELOW` marker + `generate_full_debug_system()` output, and (c)
  assembles under `ca65` (gate `@pytest.mark.requires_cc65`).

---

## 4. Prioritized Backlog (by blast radius)

1. **REG-22 / #355 (HIGH)** — root-cause the parser_fast+patterns hang. Highest leverage: it
   blocks single-pass full-suite runs and coverage gating in CI for *everything*. Fix the
   ProcessPoolExecutor/cacheprovider interaction in/around
   `tracker/pattern_detector_parallel.py`; add a teardown fixture that reaps lingering pools.
2. **REG-23 / #311 (MEDIUM)** — one-line assertion in `test_patterns.py` closing the exact
   wording of the exact-only round-trip invariant. Cheap, closes a tracked issue.
3. **REG-24 (LOW)** — new `tests/test_debug_overlay.py` covering `create_debug_rom_variant`.

---

## Suggested next step

```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-07-19.md
```
