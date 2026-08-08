# Regression / Test-Hygiene Audit — 2026-08-07

Scope: full test-suite health sweep per `.claude/commands/audit-regression/SKILL.md`,
with explicit focused scrutiny (per task brief) on the newly-merged `song build`
subcommand (song bank → multi-song "jukebox" ROM, #30/F-13, commit `c864426`) and its
new test coverage: `tests/test_song_bank.py`, `tests/test_ca65_export.py`
(`TestExportSongBankBytecode`, `TestJukeboxCompilationIntegration`),
`tests/test_nes_project_builder.py` (`TestJukeboxSongCount`), `tests/test_main.py`
(`TestRunSongBuild`).

All findings below were reproduced against live code, not inferred from prose — two of
them (REG-27, REG-28) were independently confirmed with real `ca65`/`ld65` builds
(toolchain present in this environment: `/usr/bin/ca65`, `/usr/bin/ld65`).

## Coverage map

| Subsystem | Test module(s) | Coverage (this run / prior confirmed) |
|---|---|---|
| `nes/song_bank.py` (NEW) | `tests/test_song_bank.py` | 91% (misses: `debug_size_info` helper, one `import_bank` defensive branch, `get_bank_data`/`get_bank_size` trivial getters) |
| `exporter/exporter_ca65.py::export_song_bank_bytecode` (NEW) | `tests/test_ca65_export.py::TestExportSongBankBytecode` (unit), `::TestJukeboxCompilationIntegration` (real-compile) | Symbol prefixing, shared period tables, fresh-bank-per-song, song_table sizing, clamp totalling all unit-tested with real assertions (not weak). **Segment placement of per-song instrument/macro tables is untested** — see REG-28. |
| `nes/project_builder.py::prepare_project(song_count=...)` (NEW param) | `tests/test_nes_project_builder.py::TestJukeboxSongCount` | 80-81% on the jukebox-specific test slice; `JUKEBOX_BUILD` gating (`song_count>1`) and Start-skip polling both asserted against a **hand-written stub** `music.asm`, never against real `export_song_bank_bytecode` output or a real compile. |
| `main.py::run_song_build` / `midi_to_frames_for_song` / `_song_has_dpcm_events` (NEW) | `tests/test_main.py::TestRunSongBuild` | Bank loading, ordering-by-`metadata['order']`, missing-file/empty-bank/missing-midi-path/DPCM-rejection/missing-dpcm-index error paths all covered with real (unmocked) parsing. **Every real-compile branch is mocked out** — `NESProjectBuilder`, `compile_rom`, `validate_rom` are `@patch`'d to succeed in all but the argument-validation tests — see REG-29. |
| `tracker/track_mapper.py` | `tests/test_track_mapper.py` | 71% (REG-08/#48, previously fixed) — reverified, holds |
| `tracker/pattern_detector_parallel.py` | `tests/test_pattern_detector_parallel.py` | 78%, determinism tie-break intact (REG-06/#46) — reverified: 12/12 pass, deterministic |
| `mappers/factory.py` / `mappers/base.py` | `tests/test_mappers.py` | 77% / 75% (REG-07/#47) — reverified, holds; residual gap is abstract-method stubs + capacity edge cases (already known, not re-flagged) |
| `compiler/cc65_wrapper.py` | `tests/test_cc65_wrapper.py` | 86% (REG-09/#49) — reverified, holds |
| `nes/emulator_core.py` | `tests/test_frame_validation.py`, `tests/test_integration.py` | 70%, no regression from baseline |
| `nes/pitch_table.py` | `tests/test_pitch_tables.py`, `tests/test_pitch_table_integration.py` | 96% |
| `nes/envelope_processor.py` | `tests/test_envelope.py`, `tests/test_envelope_integration.py` | 95% |
| `arranger/*` | `tests/test_arranger*.py`, `tests/test_voice_allocator.py`, `tests/test_role_analyzer.py` | 81-98% (REG-04/#44) — no regression observed |
| `tests/test_ca65_export.py::TestCA65CompilationIntegration` / `::TestJukeboxCompilationIntegration` | — | Both classes carry `@pytest.mark.requires_cc65` (REG-26/#414, closed) — reverified: 9/9 and 2/2 pass with the toolchain present, no skip-masking |
| `tests/test_rom_validation_integration.py`, `tests/test_e2e_pipeline.py` | — | 23/23 and 12/12 pass unconditionally (REG-10/REG-11/#128/#129) — reverified, holds |

No subsystem in `_audit-common.md`'s project layout is without a test module.

## Findings

### REG-27: No real-compile test for a one-song jukebox build — the shipped test suite cannot catch that `song build` unconditionally fails to link with exactly one song
- **Severity**: HIGH
- **Dimension**: 3 (round-trip / end-to-end gaps) + 1 (untested subsystem edge case)
- **Location**: `tests/test_ca65_export.py:1157-1177` (`TestJukeboxCompilationIntegration::test_single_song_still_compiles_after_jukebox_changes`); root cause `exporter/exporter_ca65.py:1641-1654` (`export_song_bank_bytecode` unconditionally emits `.import audio_init_song, audio_update` / `jmp audio_init_song`) vs. `nes/project_builder.py:307-315` (`JUKEBOX_BUILD = 1` only assigned `if song_count and song_count > 1`) vs. `nes/audio_engine.asm:246-250` (`audio_init_song`/`audio_advance_song` only `.export`ed `.ifdef JUKEBOX_BUILD`)
- **Status**: NEW
- **Description**: `main.py:run_song_build` (the real `song build` CLI entry point) calls `CA65Exporter.export_song_bank_bytecode` **unconditionally for any bank size, including one song** (`main.py:998`, no `len(songs) == 1` special case), and that method always writes symbols under the `song{i}_` prefix scheme with a `jmp audio_init_song` init stub — it has no separate "1-song" output mode. But `NESProjectBuilder.prepare_project` only defines the `JUKEBOX_BUILD` ca65 symbol (which gates `nes/audio_engine.asm`'s jukebox routines, including `audio_init_song` itself, into the assembly at all) when `song_count > 1`. The one-song case therefore always produces a music.asm that references `audio_init_song` and the bank-bytecode engine's `song{i}_`-prefixed symbols, while the included `audio_engine.asm` — never told `JUKEBOX_BUILD` — expects the *old* unprefixed single-song symbol set (`pulse1_sequence`, `instrument_table`, `channel_start_banks`, …) and never defines `audio_init_song` at all.
  The class the task brief flagged for scrutiny, `TestJukeboxCompilationIntegration`, has exactly two tests: a 2-song real-compile test (see REG-28) and `test_single_song_still_compiles_after_jukebox_changes` — but that second test does **not** exercise the actual bug-triggering path. It calls the *ordinary* single-song exporter `export_tables_with_patterns` (not `export_song_bank_bytecode`) and never passes `song_count` to `prepare_project` at all, i.e. it tests the pre-existing, unaffected single-song pipeline, not what `run_song_build` actually does for a 1-song bank. No test anywhere in the suite builds a real 1-song bank through `export_song_bank_bytecode` + `prepare_project(song_count=1)` + a real `compile_rom`.
- **Evidence**: Live reproduction (`python main.py song add song1.mid --bank bank1.json` then `python main.py song build bank1.json out1.nes --arranger -v`) with the CC65 toolchain present:
  ```
  [ERROR] Failed to link ROM: ...
  Unresolved external 'audio_init_song' referenced in:
    .../music.asm(170)
  Unresolved external 'channel_start_banks' referenced in:
    .../audio_engine.asm(155,162,169,176,183)
  Unresolved external 'dpcm_sequence' referenced in: ...
  Unresolved external 'instrument_table' referenced in: ...
  Unresolved external 'noise_sequence' referenced in: ...
  Unresolved external 'pulse1_sequence' referenced in: ...
  Unresolved external 'pulse2_sequence' referenced in: ...
  Unresolved external 'triangle_sequence' referenced in: ...
  ld65: Error: 8 unresolved external(s) found - cannot create output file
  [ERROR] Compilation failed
  ```
  This is a documented v1-scope-supported case — the CLI accepts a bank with any number of songs ≥ 1 (`main.py:947-949` only rejects an *empty* bank), and `docs/ROADMAP.md`/the feature's own docstrings describe no minimum-song-count restriction.
- **Impact**: `song build` on the smallest, most basic possible bank (one song) — arguably the first thing any user of this brand-new feature would try — fails 100% of the time with a cryptic linker error, not a clear `[ERROR]` message from `run_song_build`'s own guard rails. CRITICAL-class production defect (unbuildable ROM, no workaround short of adding a second dummy song); this finding is about the test-suite gap that let it ship undetected, hence HIGH rather than CRITICAL for the finding itself.
- **Related**: REG-28 (same feature, sibling gap); #30/F-13 (the feature this regressed); REG-26/#414 (precedent for `@pytest.mark.requires_cc65` gating on this exact test class, already correctly applied here — the gate is fine, the test just targets the wrong code path).
- **Suggested Fix**: Add a `requires_cc65`-gated test to `TestJukeboxCompilationIntegration` that calls `export_song_bank_bytecode([_song_frames(60)], ...)` (a **1-element** list, matching what `run_song_build` actually produces for a 1-song bank) followed by `prepare_project(str(music_asm), song_count=1)` and a real `compile_rom`, asserting the link succeeds. Given the bug, the fix will also need to either (a) special-case `run_song_build`/`export_song_bank_bytecode` to fall back to the ordinary single-song export path when `len(songs) == 1`, or (b) make `JUKEBOX_BUILD` gating in `project_builder.py`/`audio_engine.asm` trigger whenever `is_bytecode` content came from `export_song_bank_bytecode` (e.g. a marker string) rather than `song_count > 1`.

### REG-28: `TestJukeboxCompilationIntegration`'s 2-song real-compile test never checks that each song's symbols land in the correct segment — songs after the first silently corrupt into the wrong (dynamically-banked) memory region
- **Severity**: HIGH
- **Dimension**: 2 (weak assertions) + 3 (round-trip / end-to-end gaps)
- **Location**: `tests/test_ca65_export.py:1131-1155` (`test_two_song_jukebox_rom_compiles_and_passes_diagnostics`); root cause `exporter/exporter_ca65.py:1575` (`.segment "CODE_8000"` set once, before the per-song loop) vs. `:1594-1606` (the `for prefix, song in zip(song_labels, songs):` loop calls `_build_song_bytecode` again for song 1..N-1 with **no segment reset**, while `_build_song_bytecode` itself always ends by switching to a `.segment "BANK_NN"` dynamically-banked segment for its sequence bytecode, at `:1343` and later re-emissions on bank overflow)
- **Status**: NEW
- **Description**: `export_song_bank_bytecode` sets `.segment "CODE_8000"` exactly once, before the song loop, intending every song's `instrument_table`/macro tables to land in that fixed, always-mapped segment (as the single-song exporter does, and as the docstring at `:1547-1554` describes: "Distinct songs keep separate instrument/macro tables… `song_instrument_ptr_lo/hi` … a way to look up any song's channel entry points"). But `_build_song_bytecode` (called once per song inside the loop) unconditionally ends its own output in a `.segment "BANK_NN"` directive for that song's sequence bytecode, and the loop never re-emits `.segment "CODE_8000"` before calling `_build_song_bytecode` for the *next* song. So only **song 0** gets its `instrument_table`/macro tables placed in `CODE_8000` (because the segment is still `CODE_8000` from before the loop). Every song from index 1 onward has its `instrument_table:`/macro labels emitted while the segment ca65 is currently tracking is whatever `BANK_NN` the *previous* song's sequence data ended in — a segment that is only physically mapped into the CPU's address space when that specific bank is bank-switched in. `song_instrument_ptr_lo/hi` (the runtime lookup table `EVAL_MACRO` indirects through, per the docstring) stores only an address, no bank number — unlike `song_table_bank` for sequence data — so there is no mechanism to bank-switch to the correct physical bank before dereferencing a wrongly-placed instrument table. This silently corrupts playback (wrong or garbage macro/instrument data) for every song after the first in any jukebox ROM with 2+ songs, without any linker or runtime error.
  The task brief's flagged test, `test_two_song_jukebox_rom_compiles_and_passes_diagnostics`, only asserts: the ROM compiles/links (`assertTrue(success, ...)`), `ROMDiagnostics.overall_health` is HEALTHY/GOOD/FAIR, `reset_vectors_valid`, `apu_pattern_count > 0`, and that `main.asm` contains the `JUKEBOX_BUILD`/`audio_advance_song` strings — all structural/boot-level checks. None of them can detect a wrong `.segment` for a data label; ld65 has no issue with `song1_instrument_table` sitting in `BANK_00` (it's a valid, well-formed segment), and the ROM boots fine on song 0 before this corruption is ever reached.
- **Evidence**: Live reproduction, inspecting the real exporter output's active `.segment` directive at the point each song's `instrument_table:` label is emitted:
  ```
  song0_instrument_table:  -->  active segment: .segment "CODE_8000"   (asm line 100)
  song1_instrument_table:  -->  active segment: .segment "BANK_00"     (asm line 158)
  ```
  `song0` (the only song `test_two_song_jukebox_rom_compiles_and_passes_diagnostics` implicitly validates via ROM-boot diagnostics) is correctly placed; `song1` — and by the same code path, every subsequent song in a larger bank — is not. The 2-song ROM in this repro (`out2.nes`) still links and boots (matching the test's actual assertions), consistent with the bug being invisible to link-time and boot-time checks.
- **Impact**: Any jukebox ROM with 2+ songs plays song 0 correctly but has corrupted instrument/macro data for every subsequent song — most likely silent/wrong notes or a hang if `EVAL_MACRO` dereferences into unmapped/unrelated bank data, depending on what happens to be bank-switched in at the moment the player advances to song 1. This is exactly the CRITICAL-class "pipeline stage emits data a downstream stage parses as valid but means something else" failure mode per `_audit-severity.md` — undetectable by the current test's structural-only assertions.
- **Related**: REG-27 (same feature, sibling gap); `_audit-severity.md` "NES-hardware rows" floor (byte-emission-boundary bugs are HIGH/CRITICAL on the code, and this finding — the missing test — is rated HIGH given it's the only test in the suite positioned to catch a currently-shipping corruption bug).
- **Suggested Fix**: Two independent actions. (1) Test: in `TestExportSongBankBytecode` (or a new test), parse the generated `.asm` text and assert that `song{i}_instrument_table:` for every `i` appears immediately after a `.segment "CODE_8000"` directive (matching the pattern already exploited by `test_each_song_starts_a_fresh_bank`'s segment-tracking regex at `tests/test_ca65_export.py:676-690`) — this alone would have caught the bug without needing a real compile. (2) Code: in `export_song_bank_bytecode`'s per-song loop (`exporter/exporter_ca65.py:1597-1606`), emit `lines.append('.segment "CODE_8000"')` immediately before each call to `_build_song_bytecode` (matching what the single-song caller at `:1483` already does).

### REG-29: `run_song_build`'s own real-compile failure branches (mapper-capacity, link failure, ROM-validation failure) have zero test coverage — the CLI-level error path that REG-27's bug exercises in production is itself untested
- **Severity**: MEDIUM
- **Dimension**: 1 (untested subsystem) + 3 (round-trip / end-to-end gaps)
- **Location**: `main.py:999-1001` (`export_song_bank_bytecode` `ValueError` branch), `:1008-1010` (`check_mapper_capacity` `ValueError` branch), `:1018-1020` (`compile_rom` failure branch), `:1023-1025` (`validate_rom` failure branch); measured via `pytest tests/test_main.py -k RunSongBuild --cov=main --cov-report=term-missing`
- **Status**: NEW
- **Description**: Every `TestRunSongBuild` test that reaches the compile stage `@patch`es `main.NESProjectBuilder`, `main.compile_rom`, and `main.validate_rom` — always configured to succeed (`mock_compile.return_value = True`, etc.) except for one `MapperFactory`/`check_mapper_capacity`-adjacent branch that is never exercised either. Coverage confirms lines 999-1001, 1008-1010, 1018-1020, and 1023-1025 of `main.py` (the four `[ERROR] ...; sys.exit(1)` failure branches inside `run_song_build`) are never hit by any test. This means: even setting aside REG-27/REG-28's root causes, the suite has no test proving `run_song_build` degrades gracefully (clear message + exit 1, not a raw traceback) when the real compile fails — the exact scenario REG-27's live repro hits every time for a 1-song bank. A real 1-song `requires_cc65` test (the REG-27 fix) would incidentally close this gap for the compile-failure branch, but the mapper-capacity and validate-failure branches would remain untested even after that fix.
- **Evidence**: `python -m pytest tests/test_main.py -k RunSongBuild --cov=main --cov-report=term-missing -q` output includes `999-1001, 1008-1010, 1019-1020, 1024-1025` in `main.py`'s Missing lines for those exact tests.
- **Impact**: Lower blast radius than REG-27/REG-28 on its own (it's a defense-in-depth/error-message gap, not a correctness bug), but it's the reason the suite gave no early warning that `song build`'s failure path was even reachable in practice — a `compile_rom` call that actually returns `False` (as it does for every 1-song bank per REG-27) has never been observed by a test.
- **Related**: REG-27 (a real `requires_cc65` 1-song test would cover the compile-failure branch as a side effect); precedent pattern in `TestRunCompile`/`TestRunPrepare` (per this class's own docstring, "same style as") — worth checking whether those sibling classes have the same mock-only gap, out of scope for this pass.
- **Suggested Fix**: Add a `TestRunSongBuild` test that mocks `main.compile_rom` to return `False` and asserts `SystemExit` + the `"[ERROR] Compilation failed"` message (mirroring existing patterns elsewhere in `test_main.py`, e.g. `TestRunCompile`), plus one for `main.validate_rom` returning `False` under `skip_validation=False`.

## Reverified — no regression (not re-filed)

- **REG-26/#414** (`TestCA65CompilationIntegration` missing `requires_cc65` gate): still fixed — both it and `TestJukeboxCompilationIntegration` carry the class-level marker; 9/9 and 2/2 pass with the toolchain present.
- **REG-06/#46** (`ParallelPatternDetector` determinism): tie-break intact, 12/12 pass.
- **REG-10/REG-11/#128/#129** (ROM-validation / e2e-pipeline masked skips): both files pass unconditionally (23/23, 12/12), no `except → skip` reintroduced.
- **REG-07/REG-08/REG-09/#47/#48/#49** (mapper/track_mapper/cc65_wrapper coverage): 71-86%, consistent with the 08-06 baseline, no drop.
- **REG-05/REG-20/#45/#339** (bare `assertIn("PATTERNS"...)`): still absent; the two remaining mentions in `test_famistudio_export.py`/`test_exporter_integration.py` are comments explaining the deliberate avoidance, not live weak assertions.
- `test_no_unused_imports.py` / `test_repo_hygiene.py`: 3/3 pass (REG-23/#393 fix holds).

## Prioritized backlog

1. **REG-27** (HIGH) — add a `requires_cc65` 1-song jukebox real-compile test to `TestJukeboxCompilationIntegration`, targeting the actual `export_song_bank_bytecode([_song_frames(60)], ...)` + `prepare_project(song_count=1)` path `run_song_build` uses. This is a one-song bank — the single most basic use of the brand-new feature — and it currently cannot ship a working ROM at all.
2. **REG-28** (HIGH) — add a segment-placement assertion for `song{i}_instrument_table`/macro labels (`i >= 1`) in `TestExportSongBankBytecode`, and fix `export_song_bank_bytecode` to re-emit `.segment "CODE_8000"` before each song's `_build_song_bytecode` call. Silent playback corruption on every song after the first in any 2+-song jukebox ROM; currently invisible to both the linker and the existing structural-diagnostics test.
3. **REG-29** (MEDIUM) — add `compile_rom`/`validate_rom`-returns-`False` tests to `TestRunSongBuild` so the CLI's own error-reporting path for these two bugs (and any future real-compile regression) has coverage independent of REG-27/REG-28's fixes.
4. (LOW, not separately filed) `midi_to_frames_for_song`'s legacy (`--arranger`-off) *successful* mapping path is only exercised via its `FileNotFoundError` branch in `TestRunSongBuild`; every full run in that class uses `arranger=True`. Worth a follow-up test once REG-27/28 land, low urgency since the arranger path is the documented default for new content.

## Summary

3 new findings this run: **REG-27 (HIGH)**, **REG-28 (HIGH)**, **REG-29 (MEDIUM)** — all
against the newly-merged `song build` / jukebox feature (#30/F-13). Both HIGH findings
were independently confirmed by live `ca65`/`ld65` reproduction, not just static reading:
a one-song bank fails to link with 8 unresolved externals, and a two-song bank's second
song has its instrument table physically misplaced into a dynamically-banked segment
that the existing `TestJukeboxCompilationIntegration` test cannot detect (it only checks
that the ROM links and boots). All previously-fixed regression items (REG-06, REG-07,
REG-08, REG-09, REG-10, REG-11, REG-23, REG-26) were reverified and hold with no
detected drift.

Suggested next step:
```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-08-07.md
```
