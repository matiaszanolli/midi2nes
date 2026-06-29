# Regression / Test-Hygiene Audit — MIDI2NES

- **Date**: 2026-06-29
- **Scope**: The test suite itself (`tests/`) — coverage gaps, weak assertions, round-trip/e2e gaps, stale/wrong-target tests, determinism/flakiness, fixture hygiene. This is a **delta** audit over the 2026-06-28 regression report.
- **Skill**: `/audit-regression`
- **Suite state at audit time**: **621 passed, 16 skipped** (`python -m pytest -q`). The suite is now **GREEN** (the 2026-06-28 run was 9 FAILED). Overall line coverage ≈ **83%** unchanged (`--cov=.`). `ca65`/`ld65` present at `/usr/bin`.
- **Dedup basis**: `/tmp/audit/issues.json` (22 open issues). Prior reports in `docs/audits/` scanned: `AUDIT_REGRESSION_2026-06-28.md`, `AUDIT_PIPELINE_2026-06-28.md`, `AUDIT_NES_HARDWARE_2026-06-28.md`, `AUDIT_MAPPERS_2026-06-28.md`.

## Status of the 2026-06-28 regression findings

| Prior | Issue | Verdict now |
|-------|-------|-------------|
| REG-01 (CA65 compile gate RED; `audio_engine.asm:178` branch out of range) | — | **FIXED**. `audio_engine.asm` was rewritten; the 7 `TestCA65CompilationIntegration` tests now pass. Suite green. Not re-reported. |
| REG-02 (stale `.segment "HEADER"` e2e assertions) | — | **FIXED**. `verify_ca65_assembly` is now export-mode-aware (`tests/test_midi_parser_integration.py:64-94`); the `.segment "HEADER"` assert in `test_e2e_pipeline.py:235` now correctly targets `main.asm`. Not re-reported. |
| REG-03 (4 obsolete `@unittest.skip`'d classes, no tracking issue) | #42 | **Still open / valid** — Existing: #42. |
| REG-04 (`--arranger` front-end zero coverage) | #44 | **Still open / valid** — Existing: #44. |
| REG-05 (exporter tests assert shape, not bytes) | #45 | **Still open / valid** — Existing: #45. |
| REG-06 (`ParallelPatternDetector` 37%, fallback/determinism untested) | #46 | **Still open / valid** — Existing: #46. |
| REG-07 (no `test_mappers.py`; factory auto-select 51%) | #47 | **Still open / valid** — Existing: #47. |
| REG-08 (legacy multi-track allocation `track_mapper.py:206-240`) | #48 | **Still open / valid** — Existing: #48. |
| REG-09 (`cc65_wrapper.py` error/missing-tool paths untested) | #49 | **Still open / valid** — Existing: #49. |

The recent fix wave (#4–#16, #18–#21, #36, #50) landed with **good** accompanying tests: the new `#6/#10/#11` safety gates (`estimate_music_data_size`, `check_mapper_capacity`, the bad-vector / no-APU-init hard-fail, the INCOMPLETE-OUTPUT banner) have strong behavioral tests in `tests/test_main_pipeline.py:765-1015` that assert exact behavior (overflow raises, vectors hard-fail with `SystemExit(1)`), not shape. No regression there.

---

## 1. Coverage Map (delta — unchanged subsystems collapsed)

Coverage is materially unchanged from 2026-06-28. The high-blast-radius gaps remain exactly the open issues above:

| Subsystem | Source (cov%) | Open gap |
|-----------|---------------|----------|
| Patterns (parallel) | `tracker/pattern_detector_parallel.py` **37%** | #46 (REG-06) |
| Arranger (all) | `role_analyzer.py` **56%**, `voice_allocator.py` 73%, `pipeline_integration.py` 69% | #44 (REG-04) |
| Mappers | `factory.py` **51%**, `base.py` 70%, `nrom.py` 68% | #47 (REG-07) |
| cc65 wrapper | `compiler/cc65_wrapper.py` **71%** (error branches) | #49 (REG-09) |
| Track mapper (legacy) | `tracker/track_mapper.py` **71%** (206-240) | #48 (REG-08) |
| ROM-validation integration | `test_rom_validation_integration.py` 4/9 tests **SKIP at runtime** | **NEW — REG-10** |
| e2e anchor | `test_e2e_pipeline.py` full-pipeline test masks failures | **NEW — REG-11** |

The new safety-gate code in `main.py` (`estimate_music_data_size`, `check_mapper_capacity`) is now covered (was new this cycle).

---

## 2. Findings

### REG-10: Four ROM-compile integration tests silently SKIP on a *real* compile failure — stale `music.asm` fixture, misleading "CC65 may not be installed" skip
- **Severity**: MEDIUM
- **Dimension**: Stale / wrong-target tests (Dim 4) + Determinism/false-green (Dim 5)
- **Location**: `tests/test_rom_validation_integration.py:64-100` (fixture + skip), repeated at `:151-153, :203-205, :257-259, :333-335`
- **Status**: NEW
- **Description**: This module is the designated "compile a real ROM and validate its bytes" gate — its own docstring calls step 6 "THE CRITICAL STEP … the test that will catch if ROMs are being generated without proper validation." With `ca65`/`ld65` present at `/usr/bin`, **4 of its 9 tests SKIP at runtime** (`test_generate_and_validate_real_rom`, `test_rom_binary_contents_validation`, `test_rom_health_check_integration`, `test_debug_mode_rom_generation`, `test_generated_rom_has_expected_size`). Root cause: the hand-written `music.asm` fixture (`:64-85`) defines the music entry points as bare labels `init_music:` / `update_music:` with **no `.global`/`.export`**, so `ld65` fails with `Unresolved external 'init_music' referenced in main.asm(60)` and `compile_rom` returns `False`. The test then runs `pytest.skip("CC65 compilation failed - CC65 may not be installed")`, **blaming a missing toolchain that is in fact installed**. The real CA65 exporter emits `.export init_music, update_music` (`exporter/exporter_ca65.py:719,1138`), so the *real* pipeline links fine — only the stale fixture is broken.
- **Evidence**:
  ```
  $ python -m pytest tests/test_rom_validation_integration.py -v
  ... 4 passed, 5 skipped       # ca65/ld65 both at /usr/bin
  $ # direct repro of compile_rom on the fixture asm:
  [ERROR] Failed to link ROM: Unresolved external 'init_music' referenced in:
    .../proj/main.asm(60)
  Unresolved external 'update_music' referenced in: .../proj/main.asm(79)
  ld65: Error: 2 unresolved external(s) found
  compile_rom returned: False
  ```
  Fixture (`:70-84`) has `init_music:` / `update_music:` with no export; `main.asm` template declares `.global init_music` / `jsr init_music` (`nes/project_builder.py:579,597`).
- **Impact**: These four e2e ROM-byte assertions (valid iNES header, `reset_vectors_valid`, `apu_pattern_count > 0`, `zero_byte_percent < 85`) provide **zero coverage on every run** while the suite reports green. The `except Exception → pytest.skip("…CC65 may not be installed")` cannot distinguish "tool absent" from "engine emits unlinkable asm" — so the exact REG-01-class failure (a ROM that won't compile/boot, CRITICAL blast radius) would be **masked as a skip**, not a failure. The gate self-disables on the failure it exists to catch.
- **Related**: Prior REG-01 (#now-fixed compile regression that these tests should have guarded); REG-11 (same masking shape).
- **Suggested Fix**: (1) Fix the fixture: add `.export init_music, update_music` (or `.global`) to the hand-written `music.asm` so it links like the real exporter output. (2) Replace `except Exception → pytest.skip(...)` with a real `cc65`-presence check at module/fixture scope (`shutil.which("ca65")`) and let an actual compile failure **FAIL**, not skip. Only skip when the toolchain is genuinely absent.

### REG-11: e2e anchor `test_full_pipeline_midi_to_validated_rom` masks pipeline failures (try/except→skip + conditional assertions + skip_validation)
- **Severity**: LOW
- **Dimension**: Weak assertions (Dim 2) + Stale/wrong-target (Dim 4)
- **Location**: `tests/test_e2e_pipeline.py:152-188`
- **Status**: NEW
- **Description**: The skill names `tests/test_e2e_pipeline.py` as "the anchor" for the parse→…→ROM round trip. This test currently (a) runs the whole pipeline inside a bare `try: … except Exception as e: pytest.skip(...)` (`:171,187-188`), (b) sets `args.skip_validation = True` (`:169`) so the post-build ROM gate is disabled, and (c) wraps every assertion in `if rom_path.exists():` (`:177`). The real default pipeline does work today — I confirmed it generates a 524,304-byte MMC3 ROM and the assertions pass — so this is a **latent** weakness, not an active false-green. But structurally: if the pipeline ever raised (the common regression mode), the test would SKIP; if it ran but produced no ROM, the assertions would be **silently bypassed** and the test would PASS vacuously. None of the three failure modes (raise / no-ROM / bad-ROM-with-validation-off) produce a red test.
- **Evidence**: `:171` `try:` … `:187` `except Exception as e:` → `:188` `pytest.skip(...)`; `:177` `if rom_path.exists():` guards the asserts; `:169` `args.skip_validation = True`. Confirmed the happy path produces a real ROM (`run_full_pipeline` → `✅ SUCCESS! ROM created … 524,304 bytes`).
- **Impact**: The single anchor e2e test cannot fail on a broken pipeline for valid input — it can only pass or skip. It does not exercise arranger mode or `--no-patterns` either (the skill calls out both). Blast radius is coverage-confidence: a real end-to-end regression ships green.
- **Related**: REG-10 (identical skip-masking pattern); REG-04/#44 (arranger e2e still uncovered).
- **Suggested Fix**: Drop the broad `try/except → skip`; gate only on `@pytest.mark.requires_cc65` / a `shutil.which` skip. Assert `rom_path.exists()` unconditionally (don't make it a precondition for the asserts). Add sibling cases that run the anchor with `--arranger` and with `no_patterns=True` and `skip_validation=False`.

---

## 3. Prioritized Backlog (delta — by blast radius)

| Rank | Finding | Action | Why |
|------|---------|--------|-----|
| 1 | **REG-10** (NEW) | Fix the stale `music.asm` export fixture; make a real compile failure FAIL not skip | The "CRITICAL STEP" e2e ROM-byte gate is silently disabled right now — it would mask the exact REG-01 compile regression it exists to catch |
| 2 | #45 (REG-05) | Golden-bytes CA65/NSF export test | Register-boundary value correctness, HIGH-rated failure class, still shape-only |
| 3 | #44 (REG-04) | `tests/test_arranger.py` | Only front-end with zero behavioral coverage |
| 4 | #46 (REG-06) | Parallel-detector determinism + fallback + round-trip | Guards CRITICAL (lossless) + HIGH (fallback) failure modes |
| 5 | #47 (REG-07) | `tests/test_mappers.py` (auto-select + header/cfg + overrun) | Header/cfg drift HIGH; capacity overrun CRITICAL |
| 6 | **REG-11** (NEW) | De-mask the e2e anchor; add arranger + `--no-patterns` e2e cases | The one anchor test can't go red on a broken pipeline |
| 7 | #49 (REG-09), #48 (REG-08), #42 (REG-03) | cc65 error paths; multi-track allocation; resolve obsolete skips | Defensive subprocess; default allocation; dead-test hygiene |

**Top NEW test to write first**: repair `tests/test_rom_validation_integration.py` (REG-10) — add `.export init_music, update_music` to its `music.asm` fixture so it links, and convert the `except → skip` into a real `cc65`-presence gate so an unlinkable engine FAILS the suite. This restores the e2e ROM-compile/byte gate that is currently a no-op while looking healthy.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-06-29.md
```
