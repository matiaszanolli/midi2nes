# Regression / Test-Hygiene Audit — MIDI2NES

- **Date**: 2026-06-28
- **Scope**: The test suite itself (`tests/`) — coverage gaps, weak assertions, round-trip/e2e gaps, stale/wrong-target tests, determinism/flakiness, fixture hygiene.
- **Skill**: `/audit-regression`
- **Suite state at audit time**: **586 tests collected; 9 FAILED, 563 passed, 14 skipped** (`python -m pytest -q`). Overall line coverage **83%** (`--cov=.`).
- **Dedup basis**: `gh issue list` returned only 2 open issues (#3 "Output seems silent", #2 "how to use") — neither test-related. All findings are **NEW**. Prior audits in `docs/audits/` (`AUDIT_NES_HARDWARE_2026-06-28.md`, `AUDIT_PIPELINE_2026-06-28.md`) do not cover test-suite health.

---

## 1. Coverage Map (subsystem → test module → coverage / gap)

| Subsystem | Source (cov%) | Test module(s) | Gap assessment |
|-----------|---------------|----------------|----------------|
| Fast parser | `tracker/parser_fast.py` 72% | `test_parser_fast.py`, `test_midi_parser_integration.py` | OK (uncovered = `__main__` block) |
| Full parser | `tracker/parser.py` 80% | (indirect) | LOW gap |
| Track mapper (legacy) | `tracker/track_mapper.py` **71%** | `test_track_mapper.py` | **Multi-track allocation heuristic (206-240) untested** |
| Tempo | `tracker/tempo_map.py` 95% | `test_tempo_map.py` | OK |
| Loops | `tracker/loop_manager.py` 92% | `test_loop_manager.py`, `test_enhanced_loop_patterns.py` | OK |
| Patterns (seq) | `tracker/pattern_detector.py` 94% | `test_patterns.py`, `test_pattern_integration.py` | OK |
| Patterns (parallel) | `tracker/pattern_detector_parallel.py` **36%** | (only smoke in `test_main_pipeline.py`) | **HIGH gap: multi-core path + fallback untested** |
| **Arranger (all)** | `role_analyzer.py` **56%**, `voice_allocator.py` 73%, `pipeline_integration.py` 69%, `gm_instruments.py` 92% | **NONE** | **HIGH gap: no test references arranger at all** |
| Frame gen | `nes/emulator_core.py` 96% | `test_frame_validation.py` (+integration) | OK |
| Pitch table | `nes/pitch_table.py` 80% | `test_pitch_tables.py`, `test_pitch_table_integration.py` | OK |
| Envelope | `nes/envelope_processor.py` 98% | `test_envelope.py`, `test_envelope_integration.py` | OK |
| Project builder | `nes/project_builder.py` 86% | `test_nes_project_builder.py` | OK |
| Song bank | `nes/song_bank.py` 79% | `test_song_bank.py` | LOW gap |
| Mappers | `factory.py` **51%**, `base.py` **54%**, `nrom.py` **64%**, `mmc1.py` 85%, `mmc3.py` 93% | (only indirect via `test_ca65_export.py`) | **MEDIUM/HIGH gap: no `test_mappers.py`; factory auto-select untested** |
| Exporters | `exporter_ca65.py` 82%, `exporter_nsf.py` 97%, `exporter_famistudio.py` 90%, `compression.py` 87% | `test_ca65_export.py`, `test_nsf_export.py`, `test_famistudio_export.py`, `test_exporter_integration.py` | OK (but weak assertions, see F2/F5) |
| Compiler | `compiler.py` 92%, `cc65_wrapper.py` **70%** | `test_rom_validation_integration.py`, `test_main_pipeline.py` | MEDIUM gap: `cc65_wrapper` error/missing-tool paths untested |
| DPCM/drums | `enhanced_drum_mapper.py` 84%, `dpcm_*` 78-89% | `test_drum_*`, `test_dpcm_*`, `test_enhanced_drum_mapper.py` | OK |
| Config | `config_manager.py` 94% | `test_config_manager.py` | OK |
| Debug overlay | `nes/debug_overlay.py` 53% | (none) | LOW gap (dev-only) |
| Dev scripts | `nes_devflow.py` **0%**, `show_greeting.py` **0%** | (none) | LOW (likely dead/utility) |

---

## 2. Findings

### REG-01: CA65 compilation integration tests are RED — generated `audio_engine.asm` fails to assemble (branch out of range)
- **Severity**: HIGH
- **Dimension**: Stale / wrong-target tests (Dim 4) + the failing suite surfaces a real code bug
- **Location**: `tests/test_ca65_export.py:262` (`TestCA65CompilationIntegration`, all 7 methods); root cause `nes/audio_engine.asm:178`
- **Status**: NEW
- **Description**: 7 of the 9 suite failures are the CA65 compilation integration tests. They fail not because the toolchain is missing (`ca65`/`ld65` are present at `/usr/bin`) but because the shipped engine produces an assembler error: `audio_engine.asm(178): Error: Range error (130 not in [-128..127])`. Line 178 is `bcc @is_note`, a relative branch whose target is 130 bytes away — exceeds the 6502 ±127 branch range. Every project the builder emits currently fails to compile.
- **Evidence**:
  ```
  audio_engine.asm(178): Error: Range error (130 not in [-128..127])
  main.asm(54): Warning: Didn't use zeropage addressing for 'frame_counter'
  ```
  `nes/audio_engine.asm:177-180`:
  ```asm
  cmp #$60
  bcc @is_note      ; <-- target >127 bytes forward
  cmp #$80
  bcc @is_length
  ```
- **Impact**: Suite is red on every run; masks future regressions (a red suite trains contributors to ignore failures). Underlying bug means generated ROMs do not compile — blast radius is **every game**. The test correctly catches it, but the failure must be triaged (engine fix → `/audit-mappers` or `/audit-pipeline`), and the test should remain a gate.
- **Related**: REG-02 (same module's format-assertion tests are stale and mask this).
- **Suggested Fix**: Fix the engine branch (replace `bcc @is_note` with `bcs :+ / jmp @is_note / :+` or restructure so the branch target is in range), then keep these 7 tests as the compile gate. Do not skip them.

### REG-02: Stale e2e assertions check the *old* CA65 output format (`.segment "HEADER"`) the exporter no longer emits
- **Severity**: MEDIUM
- **Dimension**: Stale / wrong-target tests (Dim 4)
- **Location**: `tests/test_midi_parser_integration.py:77,187` (`verify_ca65_assembly`); `tests/test_e2e_pipeline.py::test_full_pipeline_midi_to_validated_rom`
- **Status**: NEW
- **Description**: 2 of the 9 failures assert that exported `.asm` contains `.segment "HEADER"`. The CA65 exporter switched to "MMC3 Macro Bytecode" mode and now emits `.segment "DPCM"`, `.segment "CODE_8000"`, `.segment "BANK_00"` with macro/sequence tables — **no `HEADER` segment**. The assertions test a format that no longer exists, so they fail on correct output and would never catch a real regression in the *current* format.
- **Evidence**:
  ```
  AssertionError: '.segment "HEADER"' not found in '; CA65 Assembly Export (MMC3 Macro Bytecode) ...'
  ```
  Actual output begins `.segment "DPCM"` / `.segment "CODE_8000"` / `.segment "BANK_00"` and contains `pulse1_sequence`, `ntsc_period_low`, `instrument_table`, `macro_vol_0`.
- **Impact**: False failures; the e2e/parser-integration tests no longer validate the real artifact. They cannot catch a genuine break in the macro-bytecode format.
- **Related**: REG-01, REG-03.
- **Suggested Fix**: Update `verify_ca65_assembly`'s required-section list to the current segments (`DPCM`, `CODE_8000`, `BANK_00`) and assert presence of `pulse1_sequence`/`ntsc_period_low`/`instrument_table`. Better: assert exact bytecode bytes for a known input (see REG-05).

### REG-03: Four obsolete tests in `test_audio_fixes.py` are `@unittest.skip`'d with no replacement and no tracking issue
- **Severity**: LOW
- **Dimension**: Stale / wrong-target tests (Dim 4)
- **Location**: `tests/test_audio_fixes.py:21,119,250,386`
- **Status**: NEW
- **Description**: Four test classes are skipped with `@unittest.skip("Obsolete: Assembly generation changed to MMC3 Macro Bytecode")`. They account for the module's 42% coverage (122 of 209 lines dead). The behaviors they used to verify (audio register/format fixes) are now unverified — they were disabled, not ported to the new format, and there is no GitHub issue tracking the gap.
- **Evidence**: `grep '@unittest.skip' tests/test_audio_fixes.py` → 4 hits, all "Obsolete: ... MMC3 Macro Bytecode".
- **Impact**: Whatever audio-fix invariants these guarded are now untested. Skipped-without-issue tests rot silently.
- **Suggested Fix**: Either delete the dead classes (and re-assert their invariants in a macro-bytecode-aware test) or file a tracking issue and reference it in the skip reason. Prefer porting the value assertions to the new format rather than deleting.

### REG-04: The entire `--arranger` front-end has zero test coverage (no test references it)
- **Severity**: MEDIUM
- **Dimension**: Untested subsystems (Dim 1)
- **Location**: `arranger/role_analyzer.py` (56%), `arranger/voice_allocator.py` (73%), `arranger/pipeline_integration.py` (69%), `arranger/gm_instruments.py` (92%)
- **Status**: NEW
- **Description**: `grep -rln "arrange_for_nes|--arranger|arranger" tests/` returns **nothing**. The arranger is one of two front-ends (`--arranger` mode does role analysis, GM mapping, smart channel allocation, and arpeggiation for polyphony) and feeds the same downstream `frames` contract. None of its logic is exercised by any test — the 56-73% coverage shown is incidental import/init, not behavioral verification. Arpeggiation correctness (chord → alternating-note sequence) and channel allocation are completely unguarded.
- **Evidence**: No test file imports `arrange_for_nes`, `VoiceRoleAnalyzer`, or `VoiceAllocator`. Coverage of `role_analyzer.py` decision branches (lines 340-428) is 0%.
- **Impact**: Any regression in role detection, GM→channel mapping, or arpeggiation ships silently. Blast radius: every `--arranger` run (polyphonic MIDI). A wrong voice dropped or a triangle assigned a duty would not be caught.
- **Related**: see `/audit-arranger` for behavioral correctness.
- **Suggested Fix**: Add `tests/test_arranger.py`. Concrete inputs and properties:
  1. **Role analysis**: feed `test_midi/multiple_tracks.mid`; assert `VoiceRoleAnalyzer` tags the lowest-avg-pitch track as bass and highest as melody.
  2. **Arpeggiation**: craft a 3-note chord event (C/E/G at one tick) → assert `arrange_for_nes` emits an alternating single-note sequence on one channel (no two notes same frame on one channel), period matches `docs/arpeggio.md`.
  3. **Channel-honoring invariant**: assert no event routed to `triangle` carries a duty/volume field the triangle can't honor (cross-check `docs/APU_TRIANGLE_REFERENCE.md`).
  4. **Contract**: assert `arrange_for_nes(events)` output is structurally interchangeable with `process_all_tracks` output (same `{channel: {frame: {...}}}` shape).

### REG-05: NES-output / exporter tests assert shape, not bytes — would pass on wrong music
- **Severity**: MEDIUM
- **Dimension**: Weak assertions (Dim 2)
- **Location**: `tests/test_exporter_integration.py:108-120`; `tests/test_midi_parser_integration.py:77` (section-presence only)
- **Status**: NEW
- **Description**: Per `_audit-severity.md`, the NES-register/exporter path is the high-blast-radius boundary where Python values become APU writes; tests there must assert exact bytes. Several exporter tests assert only file existence and presence of a header magic / substring (`assertIn("PATTERNS", content)`, `header[:5] == b'NESM\x1a'`, `assertIn(section, content)`). They would pass even if every note/timer/volume byte were wrong. The CA65 macro-bytecode (`pulse1_sequence` `.byte` stream, `ntsc_period_low/high` tables) is never byte-compared against a golden expectation for a known input.
- **Evidence**: `test_famistudio_export_with_compression` asserts only `assertIn("PATTERNS", content)`; NSF test asserts only the 5-byte magic; the parser-integration `verify_ca65_assembly` checks only that named sections exist.
- **Impact**: A regression that emits correct *structure* but wrong *values* (e.g. a pitch-table off-by-one, a wrong length nibble, a swapped duty) ships green. This is precisely the failure class the severity doc rates HIGH at the register boundary.
- **Related**: REG-02.
- **Suggested Fix**: Add a golden-bytes test: parse `test_midi/simple_loop.mid` → frames → export CA65, and `assertEqual` the `pulse1_sequence` `.byte` lines and the first 32 `ntsc_period_low` bytes against a checked-in expected fragment. Same for NSF: assert the bytecode region, not just the header magic.

### REG-06: `ParallelPatternDetector` (36% cov) — multi-core path, fallback, and core-count determinism untested
- **Severity**: MEDIUM
- **Dimension**: Untested subsystems (Dim 1) + Determinism/flakiness (Dim 5)
- **Location**: `tracker/pattern_detector_parallel.py` (lines 134-468 largely uncovered)
- **Status**: NEW
- **Description**: The default pattern-detection front-end is only smoke-touched in `test_main_pipeline.py`; the actual `ProcessPoolExecutor` map, the `as_completed` result merge, the score-`sort`+`set`-based selection (lines 181-188), and the documented graceful fallback to `EnhancedPatternDetector` are uncovered. Two risks: (a) the worker path could raise on common input without the fallback firing (a HIGH-rated failure mode per `_audit-severity.md`) and no test guards it; (b) `chunk_size = (len - length + 1) // max_workers` and `max_workers = cpu_count() - 1` make chunk boundaries — and therefore which patterns are discovered — **depend on host core count**, with no test asserting result-invariance across worker counts.
- **Evidence**: `cov` 36%; lines 264-468 (worker dispatch + merge) unexecuted. `self.max_workers = max(1, mp.cpu_count() - 1)`; `chunk_size = max(1, (len(sequence) - length + 1) // self.max_workers)`.
- **Impact**: Compression could differ run-to-run / host-to-host (CI vs local), and a worker-pool crash could silently yield no patterns. Guards a CRITICAL failure mode (round-trip) and a HIGH one (fallback).
- **Suggested Fix**: Add `tests/test_pattern_detector_parallel.py`:
  1. **Determinism**: run detection on `test_midi/short_loops.mid` frames with `max_workers=1`, `2`, `4`; assert identical `patterns`/`references`/`compression_ratio`.
  2. **Fallback**: monkeypatch the worker entry to raise; assert it falls back to `EnhancedPatternDetector` and still returns the required keys (`patterns`, `references`, `stats`, `variations`).
  3. **Round-trip**: assert compress→decompress reproduces the original sequence (guards the CRITICAL lossless claim).

### REG-07: No dedicated mapper tests — `MapperFactory` size-based auto-select (51%) and header/nes.cfg consistency unverified
- **Severity**: MEDIUM
- **Dimension**: Untested subsystems (Dim 1)
- **Location**: `mappers/factory.py` (51%), `mappers/base.py` (54%), `mappers/nrom.py` (64%); no `tests/test_mappers.py`
- **Status**: NEW
- **Description**: Mappers are only exercised indirectly through `test_ca65_export.py`. `MapperFactory`'s auto-select-by-data-size logic (lines 98-158, uncovered) and each mapper's `header`/`linker_config`/`capacity` outputs are untested in isolation. Per `_audit-severity.md`, a mapper-header vs `nes.cfg` mismatch is HIGH — there is no test asserting the iNES header byte (mapper number) matches the `nes.cfg` the same mapper emits.
- **Evidence**: `grep -rln MapperFactory tests/` → only `test_ca65_export.py`. `factory.py` lines 98-111, 124-158 uncovered.
- **Impact**: A wrong auto-selected mapper or a header/linker drift (HIGH severity) would ship unguarded. PRG-capacity-overrun detection (a CRITICAL row) is also untested at the mapper layer.
- **Suggested Fix**: Add `tests/test_mappers.py`:
  1. **Auto-select**: feed `MapperFactory` data sizes crossing each capacity threshold; assert the expected mapper (NROM→MMC1→MMC3) is chosen.
  2. **Header↔cfg consistency**: for each mapper assert the iNES header's mapper nibble equals the mapper number its `nes.cfg`/linker config targets.
  3. **Capacity overrun**: assert data exceeding a mapper's PRG capacity is detected (raises or escalates), not silently truncated.

### REG-08: Legacy multi-track channel-allocation heuristic untested (`track_mapper.py` 206-240)
- **Severity**: LOW
- **Dimension**: Untested subsystems (Dim 1)
- **Location**: `tracker/track_mapper.py:206-240`
- **Status**: NEW
- **Description**: `test_track_mapper.py` covers the single-track pitch-split path but not the multi-track branch (the `average_pitch` ranking that assigns melody→pulse1, harmony→pulse2 with arpeggio fallback, bass→triangle, drums→noise/dpcm). This is the default (non-arranger) allocation for multi-track MIDI and is entirely unverified.
- **Evidence**: Lines 206-240 uncovered; logic ranks channels by `average_pitch` and pops highest→pulse1, etc.
- **Impact**: A regression in default multi-track voice assignment (e.g. bass routed to a pulse channel) ships green for the most common real-world MIDI shape.
- **Suggested Fix**: Add to `test_track_mapper.py`: feed `test_midi/multiple_tracks.mid` events; assert the highest-avg-pitch track lands on `pulse1`, the lowest on `triangle`, and a `drum`-named track on `noise`.

### REG-09: `cc65_wrapper.py` (70%) — missing-tool detection and nonzero-exit/stderr handling untested
- **Severity**: MEDIUM
- **Dimension**: Untested subsystems (Dim 1) — defensive subprocess path
- **Location**: `compiler/cc65_wrapper.py:86-99,129-130,184-185,203,229-241`
- **Status**: NEW
- **Description**: `_audit-common.md` flags the cc65 subprocess as a must-check path: return-code handling, missing-tool detection, and stderr surfacing. The uncovered lines are exactly the error branches (nonzero `ca65`/`ld65` exit, missing-binary handling). No test forces `ca65` to fail and asserts the wrapper raises/propagates rather than reporting success — the HIGH-rated "CC65 nonzero exit ignored" failure mode is unguarded by a unit test.
- **Evidence**: Coverage misses the error-handling lines (86-99, 229-241); existing compiler tests use the happy path or a present toolchain.
- **Impact**: If a future change swallows a compile error, the suite stays green while emitting broken ROMs (HIGH per severity doc).
- **Suggested Fix**: Add `tests/test_cc65_wrapper.py`: (a) monkeypatch `subprocess.run` to return rc=1 + stderr; assert the wrapper raises `CompilationError` with stderr surfaced. (b) Point the wrapper at a nonexistent `ca65`; assert a clear missing-tool error, not a generic crash.

---

## 3. Prioritized Backlog (by blast radius)

| Rank | Finding | Action | Why first |
|------|---------|--------|-----------|
| 1 | REG-01 | Fix `audio_engine.asm:178` branch range, keep the 7 compile tests green | Suite is RED on every run and ROMs don't compile — every game affected; a red suite hides all other regressions |
| 2 | REG-02 | Update e2e/parser-integration assertions to the macro-bytecode format | 2 more false failures; the e2e gate currently validates a format that doesn't exist |
| 3 | REG-05 + REG-04 | Golden-bytes exporter test + first arranger test | The register-boundary value-correctness gap (HIGH-rated) and the only completely-untested front-end |
| 4 | REG-06 | Parallel-detector determinism + fallback + round-trip | Guards a CRITICAL (lossless) and HIGH (fallback) failure mode; CI-vs-local flakiness risk |
| 5 | REG-07 | `test_mappers.py` (auto-select + header/cfg + overrun) | Header/cfg drift is HIGH; capacity overrun is CRITICAL |
| 6 | REG-09 | `test_cc65_wrapper.py` error paths | HIGH "compile failure reported as success" guard |
| 7 | REG-08, REG-03 | Multi-track mapper test; resolve obsolete skips | Default allocation path + dead-test hygiene |

**Top 3 tests to write first**:
1. Repair the CA65 compilation gate (REG-01): fix the engine branch and keep `TestCA65CompilationIntegration` green so a real "ROM won't compile" regression is always caught.
2. Golden-bytes CA65/NSF export test (REG-05) over `test_midi/simple_loop.mid`: assert exact `pulse1_sequence` `.byte` stream + first 32 `ntsc_period_low` bytes — converts shape-only assertions into value assertions at the register boundary.
3. `tests/test_arranger.py` (REG-04): role-assignment + arpeggiation invariants on `test_midi/multiple_tracks.mid` and a crafted chord — the only front-end with zero coverage.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-06-28.md
```
