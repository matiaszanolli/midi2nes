---
description: "Audit test-suite health — coverage gaps, weak assertions, flaky/stale tests"
argument-hint: "[--limit <N>]"
---

# Regression / Test-Hygiene Audit

Audit the **test suite itself**: where coverage is missing on code that can break, where
tests assert too little to catch a regression, and where tests are stale, flaky, or testing
the wrong thing. The output is a prioritized list of tests to add or strengthen — the safety
net for every other audit's fixes.

Shared protocol: `.claude/commands/_audit-common.md`. Severity:
`.claude/commands/_audit-severity.md` — a coverage gap on working code is LOW, but a gap on
a path that *has had bugs* or that emits NES register data is MEDIUM (the blast radius is a
silently-broken ROM).

A recent sprint closed ~100 issues, several against the test suite itself (REG-01 through
REG-11 below, from `AUDIT_REGRESSION_2026-06-28.md` / `-06-29.md`). All are now fixed —
don't re-report them — but re-verify status on every run: a fix landing doesn't guarantee it
stays landed, and the skip-masking that REG-10/REG-11 removed (CC65-gated suites reporting
real compile failures as "CC65 may not be installed" skips) is exactly the failure shape
this audit exists to catch.

## Parameters
- `--limit <N>` — cap findings (report the top N by risk). Default: no cap.

## Step 1: Inventory
```bash
ls tests/                                   # 52 test_*.py + conftest.py
python -m pytest -q --collect-only | tail -5
python -m pytest --cov=. --cov-report=term-missing -q   # if pytest-cov present

# The CC65-gated suites now use a real gate: `conftest.py:pytest_runtest_setup`
# skips @requires_cc65 only when ca65/ld65 are genuinely absent (via `shutil.which`),
# so with the toolchain present they compile real ROMs and assert unconditionally.
# Run them directly to confirm they PASS (not skip), don't just trust a green summary:
python -m pytest tests/test_ca65_export.py::TestCA65CompilationIntegration -v
python -m pytest tests/test_rom_validation_integration.py -v
```
Cross-reference `tests/` against `_audit-common.md` § Project Layout: every subsystem
should have at least one test module. Map test file → subsystem it covers.

## Step 2: Coverage-Gap Dimensions

### Dimension 1: Untested subsystems / modules
A source module with no corresponding test, or only an import-smoke test. Weight by risk:
the NES-register path (`nes/emulator_core.py`, `nes/pitch_table.py`,
`nes/envelope_processor.py`), the exporters, the mappers, and the compiler are the
high-blast-radius gaps. A module with `--cov` < ~50% on a pipeline path is a finding.

Four modules previously sat at 36-71% coverage with no dedicated test module, plus one
front-end (`arranger/`) with zero test references at all — all five closed, keep verifying
the coverage didn't regress rather than re-flagging from scratch:
- `tracker/track_mapper.py` — the legacy multi-track branch of
  `assign_tracks_to_nes_channels` (melody→pulse1, harmony→pulse2 w/ arpeggio,
  bass→triangle, drum-named→noise) was wholly unverified (REG-08/#48). Fixed by
  `tests/test_track_mapper.py` (synthetic 4-track + real-MIDI regression case);
  currently 71% cover.
- `compiler/cc65_wrapper.py` — missing-tool detection (`shutil.which` → `None`),
  nonzero version-probe exit, stderr surfacing, and the full `build()` pipeline had no
  direct coverage (REG-09/#49). Fixed by `tests/test_cc65_wrapper.py`; currently 86%.
- `tracker/pattern_detector_parallel.py` — the `ProcessPoolExecutor` map/merge, the
  fallback to `EnhancedPatternDetector`, and worker-count invariance were untested
  (REG-06/#46). Fixed by `tests/test_pattern_detector_parallel.py`; currently 78%
  (up from 36%).
- `mappers/factory.py` / `mappers/base.py` — `MapperFactory` auto-select and each
  mapper's header/linker/capacity output were only exercised indirectly via
  `test_ca65_export.py` (REG-07/#47). Fixed by `tests/test_mappers.py`; factory.py now
  74%, base.py 59% (residual gap: base.py's abstract-method stubs and a couple of
  capacity edge cases — worth a look, but no longer a blank gap).
- `arranger/` (`role_analyzer.py`, `voice_allocator.py`, `gm_instruments.py`,
  `pipeline_integration.py`) — the entire `--arranger` front-end had zero test
  references (REG-04/#44). Fixed by `tests/test_arranger.py` (role tagging,
  arpeggiation cadence, triangle no-duty invariant, frames-contract parity with
  `process_all_tracks`), plus `tests/test_arranger_drum_detection.py`,
  `tests/test_arranger_frame_contract.py`, and `tests/test_voice_allocator.py`
  (DPCM routing, noise-period routing). `--arranger` now also gets a real
  ROM-compile round trip
  (`tests/test_e2e_pipeline.py::TestEndToEndPipeline::test_full_pipeline_arranger_mode`,
  #129) — see Dimension 3.

### Dimension 2: Weak assertions
Tests that run code but assert almost nothing — `assert result is not None`, `assert
len(x) > 0` where the *values* matter. The NES-output tests especially must assert exact
register bytes / timer values, not just shape. Flag tests that would pass even if the music
came out wrong.

Closed example, keep as the bar to hold other exporter tests to: several
`test_ca65_export.py` / `test_midi_parser_integration.py` tests asserted only that a
section/substring was present (header magic, `"PATTERNS"` in content) — would pass even
with every note/timer/volume byte wrong (REG-05/#45). Fixed by a golden-bytes test class
that parses `test_midi/simple_loop.mid` through the real pipeline and asserts the exact
`pulse1_sequence` macro-bytecode stream and the first `ntsc_period_low` table bytes. Still
worth a periodic grep for `assertIn('PATTERNS'` / bare-existence checks elsewhere in
`tests/test_ca65_export.py`, `tests/test_exporter_integration.py`, and
`tests/test_famistudio_export.py` — the golden-bytes fix only covers the one path it
targeted.

### Dimension 3: Round-trip / end-to-end gaps
The properties that unit tests miss: parse→...→ROM produces a valid ROM
(`tests/test_e2e_pipeline.py` is the anchor); pattern compress→decompress equals the
original; a generated `.nes` passes `debug/check_rom.py`. Missing round-trip coverage on
compression is MEDIUM (it guards a CRITICAL failure mode).

- **Fixed**: the 7-method `TestCA65CompilationIntegration` class in
  `tests/test_ca65_export.py` was RED against real `ca65`/`ld65` — the shipped
  `nes/audio_engine.asm` had a relative branch (`bcc @is_note`) whose target was 130
  bytes away, outside the 6502 ±127 range (REG-01/#39). Fixed by restructuring the
  dispatch (`nes/audio_engine.asm:204-213`, `bcs`+`jmp` instead of the out-of-range
  `bcc`) — confirmed: all 9 tests in `TestCA65CompilationIntegration` pass with the
  toolchain present. Re-verify this stays green; a relative-branch regression here is
  silent until an assembler is actually invoked.
- **Fixed (REG-10/#128)**: `tests/test_rom_validation_integration.py` is the designated
  "compile a real ROM and validate its bytes" gate. It previously had 5 of 9 tests SKIP
  even with `ca65`/`ld65` present, because the hand-written `music.asm` fixture defined
  `init_music:`/`update_music:` as bare labels with no `.export`/`.global`, so `ld65`
  failed with `Unresolved external 'init_music'` and an `except Exception → pytest.skip`
  masked it as "CC65 may not be installed". Fixed: the fixture now lives in
  `tests/conftest.py`'s `minimal_music_asm` and emits `.export init_music, update_music`
  (matching the real exporter); the compile tests are gated with
  `@pytest.mark.requires_cc65` (a real `shutil.which` gate in
  `tests/conftest.py:pytest_runtest_setup`) and each asserts `compile_rom(...)`
  unconditionally, and `test_shared_music_asm_fixture_is_linkable` pins the `.export`.
  Re-verify these PASS (not skip) with the toolchain present — a re-introduced
  `except → skip` here is exactly what this dimension catches.
- **Fixed (REG-15/#299)**: the two compile-*failure* (negative-path) tests in the same file
  (`test_compilation_with_invalid_assembly`, `test_compilation_failure_without_rom_output`) kept
  the `except → pytest.skip("CC65 not installed")` masking after REG-10 removed it from the
  compile-*success* tests, compounded by pass-either-way bodies. Now both are `@requires_cc65`
  and assert `compile_rom(...) is False` plus no partial ROM. `compile_rom()` catches all failures
  and returns False (never raises), so any surviving `except → skip` in this file is dead masking —
  re-flag it.
- **Fixed (REG-11/#129)**: the anchor `test_full_pipeline_midi_to_validated_rom`
  (`tests/test_e2e_pipeline.py`) can now fail on a broken pipeline. The old
  `try/except → pytest.skip`, `args.skip_validation = True`, and `if rom_path.exists():`
  guards are gone: the shared `_run_pipeline` helper sets `skip_validation = False`
  (validation ON) and `_assert_valid_rom` asserts unconditionally, all under a
  `@pytest.mark.requires_cc65` gate. It also now exercises `--arranger`
  (`test_full_pipeline_arranger_mode`) and `--no-patterns`
  (`test_full_pipeline_no_patterns_direct_export`) through a *real* `ca65`/`ld65`
  compile — closing the Dimension 1 arranger note above. Re-verify these assertions
  stay unconditional.

### Dimension 4: Stale / wrong-target tests
Tests referencing renamed symbols, skipped/`xfail` tests with no tracking issue, tests that
assert old (now-incorrect) behavior, or tests pinned to checked-in artifact files that have
since changed. Confirm against current code.

Two closed examples worth knowing so they aren't re-flagged:
- Four test classes in `test_audio_fixes.py` were `@unittest.skip`'d with "Obsolete:
  Assembly generation changed to MMC3 Macro Bytecode" and no tracking issue (REG-03/#42).
  All four actually targeted `export_direct_frames` (the direct/table-based export path,
  never removed) and still matched every assertion — the skip reason was stale, not the
  tests. Fixed: un-skipped; the one genuine failure
  (`test_triangle_is_octave_above_pulse_period`, a harmless pulse/16 vs triangle/32
  integer-quantization drift) had its delta loosened from 0.05 to 0.08 to cover the
  observed max (~0.071) without masking a real regression.
- `verify_ca65_assembly()` in `tests/test_midi_parser_integration.py` and the e2e
  assembly check asserted the old standalone `.segment "HEADER"` format the exporter no
  longer emits in macro-bytecode mode (REG-02/#40). Fixed (commit `184d3c9`):
  `verify_ca65_assembly` (`tests/test_midi_parser_integration.py:41-73`) now branches on
  which export mode produced the content (`"MMC3 Macro Bytecode"` marker → asserts
  `.segment "CODE_8000"`/`"BANK_00"`/`pulse1_sequence:`/etc.; `"Pattern Compressed"` or
  standalone direct-frame → asserts the legacy `HEADER`/`CODE`/`VECTORS` sections,
  which are still correct for those modes). Note `tests/test_e2e_pipeline.py:235`'s
  `.segment "HEADER"` assertion is **not** stale — it checks `main.asm` from
  `NESProjectBuilder`, a file the project builder (not the CA65 exporter) still always
  emits with a HEADER segment; don't conflate the two files when re-auditing this.

Recently-fixed stale-artifact case worth knowing: the hand-written `music.asm` fixture
behind the ROM-validation tests (REG-10 above) had drifted from what the real exporter
emits (missing the `.export init_music, update_music` directives) — the same failure
shape this dimension exists to catch. Now fixed by moving it to `tests/conftest.py`'s
`minimal_music_asm` with the `.export` directives; don't re-flag it.

### Dimension 5: Determinism / flakiness
Tests depending on multiprocessing scheduling (`ParallelPatternDetector`), dict/set
ordering, wall-clock timing, or filesystem temp paths without isolation. These pass locally
and fail in CI. Flag any test whose outcome can vary run-to-run.

Closed example: `ParallelPatternDetector`'s determinism guarantee was not actually held —
`_select_best_patterns` sorted candidates by score alone, so equal-score candidates
resolved by `ProcessPoolExecutor.as_completed` arrival order, making which non-overlapping
pattern won depend on host core count (REG-06/#46, same fix as Dimension 1). Fixed: a
deterministic `(start, length)` tie-break was added, and
`tests/test_pattern_detector_parallel.py` now pins identical `patterns`/`references`/
`compression_ratio` across `max_workers=1/2/4` plus the pool-failure fallback. Re-run this
test file specifically after any change to `tracker/pattern_detector_parallel.py`'s
scoring/selection — it's the one place a reintroduced non-determinism would surface.

### Dimension 6: Fixture & isolation hygiene
Tests that write into the repo root instead of a temp dir, leak state between tests, or
depend on a prior test having run. Check `tests/conftest.py` for shared fixtures (`temp_dir`,
`project_dir`, `minimal_midi_file`, `minimal_music_asm`, `valid_rom_file`, and synthetic
ROM-corruption fixtures) and whether they're used consistently — most compiler/ROM tests do
use them. The `music.asm` fixture that had drifted from reality (missing `.export`
directives) is now the shared `minimal_music_asm` fixture in `tests/conftest.py`, updated
to emit `.export init_music, update_music` (see Dimension 3/4, REG-10) — re-verify the
shared fixture is used consistently rather than re-hand-rolled per test.

## Step 3: For each gap, specify the test
Don't just say "needs a test" — name the module, the property to assert, and the concrete
input (a `test_midi/` sample or a crafted JSON). A finding the `/fix-issue` pipeline can
act on directly.

## Output
Write to: **`docs/audits/AUDIT_REGRESSION_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Coverage map** — subsystem → test module(s) → rough coverage / gap.
2. **Findings** — base format + `Dimension`; each names the test to add/strengthen.
3. **Prioritized backlog** — the top tests to write first, by blast radius.

Then suggest:
```
/audit-publish docs/audits/AUDIT_REGRESSION_<TODAY>.md
```
