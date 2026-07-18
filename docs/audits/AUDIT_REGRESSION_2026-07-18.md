# MIDI2NES — Regression / Test-Hygiene Audit

**Date:** 2026-07-18
**Scope:** Test-suite health — coverage gaps, weak assertions, flaky/stale tests, skip-masking.
**Tree state:** `master` @ `308d712`, with the current-branch additions for #312–#315 / #318–#321
(~19 new regression tests across `tests/test_main.py`, `tests/test_patterns.py`,
`tests/test_enhanced_drum_mapper.py`, `tests/test_famistudio_export.py`,
`tests/test_nes_project_builder.py`) taken into account.
**Toolchain:** `ca65`/`ld65` present (`/usr/bin/ca65`, `/usr/bin/ld65`) — CC65-gated suites run for real.
**Collection:** `1043 tests collected`; targeted runs used throughout (no unscoped full run).

---

## 1. Coverage Map (subsystem → test module → coverage)

| Subsystem / module | Test module(s) | Coverage | Notes |
|---|---|---|---|
| `tracker/parser_fast.py` | `test_parser_fast.py` | (via integration) | OK |
| `tracker/parser.py` (full) | `test_midi_parser_integration.py` | indirect | OK |
| `tracker/track_mapper.py` | `test_track_mapper.py` | **76%** | up from 71% baseline (REG-08) |
| `tracker/tempo_map.py` | `test_tempo_map.py` | — | OK |
| `tracker/loop_manager.py` | `test_loop_manager.py` | — | OK |
| `tracker/pattern_detector.py` | `test_patterns.py` | high | `was_sampled` flag now tested |
| `tracker/pattern_detector_parallel.py` | `test_pattern_detector_parallel.py` | **76%** | stable vs 78% baseline (REG-06); determinism pinned |
| `arranger/*` | `test_arranger*.py`, `test_role_analyzer.py`, `test_voice_allocator.py` | high | front-end fully covered (REG-04) + real compile round-trip |
| `nes/emulator_core.py` | `test_frame_validation.py` + integration | **86%** | uncovered lines are CLI/`__main__` + shared extractor (covered elsewhere) |
| `nes/pitch_table.py` | `test_pitch_table*.py` | **96%** | OK |
| `nes/envelope_processor.py` | `test_envelope*.py` | **99%** | OK |
| `nes/project_builder.py` | `test_nes_project_builder.py` | **97%** | dead-macro removal now pinned (#314) |
| `nes/song_bank.py` | `test_song_bank.py` | **91%** | OK |
| `nes/debug_overlay.py` | `test_rom_diagnostics.py` (indirect) | **52%** | dev-only `--debug` overlay; low blast radius |
| `mappers/base.py` | `test_mappers.py` | **75%** | up from 59% baseline (REG-07) |
| `mappers/factory.py` | `test_mappers.py` | **75%** | up from 74% |
| `mappers/mmc1/mmc3/nrom.py` | `test_mappers.py` | 94/93/100% | OK |
| `exporter/exporter_ca65.py` | `test_ca65_export.py` | **93%** | golden-bytes class present (REG-05) |
| `exporter/exporter_famistudio.py` | `test_famistudio_export.py` | **95%** | golden-bytes class present (REG-14); crash fix pinned (#313) |
| `exporter/exporter_nsf.py` | `test_nsf_export.py` | **100%** | `NotImplementedError` pinned |
| `exporter/compression.py` | `test_compression*.py` | **78%** | OK |
| `exporter/base_exporter.py` | (indirect) | 44% | abstract base; low risk |
| `dpcm_sampler/dpcm_packer.py` | `test_dpcm_packer.py` | **99%** | OK |
| `dpcm_sampler/dpcm_sample_manager.py` | `test_dpcm_sample_manager.py` | **98%** | OK |
| `dpcm_sampler/enhanced_drum_mapper.py` | `test_enhanced_drum_mapper.py` | **90%** | alias table now tested (#315) |
| `dpcm_sampler/drum_engine.py` | `test_drum_engine.py` | **80%** | uncovered = `__main__` CLI only |
| `dpcm_sampler/generate_dpcm_index.py` | `test_dpcm_index_resolution.py`, `test_dpcm_packer.py` | **66%** | **gap — see REG-19** |
| `dpcm_sampler/dpcm_converter.py` | **none** | **0%** | **gap — see REG-18** |
| `compiler/cc65_wrapper.py` | `test_cc65_wrapper.py` | **92%** | up from 86% baseline (REG-09) |
| `compiler/compiler.py` | `test_e2e_pipeline.py`, `test_rom_validation_integration.py` | **78%** | OK |
| `config/config_manager.py` | `test_config_manager.py` | — | OK |
| `core/dto.py`, `types.py`, `exceptions.py` | none dedicated | indirect | pure data/enums; low risk |

Every subsystem in `_audit-common.md` § Project Layout maps to at least one test module, **except
`dpcm_sampler/dpcm_converter.py`** (0%, no test at all — REG-18).

---

## 2. Re-verification of prior fixes (REG-01 … REG-15) — all still GREEN

Confirmed against the live tree with the toolchain present:

- **REG-01** — `tests/test_ca65_export.py::TestCA65CompilationIntegration`: **9 passed**, 0 skipped
  (real `ca65`/`ld65` compile; the ±127 relative-branch fix in `nes/audio_engine.asm` holds).
- **REG-10 / REG-15** — `tests/test_rom_validation_integration.py`: **10 passed**, 0 skipped.
  Compile-success *and* compile-failure (`test_compilation_with_invalid_assembly`,
  `test_compilation_failure_without_rom_output`) tests assert unconditionally under
  `@requires_cc65`; `test_shared_music_asm_fixture_is_linkable` passes.
- **REG-11 / REG-04(e2e)** — `tests/test_e2e_pipeline.py`: **12 passed**. Anchor
  `test_full_pipeline_midi_to_validated_rom`, plus `test_full_pipeline_arranger_mode` and
  `test_full_pipeline_no_patterns_direct_export`, all do a real compile with validation ON.
- **REG-06** — determinism tie-break still pinned; `test_pattern_detector_parallel.py` passes.
- **REG-05 / REG-14** — golden-bytes classes (`TestCA65GoldenBytes`, `TestFamiStudioGoldenBytes`) present.
- Skip-masking grep across `tests/`: the only `pytest.skip` for CC65 is the legitimate
  `shutil.which` gate in `tests/conftest.py:pytest_runtest_setup`; no `except → skip` masking survives.
- New-branch tests (#312–#315, #318–#321): **280 passed, 1 skipped** (the 1 skip is a legitimate
  `Windows-only test` platform guard in `test_nes_project_builder.py:358`). The new tests are
  strong — exact-value/parametrized assertions (DPCM alias→sample table, `was_sampled` truth
  table, dead-symbol removal, `dpcm_sample_map` crash), not shape-only.

No regression of any closed REG item.

---

## 3. Findings

### REG-18: `dpcm_sampler/dpcm_converter.py` has 0% test coverage — WAV→DMC encoder emits NES sample bytes untested
- **Severity**: MEDIUM
- **Dimension**: 1 (untested subsystem emitting NES hardware data)
- **Location**: `dpcm_sampler/dpcm_converter.py:1-86` (whole file)
- **Status**: NEW
- **Description**: The module that turns a WAV into NES DMC sample data
  (`convert_wav_to_unsigned_pcm`, `delta_encode`, `dpcm_compress`, `convert_wav_to_dmc`) has
  **zero** test references and 0% coverage. Its output is raw DMC bytes consumed by the DPCM
  channel. The encoding is non-trivial DSP: `delta_encode` produces reconstructed 7-bit values
  clamped to `[0,127]` with ±1 steps, then `dpcm_compress` re-derives 1-bit deltas from
  consecutive comparisons and truncates at `dmc_bytes[:4081]`. A silent bug here (off-by-one in
  the bit-packing `byte |= (bits[i+j] << j)`, wrong mid-range start `0x40`, or the `4081` cap)
  produces a wrong-sounding or truncated drum sample with no test to catch it.
- **Evidence**: `grep -rn --include="*.py" "dpcm_converter|convert_wav_to_dmc|dpcm_compress"`
  returns only the module itself — no importer in the pipeline and no test. Coverage run:
  `dpcm_sampler/dpcm_converter.py  57  57  0%  1-85`.
- **Impact**: Blast radius is reduced because the module is a **standalone asset-prep CLI**, not
  wired into the automated MIDI→ROM pipeline (checked-in `.dmc` files + `dpcm_index.json` are what
  the pipeline consumes). But it is the only path that produces those bytes, so a regression is
  silently-wrong drum audio for anyone rebuilding samples.
- **Related**: `dpcm_index.json`, `generate_dpcm_index.py` (REG-19).
- **Suggested Fix**: Add `tests/test_dpcm_converter.py`. Concrete inputs: (a) a synthetic 8-bit
  mono WAV written with `wave` in a `tmp_path` fixture → assert `convert_wav_to_unsigned_pcm`
  length/dtype/range; (b) a known ramp array → assert exact `delta_encode` output and that
  `dpcm_compress` packs 8 bits/byte LSB-first with correct padding; (c) assert `convert_wav_to_dmc`
  never emits more than 4081 bytes and returns the written length.

### REG-19: `generate_dpcm_index()` directory-walk and the sample-not-found skip branch are untested
- **Severity**: LOW
- **Dimension**: 1 (untested paths in a live module)
- **Location**: `dpcm_sampler/generate_dpcm_index.py:85-88` (skip/warn on missing sample) and
  `:100-120` (`generate_dpcm_index(dmc_folder, output_json)`)
- **Status**: NEW
- **Description**: `generate_dpcm_index.py` is imported by the live pipeline
  (`main.py:597`, `main.py:989`) but only its `get_dpcm_sample_ids_from_frames` /
  `load_dpcm_index_into_packer` halves are tested (66% total). The `os.walk`-based
  `generate_dpcm_index()` builder and the "DPCM sample not found → `skipped += 1`" branch inside
  `load_dpcm_index_into_packer` have no coverage. The skip branch is on the live packer path — a
  regression that swallows a genuinely-missing sample would drop a drum without a test noticing.
- **Evidence**: coverage `dpcm_sampler/generate_dpcm_index.py  64  22  66%  85-88, 101-120, 157-162`.
- **Impact**: LOW — the walk function is offline asset prep; the skip branch is a recoverable
  warn-and-continue. No ROM breakage, but a silent drum drop is possible.
- **Related**: REG-18, `dpcm_index.json`.
- **Suggested Fix**: In `tests/test_dpcm_index_resolution.py`, add (a) a `tmp_path` tree of
  `.dmc` files → call `generate_dpcm_index(folder, out)` → assert the emitted JSON has one entry
  per file with sequential `id` and relative `filename`; (b) an index referencing a non-existent
  filename → assert `load_dpcm_index_into_packer` returns `skipped == 1, loaded == 0` and does not
  raise.

### REG-20: Two FamiStudio/exporter tests still gate on bare `assertIn("PATTERNS", ...)` structural presence
- **Severity**: LOW
- **Dimension**: 2 (weak assertions)
- **Location**: `tests/test_exporter_integration.py:121`, `tests/test_famistudio_export.py:61`
- **Status**: NEW (residual of REG-05/REG-14 scope, explicitly flagged for periodic re-grep by the skill)
- **Description**: Both tests assert only that the substring `"PATTERNS"` appears in the export,
  which would still pass if every note/volume value in the pattern rows were wrong. Each is
  partially rescued by an adjacent single note-value check (`assertIn("C-4 15", ...)`), and the
  path now has a dedicated golden-bytes class (`TestFamiStudioGoldenBytes`), so the residual risk
  is small — but the two structural checks themselves remain the weak-assertion shape this
  dimension exists to eliminate.
- **Evidence**: `grep 'assertIn("PATTERNS"' tests/` → the two lines above; both sit in
  general-structure test methods (`test_generate_famistudio_txt`,
  `test_famistudio_export_with_compression`).
- **Impact**: LOW — a values-wrong/structure-right regression in these two methods would pass, but
  the golden-bytes class covers the same emit path.
- **Related**: REG-05 (#45), REG-14 (#232).
- **Suggested Fix**: Either delete the redundant `assertIn("PATTERNS")` assertions (the golden-bytes
  class already pins the pattern rows), or extend each to assert a full expected pattern-row line
  (note + volume + frame) rather than the section header alone.

---

## 4. Prioritized Backlog (write these first, by blast radius)

1. **REG-18** — `tests/test_dpcm_converter.py`: pin `delta_encode`/`dpcm_compress` byte output and
   the 4081-byte cap. Highest blast radius of the three (only producer of DMC sample bytes, 0%).
2. **REG-19** — extend `tests/test_dpcm_index_resolution.py` to cover the `os.walk` builder and the
   missing-sample skip branch (live packer path).
3. **REG-20** — strengthen or drop the two `assertIn("PATTERNS")` checks (quick hygiene cleanup).

Overall the suite is **healthy**: 1043 tests, all prior REG-01…REG-15 fixes verified still green,
CC65-gated suites compile real ROMs and assert unconditionally, and the new #312–#315 / #318–#321
tests are exact-value regressions. The only genuinely blank subsystem is `dpcm_converter.py`.

---

```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-07-18.md
```
