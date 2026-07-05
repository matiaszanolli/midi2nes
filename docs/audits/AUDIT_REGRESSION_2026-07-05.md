# Regression / Test-Hygiene Audit — MIDI2NES

- **Date**: 2026-07-05
- **Scope**: The test suite itself (`tests/`) — coverage gaps, weak assertions, round-trip/e2e gaps,
  stale/wrong-target tests, determinism/flakiness, fixture hygiene. Delta audit over
  `AUDIT_REGRESSION_2026-07-03.md` (and the `-06-28` / `-06-29` baselines).
- **Skill**: `/audit-regression`
- **Suite state at audit time**: **894 passed, 6 skipped** (`python -m pytest -q`, 227s). `ca65`/`ld65`
  both present at `/usr/bin`. Test count grew from 783 → 900 collected (894 run) since 07-03 — every one of
  the ~50 fixes that landed in the interim (issues #80/#83, #89/#90, #116-119, #168/#169, #170/#171/#179,
  #176-178, #195-197, #200/#201, #205-207, #208-211, #212/#213, #214, #215-217, #218/#219, #220/#221) shipped
  with accompanying tests. 5 of the 6 skips are the still-open REG-10 (`test_rom_validation_integration.py`,
  `ssss..s` shape reproduced verbatim); the 6th is the legitimate `Windows-only test` skip
  (`test_nes_project_builder.py:358`). Suite is green.
- **Dedup basis**: pre-fetched `/tmp/audit/issues.json` (36 issues; **verified MIDI2NES** — contains the
  `REG-`/`PAT-`/`NH-`/`TD-`/`SAFE-`/`D-` prefixes matching this repo's audit scheme, including this audit's
  own prior findings REG-10 → REG-14 as issues #128/#129/#230/#231/#232). Prior reports scanned:
  `AUDIT_REGRESSION_2026-07-03.md`, `AUDIT_REGRESSION_2026-06-29.md`, `AUDIT_REGRESSION_2026-06-28.md`.

> **Headline**: **Zero NEW findings.** This is a mature, well-maintained test suite. All five open
> regression findings from the 07-03 audit were re-verified as still valid and are already tracked as
> open GitHub issues (#128, #129, #230, #231, #232). No new coverage gap, weak assertion, stale test,
> flaky test, or fixture-hygiene defect was found that is not already tracked. The interim 50-fix sprint
> introduced no new unconditional skips, no new repo-root write leaks, and no coverage regressions on the
> high-blast-radius paths.

## Status of prior regression findings (re-verified this run)

| Prior | Issue | Verdict now (2026-07-05) |
|-------|-------|--------------------------|
| REG-01 (CA65 compile gate RED) | #39 | **FIXED, holding.** `TestCA65CompilationIntegration` — **9/9 pass** with real `ca65`/`ld65`. |
| REG-02 (stale `.segment "HEADER"` e2e assertions) | #40 | **FIXED, holding.** `verify_ca65_assembly` still export-mode-aware. |
| REG-03 (obsolete `@unittest.skip`'d classes) | #42 | **FIXED, holding.** No unconditional `@unittest.skip`/`@pytest.mark.skip`/`xfail` anywhere; all remaining `pytest.skip` calls are conditional (cc65-presence, OS, or optional-file gates). |
| REG-04 (`--arranger` zero coverage) | #44 | **FIXED for its scope.** See **REG-12/#230** for the residual contention-branch gap (partially narrowed this sprint). |
| REG-05 (exporter tests assert shape not bytes) | #45 | **FIXED for CA65, holding.** `TestCA65GoldenBytes` (`test_exporter_integration.py:125`) still pins exact `pulse1_sequence` / `ntsc_period_low` bytes — **survives** the interim exporter changes (#83, #215). FamiStudio half still open (**REG-14/#232**). |
| REG-06 (`ParallelPatternDetector` determinism/fallback) | #46 | **FIXED, holding.** `test_pattern_detector_parallel.py` 6/6 pass; determinism across `max_workers=1/2/4` held after the #218/#219 worker-cap + sampling-cap changes. |
| REG-07 (no `test_mappers.py`) | #47 | **FIXED, holding.** |
| REG-08 (legacy multi-track allocation untested) | #48 | **FIXED, holding.** |
| REG-09 (`cc65_wrapper.py` error paths) | #49 | **FIXED, holding.** |
| **REG-10** (5 ROM-compile tests silently SKIP, stale `music.asm` fixture) | **#128, OPEN** | **Still open, unchanged.** Reproduced verbatim: 5 skips at `test_rom_validation_integration.py:98,151,203,257,333`, all via the `except Exception → pytest.skip("CC65 may not be installed")` handler, with `ca65`/`ld65` confirmed present. Root cause unchanged (fixture defines `init_music:`/`update_music:` with no `.export`). Not re-reported — see #128. |
| **REG-11** (e2e anchor masks failures; no arranger/no-patterns real compile) | **#129, OPEN** | **Still open, structurally unchanged.** `test_e2e_pipeline.py` still sets `args.skip_validation = True`, still guards every assert with `if rom_path.exists():`, still wraps the run in `except Exception → pytest.skip`. Confirmed **no `--arranger` and no `--no-patterns` reference** drives a real `ca65`/`ld65` compile anywhere in `test_e2e_pipeline.py` (only `args.no_patterns = False`). Not re-reported — see #129. |
| **REG-12** (`RoleAnalyzer._assign_channels` contention/drop untested) | **#230, OPEN** | **Still open, partially narrowed.** The #207 fix added `test_second_drum_track_recorded_as_dropped_not_silently_lost` (drum-drop branch now covered), lifting `role_analyzer.py` from 62% → **70%**. But the **pulse-contention fallback branches remain uncovered** — coverage `--cov-report=term-missing` still shows misses at `339-364, 368-383` (two melody→Pulse2 fallback, two harmony→Pulse1 fallback, ANY_PULSE fill, and the final drop-to-`dropped_tracks` for tone tracks). No test still builds 3+ competing *melodic* tracks. Not re-reported — see #230. |
| **REG-13** (`test_drum_mapping.py` bare-relative fixture + `invalid.json` leak) | **#231, OPEN** | **Still open, verbatim.** `self.test_index_path = "test_dpcm_index.json"` (`:15`, bare relative → repo root, untracked/gitignored), read at `:44`; `open("invalid.json", "w")` at `:67` with no cleanup. Confirmed a fresh `invalid.json` was **re-created in the repo root during this audit's own test run** (timestamped 2026-07-05 14:51). Not re-reported — see #231. |
| **REG-14** (FamiStudio export tests shape-only) | **#232, OPEN** | **Still open, verbatim.** `assertIn("PATTERNS", …)` at `test_famistudio_export.py:61` and `test_exporter_integration.py:121`; no `TestFamiStudioGoldenBytes` equivalent. Not re-reported — see #232. |

---

## 1. Coverage Map (delta vs 07-03)

| Subsystem | Source (cov%) | Test module(s) | Status |
|-----------|---------------|-----------------|--------|
| Track mapper (legacy) | `tracker/track_mapper.py` ~88% | `test_track_mapper.py` (+ integration) | OK |
| cc65 wrapper | `compiler/cc65_wrapper.py` 86% | `test_cc65_wrapper.py` | OK |
| Patterns (parallel) | `tracker/pattern_detector_parallel.py` 78% | `test_pattern_detector_parallel.py` | OK; determinism held after #218/#219 worker-cap change |
| Pattern caps / sampling (#219) | `main.py:get_pattern_detection_caps`, `ParallelPatternDetector.max_pattern_events` | `test_patterns.py:992-1029`, `test_main.py:1280-1302` | OK — default + config-override + `was_sampled` branch all pinned |
| Pattern positions / coverage_ratio (#168/#169/#170/#171) | `tracker/pattern_detector.py:831-863`, `_find_pattern_matches` | `test_patterns.py:157-167,1220-1248`, `test_main_pipeline.py` | OK — anchor-non-overlap + coverage_ratio-vs-song all asserted |
| Mappers + `--mapper` flag (#217) | `factory.py` 74%, `base.py` 59%, nrom/mmc1/mmc3 | `test_mappers.py`, `test_main.py` (`resolve_mapper`, 11 refs) | OK |
| Mapper-capacity gate (#23/#28/#178) | `main.py` capacity/validation gates | `test_main_pipeline.py:920-1076` (bad-vectors, no-APU-init, overflow, bad-ROM removal) | OK — behavior-specific, not shape-only |
| Compiler post-process (#214) | `compiler/compiler.py` | `test_main_pipeline.py:184-259` | OK |
| Arranger | `gm_instruments.py` 97%, `voice_allocator.py` 90%, `pipeline_integration.py`, `role_analyzer.py` **70%** (↑ from 62%) | `test_arranger*.py`, `test_voice_allocator.py` | Role/arpeggio/drum-drop OK; **REG-12/#230** — pulse-contention branches still uncovered |
| Arranger pitch (#89/#90) | `arranger/pipeline_integration.py` (delegates to canonical tables) | `test_arranger.py` | OK |
| Exporters (CA65) | `exporter_ca65.py` golden-bytes covered; single-byte-operand guard (#83) | `test_exporter_integration.py:125` (`TestCA65GoldenBytes` — **2/2 pass**), `test_ca65_export.py` | OK |
| Exporters (FamiStudio) | `exporter_famistudio.py` | `test_famistudio_export.py`, `test_exporter_integration.py` | **REG-14/#232** — shape-only |
| Compression round-trip | `exporter/compression.py` (`decompress_pattern`) | `test_compression.py` (compress→decompress→`assertEqual` original) | OK |
| Song bank / parser reopen guard (#220/#221) | `nes/song_bank.py`, `tracker/parser_fast.py` | `test_song_bank.py`, `test_parser_fast.py`, `test_main.py` | OK |
| Tempo (#208-211) | `tracker/tempo_map.py` | `test_tempo_map.py` | OK |
| DPCM/drums | `enhanced_drum_mapper.py`, `dpcm_*` | `test_dpcm_*.py`, `test_drum_*.py`, `test_enhanced_drum_mapper.py` | OK; **REG-13/#231** — `test_drum_mapping.py` fixture hygiene |
| ROM-compile e2e | — | `test_rom_validation_integration.py`, `test_e2e_pipeline.py` | **REG-10/#128 + REG-11/#129** (open) |

---

## 2. Findings

**No NEW findings this run.** Every test-hygiene defect observed is already an open GitHub issue and was
re-verified above (dedup protocol: OPEN → "Existing: #NNN" and skip re-reporting in detail):

| ID | Severity | Dimension | Status | One-line |
|----|----------|-----------|--------|----------|
| REG-10 | MEDIUM | Round-trip/e2e (Dim 3), Fixture (Dim 6) | Existing: #128 | 5 ROM-compile tests silently SKIP via `except→skip` masking a broken `music.asm` fixture (no `.export`). |
| REG-11 | LOW | Round-trip/e2e (Dim 3) | Existing: #129 | e2e anchor can only pass/skip, never fail on a broken pipeline; no arranger/no-patterns real compile. |
| REG-12 | MEDIUM | Untested subsystem (Dim 1) | Existing: #230 | `role_analyzer._assign_channels` pulse-contention/drop branches (`:339-383`) still uncovered (drum-drop now covered). |
| REG-13 | MEDIUM | Fixture hygiene (Dim 6), Stale (Dim 4) | Existing: #231 | `test_drum_mapping.py` reads a bare-relative untracked repo-root fixture and leaks `invalid.json` (no cleanup). |
| REG-14 | MEDIUM | Weak assertions (Dim 2) | Existing: #232 | FamiStudio export tested only with `assertIn("PATTERNS", …)`; no golden-bytes equivalent. |

Negative results worth recording (checked, found clean — do not re-investigate next run):
- **Dim 5 (determinism)**: the #218/#219 worker-cap/sampling-cap change did not reintroduce non-determinism —
  `test_pattern_detector_parallel.py` worker-invariance test still passes.
- **Dim 4 (stale)**: the interim exporter changes (#83 operand guard, #215 OAM-segment removal) did **not**
  stale the golden-bytes assertions — `TestCA65GoldenBytes` still passes with exact byte pins.
- **Dim 6 (leaks)**: a repo-wide scan for bare-relative `open(…, 'w')` in `tests/` found **only** the known
  REG-13 `invalid.json` — no new repo-root write leaks from the 50-fix sprint.
- **Dim 3 (round-trip)**: compression `compress_pattern → decompress_pattern → assertEqual(original)` is
  covered in `test_compression.py`; the #168/#169 coverage_ratio and #170/#171 anchor-non-overlap fixes both
  shipped value-asserting regression tests.

---

## 3. Prioritized Backlog

Unchanged from 07-03 — all items are already-filed open issues; ordered by blast radius:

| Rank | Finding | Issue | Action | Why |
|------|---------|-------|--------|-----|
| 1 | REG-10 | #128 | Fix the stale `music.asm` fixture (`.export init_music, update_music`); convert `except→skip` to a real cc65-presence gate | The ROM-byte gate is still silently disabled — 5/9 tests give zero coverage every run while reporting green-ish |
| 2 | REG-12 | #230 | Add a `create_arrangement_plan()` test with 3+ competing **melodic** tracks; assert Pulse2 fallback + `dropped_tracks` | Arranger's largest still-uncovered decision point (`:339-383`); drum-drop is done, tone-contention isn't |
| 3 | REG-14 | #232 | Add `TestFamiStudioGoldenBytes` pinning exact pattern-row text | Same failure class as closed #45, left open on the FamiStudio path |
| 4 | REG-13 | #231 | Point `test_index_path` at `tests/fixtures/test_dpcm_index.json`; write `invalid.json` under `tmp_path` | Silent false-failure on fresh clone/CI; repo-root litter (re-confirmed created today) |
| 5 | REG-11 | #129 | De-mask the e2e anchor; add a real `--arranger` and `--no-patterns` compile | Cannot go red on a broken pipeline; still structurally present |

**Top item**: REG-10 (#128) — the designated "compile a real ROM and validate its bytes" gate remains the
single most valuable test to repair; it is disabled today by nothing more than a stale hand-written fixture.

---

Suggested next step (no new issues to file — all findings already tracked; publish would be a no-op):
```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-07-05.md
```
