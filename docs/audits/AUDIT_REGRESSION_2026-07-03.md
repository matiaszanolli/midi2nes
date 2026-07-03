# Regression / Test-Hygiene Audit — MIDI2NES

- **Date**: 2026-07-03
- **Scope**: The test suite itself (`tests/`) — coverage gaps, weak assertions, round-trip/e2e gaps,
  stale/wrong-target tests, determinism/flakiness, fixture hygiene. Delta audit over
  `AUDIT_REGRESSION_2026-06-28.md` / `-06-29.md`.
- **Skill**: `/audit-regression`
- **Suite state at audit time**: **783 passed, 6 skipped** (`python -m pytest -q`, ~218s). `ca65`/`ld65`
  both present at `/usr/bin`. 5 of the 6 skips are the still-open REG-10 (`test_rom_validation_integration.py`);
  the 6th is a legitimate `Windows-only test` skip (`test_nes_project_builder.py:358`). Suite is green.
- **Dedup basis**: `gh issue list --repo matiaszanolli/midi2nes --limit 200 --json number,title,state,labels`
  (47 open issues) plus `--state closed --limit 300` (100 most-recent closed). Prior reports scanned:
  `AUDIT_REGRESSION_2026-06-28.md`, `AUDIT_REGRESSION_2026-06-29.md`, `AUDIT_TECH_DEBT_2026-06-29.md`,
  `AUDIT_TECH-DEBT_2026-07-03.md`, `AUDIT_EXPORTERS_2026-06-29.md`, `AUDIT_EXPORTERS_2026-07-03.md`,
  `AUDIT_DPCM_2026-06-29.md`, `AUDIT_MAPPERS_2026-07-03.md`.

## ⚠️ Dedup-data integrity incident (read before the findings below)

Partway through this audit, a second read of `/tmp/audit/issues.json` — the exact path the shared
`_audit-common.md` protocol instructs every audit to write its `gh issue list` snapshot to — returned
**71 issues from a completely different repository** (labels like `renderer`/`Vulkan`, `import-pipeline`,
`legacy-compat`; titles referencing FNV/NIF/BSA/SpeedTree — clearly a Gamebryo/Bethesda-engine codebase,
not MIDI2NES). My first read of that same path, minutes earlier, had correctly returned 47 MIDI2NES issues
(`PL-`, `PAT-`, `NH-`, `TD-`, `ARR-`, `EXP-`, `D-`, `M-`, `PERF-`, `F-` prefixes matching this repo's audit
scheme). The file had been silently overwritten between my two reads.

Root cause (most likely, not confirmed): this audit runs as one of several **parallel audit agents**, each
following the same shared protocol, and the protocol names a **single fixed shared path**
(`/tmp/audit/issues.json`) with no per-agent/per-run uniqueness — so concurrent `gh issue list` writes from
unrelated audits (apparently running against a different repository entirely in this environment) race and
clobber each other. This is a **latent bug in the shared audit protocol itself** (`_audit-common.md` §
Deduplication), not something specific to this run, and it means **any** audit trusting a bare read of
`/tmp/audit/issues.json` without re-verifying its contents could silently dedup against the wrong repo's
issue list and either wrongly suppress a real finding (if a title happens to collide) or, more likely here,
just get garbage that doesn't match anything and over-reports.

I did not act on the corrupted data. I re-ran `gh issue list` against a private, session-scoped path
(`/tmp/claude-*/.../scratchpad/issues_regression.json`) — not the shared one — got the correct 47 MIDI2NES
issues back (verified content matches my first, pre-corruption read), and used that for all dedup decisions
below. I also saw no other injected instructions in any tool output during this run (no fake "system
reminder" asking me to hide anything) — just the clobbered file. Flagging this so the shared protocol can be
fixed (e.g., a per-run temp file, or a repo-name assertion after the read) rather than silently trusting a
shared mutable path next time.

## Status of the 2026-06-28 / 2026-06-29 regression findings (re-verified this run)

| Prior | Issue | Verdict now |
|-------|-------|-------------|
| REG-01 (CA65 compile gate RED) | #39 | **FIXED, still holding.** `TestCA65CompilationIntegration` — 9/9 pass with real `ca65`/`ld65`. |
| REG-02 (stale `.segment "HEADER"` e2e assertions) | #40 | **FIXED, still holding.** `verify_ca65_assembly` still export-mode-aware. |
| REG-03 (obsolete `@unittest.skip`'d classes) | #42 | **FIXED, still holding.** `grep -rn "@unittest.skip\|@pytest.mark.skip\|xfail" tests/*.py` (excluding `requires_cc65`/`skipif`) returns nothing — no unconditional skips anywhere in the suite. |
| REG-04 (`--arranger` zero coverage) | #44 | **FIXED for the scope it targeted** (role tagging, arpeggiation cadence, triangle no-duty, frames-contract parity). See **REG-12** below for a related gap the fix didn't cover. |
| REG-05 (exporter tests assert shape not bytes) | #45 | **FIXED for `test_ca65_export.py`/`test_midi_parser_integration.py`** (golden-bytes class). See **REG-14** below — the FamiStudio export path the original finding also named was never covered by the fix. |
| REG-06 (`ParallelPatternDetector` determinism/fallback) | #46 | **FIXED, still holding.** `tests/test_pattern_detector_parallel.py::TestParallelDeterminism::test_results_identical_across_worker_counts` passes; coverage now 78%. |
| REG-07 (no `test_mappers.py`) | #47 | **FIXED, still holding.** `tests/test_mappers.py` exists; `factory.py` 74%, `base.py` 59% (residual — see coverage map). |
| REG-08 (legacy multi-track allocation untested) | #48 | **FIXED, still holding.** `tests/test_track_mapper.py` covers both the multi-track heuristic (206-240) *and* the single-polyphonic-track split dispatch (191-203, exercised via `test_exporter_integration.py`/`test_midi_parser_integration.py`/`test_integration.py`) — confirmed with a combined coverage run, 88% on `tracker/track_mapper.py`. |
| REG-09 (`cc65_wrapper.py` error paths) | #49 | **FIXED, still holding.** `tests/test_cc65_wrapper.py`; 86% coverage. |
| **REG-10** (5 ROM-compile tests silently SKIP, stale fixture) | **#128, OPEN** | **Still open, unchanged.** Reproduced verbatim: `ssss..s` shape live — 5 skips at exactly `tests/test_rom_validation_integration.py:98,151,203,257,333`, all `"CC65 compilation failed"` / `"CC65 may not be installed"`, with `ca65`/`ld65` confirmed present at `/usr/bin`. Fixture still has bare `init_music:`/`update_music:` with no `.export`. Not re-reported in detail — see #128. |
| **REG-11** (e2e anchor masks failures) | **#129, OPEN** | **Still open, structurally unchanged.** `tests/test_e2e_pipeline.py:152-188` still wraps the run in `try/except Exception → pytest.skip`, still sets `args.skip_validation = True` (:169), still guards every assertion with `if rom_path.exists():` (:177). Currently **passing** (not skipping) because the default pipeline happens to work end-to-end today — but the mask is still there and would hide a real regression as a skip, not a failure. Not re-reported in detail — see #129. |

---

## 1. Coverage Map

| Subsystem | Source (cov%) | Test module(s) | Status |
|-----------|---------------|-----------------|--------|
| Track mapper (legacy) | `tracker/track_mapper.py` **88%** (both branches; 71% in isolation) | `test_track_mapper.py` + `test_exporter_integration.py`/`test_midi_parser_integration.py`/`test_integration.py` | OK |
| cc65 wrapper | `compiler/cc65_wrapper.py` **86%** | `test_cc65_wrapper.py` | OK |
| Patterns (parallel) | `tracker/pattern_detector_parallel.py` **78%** | `test_pattern_detector_parallel.py` | OK |
| Mappers | `factory.py` **74%**, `base.py` **59%**, `nrom.py` 95%, `mmc1.py` 85%, `mmc3.py` 79% | `test_mappers.py`, `test_nes_project_builder.py` | OK; `base.py`'s residual misses are its `@abstractmethod` stubs (untestable by design) + the `is_windows=True` build-script branch (correctly gated behind the `Windows-only test` skip) — not a real gap |
| Arranger | `gm_instruments.py` 97%, `voice_allocator.py` 90%, `pipeline_integration.py` 73%, `role_analyzer.py` **62%** | `test_arranger.py`, `test_arranger_drum_detection.py`, `test_arranger_frame_contract.py`, `test_voice_allocator.py` | Role/arpeggiation/contract behavior OK; **REG-12** (below) — channel-contention/drop logic specifically untested |
| Exporters | `exporter_ca65.py` (golden-bytes covered), `exporter_famistudio.py`, `exporter_nsf.py` (stub, `NotImplementedError` only) | `test_ca65_export.py`, `test_exporter_integration.py`, `test_famistudio_export.py`, `test_nsf_export.py` | CA65 path OK (golden bytes); **REG-14** (below) — FamiStudio path still shape-only |
| DPCM/drums | `enhanced_drum_mapper.py`, `dpcm_packer.py`, `dpcm_sample_manager.py`, `drum_engine.py` | `test_drum_*.py`, `test_dpcm_*.py`, `test_enhanced_drum_mapper.py` | OK; **REG-13** (below) — `test_drum_mapping.py` fixture/isolation hygiene |
| ROM-compile e2e | `test_rom_validation_integration.py`, `test_e2e_pipeline.py` | — | REG-10/REG-11 (existing, still open) |
| Debug overlay | `nes/debug_overlay.py` (dev-only, `--debug` flag) | none directly (indirectly via `test_nes_project_builder.py` string checks) | Unchanged since 06-28 report (~53% then); flagged there as an accepted LOW dev-only gap, not re-opened here |
| Orphaned utilities | `dpcm_sampler/dpcm_converter.py` (0 refs anywhere outside itself), `core/dto.py` (0 refs anywhere) | none | Not a coverage gap — these are unreferenced by the live pipeline (dead-code territory, `/audit-tech-debt`'s domain, not re-flagged here) |

---

## 2. New Findings

### REG-12: `RoleAnalyzer._assign_channels` (channel-contention fallback + track-drop logic) has zero test coverage
- **Severity**: MEDIUM
- **Dimension**: Untested subsystems (Dim 1) + round-trip/e2e gaps (Dim 3)
- **Location**: `arranger/role_analyzer.py:306-386` (`_assign_channels`, called from `create_arrangement_plan` at `:302`, itself called from the live `--arranger` path at `arranger/pipeline_integration.py:178`)
- **Status**: NEW (related to, but not covered by, the now-closed #44/REG-04)
- **Description**: This is the method that decides which MIDI track lands on which NES channel when
  multiple tracks compete for the same preferred channel — e.g. two melody-role tracks both wanting
  Pulse1 (one falls back to Pulse2 with an advisory note, `:339-343`), two harmony tracks wanting Pulse2
  (falls back to Pulse1, `:350-354`), `ANY_PULSE`/`FLEXIBLE` tracks filling whichever pulse channel is
  free (`:356-364`), and the final "try any available channel" fallback that can silently move a track to
  `plan.dropped_tracks` (`:366-386`) when NES has run out of channels. This is exactly the kind of
  allocation logic the severity doc flags as MEDIUM ("Suboptimal channel allocation in the arranger —
  playable but musically wrong voice dropped").
  `grep -rn "create_arrangement_plan\|_assign_channels\|dropped_tracks\|ArrangementPlan" tests/*.py`
  returns **zero matches** — no test calls `create_arrangement_plan()` directly, inspects
  `plan.dropped_tracks`, or constructs a MIDI input with enough competing tracks (e.g. 3+ melody-role
  tracks) to exercise the fallback branches. The existing arranger tests (`test_arranger.py`,
  `test_arranger_frame_contract.py`) all use 1-2 track inputs — never enough to force channel contention.
  `test_voice_allocator.py` tests a different, downstream concern (DPCM/noise routing inside
  `VoiceAllocator`), not this method.
- **Evidence**:
  ```
  $ grep -rln "create_arrangement_plan\|_assign_channels\|dropped_tracks\|ArrangementPlan" tests/*.py
  (no output)
  $ grep -c "def test_" tests/test_arranger.py tests/test_arranger_frame_contract.py
  tests/test_arranger.py:10
  tests/test_arranger_frame_contract.py:2
  ```
  `role_analyzer.py` coverage is 62% with the largest missed block at `:319-326,340-365,369-384` —
  the fallback/drop branches of `_assign_channels` plus the unrelated (and legitimately untested,
  print-only) `print_analysis`.
- **Impact**: A regression in the channel-contention logic (e.g. always dropping the second melody track
  instead of falling back to Pulse2, or dropping a bass track that should have gone to Triangle) would
  ship silently — the arranger would produce a playable ROM that is musically wrong (a voice missing)
  with no test catching it. This is the arranger's single largest untested decision point.
- **Related**: #44 (REG-04, closed) — fixed role-tagging/arpeggiation/contract but not this method; #88
  (ARR-05, open) — `get_role_priority()` dead code inconsistent with "the live drop order", which is
  this exact method's fallback order; a test here would also pin down what "the live drop order" is for
  that issue.
- **Suggested Fix**: Add `tests/test_arranger.py` (or a new `test_role_analyzer.py`) cases that build 3-4
  competing tracks (e.g. two high-pitch melody-role tracks, two low-pitch bass-role tracks, one drum
  track) through `RoleAnalyzer.create_arrangement_plan()` directly, and assert: (1) the second melody
  track lands in `plan.pulse2_tracks` with the expected advisory note, (2) a track that truly can't fit
  anywhere lands in `plan.dropped_tracks` with a note, not silently vanishes.

### REG-13: `tests/test_drum_mapping.py` depends on a gitignored, untracked repo-root fixture and leaks `invalid.json` into the repo root with no cleanup
- **Severity**: MEDIUM
- **Dimension**: Fixture & isolation hygiene (Dim 6) + stale/wrong-target (Dim 4)
- **Location**: `tests/test_drum_mapping.py:15` (`self.test_index_path = "test_dpcm_index.json"`), `:66-68` (`test_invalid_index_file` writes `"invalid.json"`)
- **Status**: NEW
- **Description**: Every other test file that needs a DPCM index fixture points at the checked-in
  `tests/fixtures/test_dpcm_index.json` (`test_track_mapper.py:161,205`, `test_integration.py:54,101`,
  `test_enhanced_drum_mapper.py:36,57,85`). `test_drum_mapping.py` alone uses the bare relative path
  `"test_dpcm_index.json"`, which resolves against the process CWD — i.e. the **repo root** when tests
  are run the documented way (`python -m pytest` from the repo root). That root-level file is **not
  tracked by git** (`git ls-files | grep -x test_dpcm_index.json` → no match) and is explicitly excluded
  by `.gitignore:29` (`/*.json`). It currently exists on this machine only as stray, untracked cruft
  (dated Sep 30 2025 — clearly a leftover from a prior manual run, not a fixture anyone maintains).
  Separately, `test_invalid_index_file` (`:66-68`) does `open("invalid.json", "w")` — also a bare
  relative path into the repo root — with **no `tearDown`/cleanup**; it also matches the `.gitignore`
  `/*.json` pattern, so `git status` never surfaces it, but it persists on disk after every test run
  (confirmed: a fresh `invalid.json` was created in the repo root, timestamped to this exact test run,
  while auditing).
- **Evidence**:
  ```
  $ git ls-files tests/fixtures/ | grep dpcm
  tests/fixtures/test_dpcm_index.json
  $ git ls-files | grep -x "test_dpcm_index.json"
  (no output)                                  # not tracked at repo root
  $ git check-ignore -v test_dpcm_index.json invalid.json
  .gitignore:29:/*.json  test_dpcm_index.json
  .gitignore:29:/*.json  invalid.json
  $ ls -la test_dpcm_index.json invalid.json
  -rwxr-xr-x 1 matias matias 449 Sep 30  2025 test_dpcm_index.json
  -rwxr-xr-x 1 matias matias  12 Jul  3 13:47 invalid.json   # created during this audit's test runs
  ```
- **Impact**: On a fresh `git clone` (or any CI environment without that untracked leftover file —
  this repo has no `.github/` CI config today, so it has never been caught), every test in
  `TestDrumMapping` that reads `self.test_index_path` (`test_velocity_ranges`,
  `test_sample_id_is_index_id_not_allocation_order`, `test_invalid_index_file`, `test_noise_fallback`)
  would raise `FileNotFoundError` — a confusing false failure with no relation to an actual code
  regression, in a file whose entire purpose is regression-guarding drum-sample-id mapping (`#65`).
  Independently, the no-cleanup `invalid.json` write litters the working tree on every local run.
- **Suggested Fix**: Point `self.test_index_path` at `"tests/fixtures/test_dpcm_index.json"` like the
  other three test files do. Write `invalid.json` via `tempfile.TemporaryDirectory()` (or the shared
  `temp_dir`/`tmp_path` fixture) with automatic cleanup instead of a bare relative path.

### REG-14: FamiStudio export tests are still shape-only (`assertIn("PATTERNS", ...)`) — the golden-bytes fix for #45/REG-05 only covers the CA65 path
- **Severity**: MEDIUM
- **Dimension**: Weak assertions (Dim 2)
- **Location**: `tests/test_famistudio_export.py:49-70` (`test_generate_famistudio_txt`), `tests/test_exporter_integration.py:108-121` (`test_famistudio_export_with_compression`)
- **Status**: Regression of #45 (partial fix — the closed issue's own evidence explicitly named this exact
  test/assertion, `test_famistudio_export_with_compression` asserting only `assertIn("PATTERNS", content)`,
  and it is still true verbatim today; only the CA65/`test_midi_parser_integration.py` half of the original
  finding was addressed)
- **Description**: `TestCA65GoldenBytes` (added for #45) pins exact `.byte` streams for the CA65
  macro-bytecode path, but the FamiStudio exporter — a separate, real export format
  (`exporter/exporter_famistudio.py`) — still has no equivalent. `test_generate_famistudio_txt` checks
  section-presence strings (`"PROJECT"`, `"INSTRUMENTS"`, `"PATTERNS"`) plus a few `assertIn("C-4 15", ...)`
  style substring checks; `test_famistudio_export_with_compression`
  (`tests/test_exporter_integration.py:119-121`) checks only `assertIn("PATTERNS", content)` and one note
  string. Neither test would catch a wrong note-name/octave conversion for any note not explicitly checked,
  a pattern emitted under the wrong track/frame, or note data silently dropped from the output — the tests
  would still pass on a FamiStudio export that describes different music than the input.
- **Evidence**:
  ```
  $ grep -n 'assertIn(.PATTERNS.' tests/test_famistudio_export.py tests/test_exporter_integration.py
  tests/test_famistudio_export.py:61:        self.assertIn("PATTERNS", output)
  tests/test_exporter_integration.py:121:            self.assertIn("PATTERNS", content)
  $ grep -n "class Test" tests/test_famistudio_export.py tests/test_exporter_integration.py
  tests/test_famistudio_export.py:8:class TestFamiStudioExport(unittest.TestCase):
  tests/test_exporter_integration.py:16:class TestExporterIntegration(unittest.TestCase):
  tests/test_exporter_integration.py:125:class TestCA65GoldenBytes(unittest.TestCase):   # CA65 only
  ```
  No `TestFamiStudioGoldenBytes`-equivalent class exists.
- **Impact**: FamiStudio export is a secondary/external-tracker format (not wired into the default ROM
  pipeline), so blast radius is contained to users who explicitly export to FamiStudio — same contained
  scope the 2026-06-29 EXP audit assigned FamiTracker/FamiStudio bugs. Still, this is the same failure
  class the closed #45 exists to prevent, left open on a sibling path (the closed issue's own cited
  evidence line named this exact assertion verbatim).
- **Related**: #45 (REG-05, closed — partial fix); `docs/audits/AUDIT_EXPORTERS_2026-06-29.md`'s
  FamiStudio/FamiTracker octave findings (same file, different bug class).
- **Suggested Fix**: Add a `TestFamiStudioGoldenBytes`-style case: run a small crafted `frames` dict (or
  `test_midi/simple_loop.mid` through the real pipeline) through `generate_famistudio_txt`, and assert the
  exact emitted pattern-row text for every note (not a subset), not just structural markers.

---

## 3. Prioritized Backlog

| Rank | Finding | Action | Why |
|------|---------|--------|-----|
| 1 | **REG-10** (Existing #128) | Fix the stale `music.asm` export fixture; convert `except → skip` to a real `cc65`-presence gate | The "CRITICAL STEP" ROM-byte gate is still silently disabled — 5/9 tests provide zero coverage every run |
| 2 | **REG-12** (NEW) | `RoleAnalyzer._assign_channels` contention/drop tests | Arranger's single largest untested decision point; MEDIUM voice-drop blast radius |
| 3 | **REG-14** (NEW / partial #45) | FamiStudio golden-bytes test | Same failure class as the closed #45, left open on a sibling export path |
| 4 | **REG-13** (NEW) | Fix `test_drum_mapping.py`'s fixture path + `invalid.json` cleanup | Silent false-failure risk on any fresh clone/CI (repo currently has none); repo-root litter |
| 5 | **REG-11** (Existing #129) | De-mask the e2e anchor | Can't go red on a broken pipeline; still structurally present even though currently green |

**Top NEW test to write first**: REG-12 (`RoleAnalyzer._assign_channels` contention tests) — it guards the
arranger's core allocation decision (which voice gets dropped when channels run out), the one arranger
behavior the #44 fix wave didn't reach, and directly informs the still-open #88 (ARR-05) about what "the
live drop order" actually is.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-07-03.md
```
