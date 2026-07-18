# Regression / Test-Hygiene Audit — MIDI2NES

- **Date**: 2026-07-18
- **Scope**: The test suite itself (`tests/`) — coverage gaps, weak assertions, round-trip/e2e
  gaps, stale/wrong-target tests, determinism/flakiness, fixture hygiene. Delta audit over
  `AUDIT_REGRESSION_2026-07-06.md` (the most recent prior regression report), cross-referenced
  against two bugs found by sibling audits running in this same suite today:
  `AUDIT_EXPORTERS_2026-07-18.md` (EXP-11) and `AUDIT_MAPPERS_2026-07-18.md` (MAP-2026-07-18-1).
- **Skill**: `/audit-regression`
- **Suite state at audit time**: **1006 passed, 1 skipped** (`python -m pytest -q`, 227s; 1007
  collected), up from 986 passed/1 skipped at 07-06 — 21 new tests landed since (arranger
  pulse-volume-floor / arp-speed validation classes in `tests/test_voice_allocator.py` among
  them, from concurrent work in this session). `ca65`/`ld65` both present; the single skip is
  the legitimate `Windows-only test` platform gate at `tests/test_nes_project_builder.py:346`.
  Suite is fully green — zero failures, despite the two coverage gaps below.
- **Dedup basis**: `/tmp/audit/issues.json` (27 OPEN issues, pre-fetched by a concurrent audit run
  this session — reused per the mandatory-dedup step). Prior reports scanned:
  `AUDIT_REGRESSION_2026-07-06.md` (and its own `-07-05`/`-07-03`/`-06-29`/`-06-28` chain).
  Neither finding below has a matching open issue (checked titles for `famistudio`, `dpcm_sample_map`,
  `relative`, `compile`, `project_dir` — only unrelated hits: #269 PL-08, #134 TD-07).

> **Headline**: **Two NEW findings (both MEDIUM)** — both are the exact failure shape this audit
> exists to catch: a test suite that was green while two real, user-facing bugs shipped
> undetected. `tests/test_famistudio_export.py` never builds a `frames` dict containing the
> `dpcm_sample_map` side-table key, so it never exercised the crash EXP-11 found (any DPCM song
> makes the FamiStudio exporter raise `ValueError`). No test anywhere in the suite calls
> `compile_rom`/`ROMCompiler.compile()` with a relative `project_dir`, so MAP-2026-07-18-1's
> `main.py compile <relative-dir> <out>` failure (documented in `CLAUDE.md` itself) was invisible —
> every compile-path test uses pytest's `tmp_path`/`temp_dir` fixtures (always absolute) or mocks
> `main.compile_rom` outright. REG-15 (#299), the one open item carried from the 07-06 report, is
> now **confirmed fixed and holding**.

---

## 1. Status of prior regression findings

| Prior | Issue | Verdict now (2026-07-18) |
|-------|-------|---------------------------|
| REG-15 (`compile_rom` negative-path tests toothless + `except→skip` masking) | #299 | **FIXED, verified.** `tests/test_rom_validation_integration.py:212-231` (`test_compilation_with_invalid_assembly`) and `:301-317` (`test_compilation_failure_without_rom_output`) now assert `compile_rom(...) is False` and `not rom_output.exists()` unconditionally, with no `try/except → pytest.skip`. Commit `d08e4ba` (`fix: de-tooth compile_rom error-handling tests, drop false CC65-skip masking (#299)`) is present on this branch. |
| REG-01…REG-14 | various | Re-confirmed still fixed and holding (suite green, `TestCA65CompilationIntegration`, `TestFamiStudioGoldenBytes`, `test_pattern_detector_parallel.py` determinism, `test_role_analyzer.py` contention branches all present and passing per code inspection). No regression found in any of these. |

No stale skip/xfail found: every remaining `pytest.skip(...)` in the suite is a legitimate
environment gate (`shutil.which` CC65 absence via `conftest.py:pytest_runtest_setup`, missing
`dpcm_index.json`/`pyflakes` in the checkout, or a `Windows-only test` platform skip in
`tests/test_nes_project_builder.py:346`) — none mask a real failure as "toolchain not installed".

---

## 2. Findings

### REG-16: `tests/test_famistudio_export.py` never exercises a `frames` dict carrying `dpcm_sample_map`, so it missed EXP-11's crash on every DPCM-bearing song
- **Severity**: MEDIUM
- **Dimension**: 1 (Untested subsystems/paths) — a coverage gap on a path that emits exporter
  output and has now had a crash-level bug land on it clears the MEDIUM bar in the regression
  skill's own severity note ("a gap on a path that *has had bugs*... is MEDIUM").
- **Location**: `tests/test_famistudio_export.py` (all of `TestFamiStudioExport` and
  `TestFamiStudioGoldenBytes`); root cause under test is `exporter/exporter_famistudio.py:90`
  (`for channel, events in frames_data.items():`, no skip for the `dpcm_sample_map` key that
  `nes/emulator_core.py:206-242` attaches to `frames` for any song using DPCM samples).
- **Status**: NEW
- **Description**: Every `frames`/`self.test_frames` fixture in this file is built by hand with
  channel keys drawn only from `{pulse1, pulse2, triangle, noise, dpcm}` — none include
  `dpcm_sample_map`, the side-table key the real pipeline (`nes/emulator_core.py`) attaches
  whenever a song's DPCM channel actually resolves sample IDs. `generate_famistudio_txt` iterates
  every top-level key of `frames_data` as if it were a channel (`exporter/exporter_famistudio.py:90`),
  so on real DPCM-bearing output it treats `dpcm_sample_map` as a sixth "channel", builds a pattern
  key `f"dpcm_sample_map_{n}"`, and crashes at `channel, index = pattern_key.split('_')`
  (`ValueError: too many values to unpack`, `exporter_famistudio.py:128`) — this is exactly
  EXP-11 (HIGH, `AUDIT_EXPORTERS_2026-07-18.md`). Confirmed by re-reading the exporter and every
  fixture in this test file: none pass a `dpcm_sample_map` key, including the file's own
  `TestFamiStudioGoldenBytes.FRAMES`, which uses a `dpcm` channel with `note`/`volume` but never
  the side-table.
- **Evidence**:
  ```python
  # exporter/exporter_famistudio.py:90-128 — no skip for dpcm_sample_map
  for channel, events in frames_data.items():
      ...
      if channel in ['pulse1', 'pulse2', 'triangle']: ...
      elif channel == 'noise': ...
      elif channel == 'dpcm': ...
      # dpcm_sample_map falls through with an empty per-frame body -> still gets
      # a pattern_key "dpcm_sample_map_0" written below
  ...
  for pattern_key, pattern_data in patterns.items():
      channel, index = pattern_key.split('_')   # "dpcm_sample_map_0".split('_')
                                                  # -> ValueError: too many values to unpack

  # tests/test_famistudio_export.py — every fixture, grepped for 'dpcm_sample_map': no hits
  $ grep -n dpcm_sample_map tests/test_famistudio_export.py   # (no output)
  ```
  Compare to the sibling exporter, which is explicitly guarded and explicitly tested for it:
  `exporter/exporter_ca65.py:104` (`if name != 'dpcm_sample_map' and data`) and
  `dpcm_sampler/generate_dpcm_index.py:135-146` both skip/read the key explicitly, and
  `tests/test_ca65_export.py` exercises DPCM-bearing frames through that path.
- **Impact**: The gap let a crash-level bug (FamiStudio export completely non-functional for any
  DPCM-bearing song, EXP-11/HIGH) ship undetected — this is the FamiStudio exporter's *only*
  DPCM interaction path and it has zero coverage of the shape real pipeline output takes. Any CI
  run of this suite would stay green while `python main.py export ... --format famistudio` (once
  wired up) crashes on the first real song with drums.
- **Related**: EXP-11 (`AUDIT_EXPORTERS_2026-07-18.md`) — the underlying bug this gap let through.
- **Suggested Fix**: Add a fixture/test to `tests/test_famistudio_export.py` that includes a
  `dpcm_sample_map` key alongside a `dpcm` channel (e.g.
  `{'dpcm': {'0': {'note': 4, 'volume': 15}}, 'dpcm_sample_map': {'0': 3, '1': 7}}`, matching the
  `dense_id -> catalog_id` shape `nes/emulator_core.py` produces) and assert
  `generate_famistudio_txt(frames)` returns without raising and does not emit a
  `PATTERN "dpcm_sample_map_*"` block. This test should be added as part of (or immediately
  alongside) the EXP-11 fix so it fails red before the fix and green after.

---

### REG-17: No test anywhere in the suite calls `compile_rom`/`ROMCompiler.compile()` with a relative `project_dir`, missing MAP-2026-07-18-1's path-doubling failure
- **Severity**: MEDIUM
- **Dimension**: 1 (Untested subsystems/paths) / 6 (Fixture & isolation hygiene — every existing
  fixture happens to be absolute, which is exactly why the gap is invisible)
- **Location**: `tests/test_main.py:760-799` (`TestRunCompile` — both tests `@patch('main.compile_rom')`,
  so the real `ROMCompiler`/`cc65_wrapper` subprocess path is never reached);
  `tests/test_rom_validation_integration.py` and `tests/test_main_pipeline.py` (every
  `compile_rom(project_dir, ...)` call uses `project_dir`/`temp_dir` built from pytest's `tmp_path`
  fixture or `tempfile.TemporaryDirectory()`/`tempfile.mkdtemp()`, both always absolute);
  `tests/conftest.py:50-54` (`temp_dir` fixture: `tempfile.TemporaryDirectory()`). Root cause under
  test is `compiler/compiler.py:141-180` (`ROMCompiler.compile()` never calls `.resolve()` on
  `project_dir` before using it as both a path prefix and the subprocess `cwd`).
- **Status**: NEW
- **Description**: `main.py compile <relative-dir> <out>` — the literal command form documented
  in `CLAUDE.md`'s "Step-by-step pipeline for debugging" section and printed by `run_prepare`'s own
  "next step" guidance — fails with a `ca65` file-not-found error because `ROMCompiler.compile()`
  passes the same relative `project_dir` as both the assemble/link source-path prefix and the
  subprocess `cwd`, doubling the directory (`nes_project/nes_project/main.asm`). This is
  MAP-2026-07-18-1 (HIGH, `AUDIT_MAPPERS_2026-07-18.md`). Re-reading every test that calls
  `compile_rom`/`ROMCompiler.compile` in the suite: `TestRunCompile` in `tests/test_main.py` mocks
  `main.compile_rom` entirely (`@patch('main.compile_rom')`), so it verifies mapper-selection wiring
  only and never reaches `compiler/compiler.py` or `compiler/cc65_wrapper.py` at all. Every other
  caller (`tests/test_rom_validation_integration.py`, `tests/test_e2e_pipeline.py`,
  `tests/test_main_pipeline.py`, `tests/test_mappers.py`) builds `project_dir` from the shared
  `temp_dir`/`tmp_path` fixtures, which pytest guarantees are absolute
  (`tempfile.TemporaryDirectory()` / `tempfile.mkdtemp()` both return absolute paths). No `os.chdir`
  + relative-`project_dir` combination exists anywhere in the suite for the compile path (the few
  `os.chdir` call sites in `tests/test_main.py:993,1021,1954` cover unrelated `run_export`/
  `run_full_pipeline` cwd-relative-file lookups, not `compile_rom`'s `project_dir` argument, and
  `run_full_pipeline` itself is unaffected by MAP-2026-07-18-1 since it always builds `project_path`
  from `tempfile.TemporaryDirectory()`).
- **Evidence**:
  ```python
  # tests/test_main.py:773-786 — real compile_rom never invoked
  @patch('main.validate_rom')
  @patch('main.compile_rom')
  def test_run_compile_defaults_to_mmc3(self, mock_compile, mock_validate):
      ...
      mock_compile.return_value = True
      args = Namespace(input=str(self.project_dir), output=str(self.output_rom), ...)
      run_compile(args)
      used_mapper = mock_compile.call_args.kwargs['mapper']  # only checks the mapper kwarg

  # tests/conftest.py:50-54 — the shared fixture is always absolute
  @pytest.fixture
  def temp_dir():
      with tempfile.TemporaryDirectory() as tmpdir:
          yield Path(tmpdir)   # tempfile always returns an absolute path
  ```
  Grepping the whole suite for `compile_rom(` / `ROMCompiler(` call sites and checking each
  `project_dir`'s construction confirms every one traces back to `tmp_path`, `temp_dir`, or
  `tempfile.mkdtemp()` — never a bare relative string like `"nes_project"`.
- **Impact**: The gap let a HIGH-severity, CLAUDE.md-documented CLI flow break silently — `prepare`
  → `compile` with a relative project directory (the natural invocation after `cd`-ing to a working
  directory) fails with a confusing `ca65` file-not-found instead of compiling, and no test would
  catch a regression or a fix in this exact path. Blast radius matches MAP-2026-07-18-1: all three
  mappers, the entire step-by-step/debugging flow, and any library caller of
  `compile_rom`/`ROMCompiler.compile()` that passes a relative path.
- **Related**: MAP-2026-07-18-1 (`AUDIT_MAPPERS_2026-07-18.md`) — the underlying bug this gap let
  through. Not a duplicate of REG-10/#128 (that was a stale-fixture/masked-skip gap on the
  *positive* compile path with absolute paths, already fixed) — this is a distinct gap: absolute
  paths are covered thoroughly, relative paths are not covered at all.
- **Suggested Fix**: Add a test (e.g. to `tests/test_rom_validation_integration.py` or a new
  `tests/test_compiler.py`) that builds a project with `tmp_path`, then calls
  `compile_rom(Path(os.path.relpath(project_dir, Path.cwd())), rom_output)` (or `os.chdir`s into
  `project_dir.parent` and passes the bare directory name) and asserts it succeeds identically to
  the absolute-path case — this should be written to fail red against the current
  `compiler/compiler.py` and pass once MAP-2026-07-18-1's `.resolve()` fix lands, per this audit
  suite's usual "test proves the bug, then proves the fix" pairing.

---

## 3. Coverage Map (delta vs 07-06)

| Subsystem | Test module(s) | Status |
|-----------|-----------------|--------|
| FamiStudio export / DPCM interaction | `tests/test_famistudio_export.py` | **NEW GAP: REG-16** — `dpcm_sample_map` side-table shape never constructed in any fixture. |
| Compiler (`ROMCompiler.compile`) relative-path handling | `tests/test_main.py` (`TestRunCompile`, mocked), `tests/test_rom_validation_integration.py`, `tests/test_main_pipeline.py` (all absolute) | **NEW GAP: REG-17** — no relative-`project_dir` case anywhere. |
| ROM-compile e2e (absolute-path positive + negative) | `test_rom_validation_integration.py`, `test_e2e_pipeline.py` | OK — REG-10/#128, REG-11/#129, REG-15/#299 all re-verified fixed and holding. |
| Arranger role analysis / voice allocation | `test_role_analyzer.py`, `test_voice_allocator.py` (grew by 6 tests this session — pulse-volume-floor + arp-speed-zero validation) | OK, growing. |
| Patterns (parallel) | `test_pattern_detector_parallel.py` | OK — determinism pinning held (spot-checked, no change since 07-06). |
| Mappers + `--mapper` | `test_mappers.py`, `test_ca65_export.py`, `test_main.py` | OK, no new gap found this pass. |
| Everything else | per `_audit-common.md` §Layout | No new gap found; 1007 tests collected (+21 vs 07-06's 986). |

---

## 4. Prioritized Backlog

| Rank | Finding | Status | Action | Why |
|------|---------|--------|--------|-----|
| 1 | REG-16 | NEW | Add a `dpcm_sample_map`-bearing fixture to `tests/test_famistudio_export.py` asserting no crash and no spurious pattern block | Directly missed a HIGH crash bug (EXP-11) that ships FamiStudio export broken for every DPCM song |
| 2 | REG-17 | NEW | Add a relative-`project_dir` test for `compile_rom`/`ROMCompiler.compile()` | Directly missed a HIGH, CLAUDE.md-documented CLI failure (MAP-2026-07-18-1) |

Negative results worth recording (checked, found clean — do not re-investigate next run):
- REG-15 (#299) fix confirmed still in place at `tests/test_rom_validation_integration.py:212-231,301-317` —
  both negative-path compile tests assert `is False` / `not rom_output.exists()` unconditionally,
  no `except → skip` masking.
- No stale `@unittest.skip`/`xfail` without a tracking issue found; every remaining `pytest.skip`
  call site is a legitimate environment gate (CC65 absence, missing checked-in fixture file,
  platform).
- No new repo-root file litter (`git status` shows only expected in-progress/untracked audit docs
  and files already known to be under concurrent edit in this session — no stray test-output
  artifacts).
- Suite grew from 986 → 1007 collected tests since 07-06 with no collection errors.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-07-18.md
```
