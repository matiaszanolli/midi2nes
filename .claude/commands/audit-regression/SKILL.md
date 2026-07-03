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
REG-11 below, from `AUDIT_REGRESSION_2026-06-28.md` / `-06-29.md`). Most are now fixed —
don't re-report them — but re-verify status on every run: a fix landing doesn't guarantee it
stays landed, and the two still-open items (REG-10, REG-11) are exactly the kind of
skip-masking this audit exists to catch.

## Parameters
- `--limit <N>` — cap findings (report the top N by risk). Default: no cap.

## Step 1: Inventory
```bash
ls tests/                                   # 50 test_*.py + conftest.py
python -m pytest -q --collect-only | tail -5
python -m pytest --cov=. --cov-report=term-missing -q   # if pytest-cov present

# The two CC65-gated suites mask real failures as skips (see Dimension 3/4) — run
# them directly with the toolchain present and read the skip reasons, don't trust
# a green summary:
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
  (DPCM routing, noise-period routing). Still worth checking: no test drives
  `--arranger` through the *real* ROM-compile path (see Dimension 3).

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
- **Still open (REG-10/#128, MEDIUM)**: `tests/test_rom_validation_integration.py` is
  the designated "compile a real ROM and validate its bytes" gate, but **5 of its 9
  tests still SKIP** even with `ca65`/`ld65` present (confirmed: `ssss..s..` — 4
  passed, 5 skipped). Root cause unchanged: the hand-written `music.asm` fixture
  (`tests/test_rom_validation_integration.py:64-85`) defines `init_music:`/
  `update_music:` as bare labels with no `.export`/`.global`, so `ld65` fails with
  `Unresolved external 'init_music'` and the `except Exception → pytest.skip(...)` at
  lines 98-100, 151-153, 203-205, 257-259, 333-335 reports "CC65 may not be installed"
  — which is false; the toolchain is present, only the fixture is unlinkable. The real
  exporter (`exporter/exporter_ca65.py:1138`) emits `.export init_music, update_music`,
  so the actual pipeline is unaffected — only this test's own fixture is broken, and it
  provides **zero coverage** on every run while reporting green-ish.
- **Still open (REG-11/#129, LOW)**: the anchor
  `test_full_pipeline_midi_to_validated_rom` (`tests/test_e2e_pipeline.py:154-188`)
  cannot fail on a broken pipeline for valid input — only pass or skip. It (a) wraps
  the whole run in `try: ... except Exception as e: pytest.skip(...)` (`:171,187-188`),
  (b) sets `args.skip_validation = True` (`:169`), and (c) guards every assertion with
  `if rom_path.exists():` (`:177`). Confirmed still present verbatim. It also still
  does not exercise `--arranger` or `--no-patterns` through a real compile (confirmed:
  no `arranger` reference anywhere in `tests/test_e2e_pipeline.py`, and
  `tests/test_main_pipeline.py` exercises `no_patterns` only against mocked
  `run_full_pipeline` calls, never a real `ca65`/`ld65` compile) — ties back to the
  Dimension 1 arranger note above.

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

Still-open stale-artifact case: the `music.asm` fixture in
`tests/test_rom_validation_integration.py` (REG-10 above) is a checked-in-by-hand
artifact that has drifted from what the real exporter emits — the same failure shape
this dimension exists to catch, just not yet fixed.

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
use them. The one fixture that has actually drifted from reality is the hand-written
`music.asm` in `tests/test_rom_validation_integration.py` (see Dimension 3/4, REG-10) — it
predates the exporter adding `.export` directives and was never updated to match.

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
