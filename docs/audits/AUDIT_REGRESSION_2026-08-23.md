# Regression / Test-Hygiene Audit — 2026-08-23

Scope: full test-suite health sweep per `.claude/commands/audit-regression/SKILL.md`,
against `master` after this session's own fix commits (`394cddb` #504/505/506,
`8489d02` #508/509/510/511/512). CC65 toolchain present (`/usr/bin/ca65`,
`/usr/bin/ld65`).

**Method**: Diffed against `AUDIT_REGRESSION_2026-08-21.md`'s six findings
(REG-30 through REG-36) plus its two carried MEDIUM items (REG-31, REG-33) by
searching `gh issue list --state all` for each ID and re-reading the current code at
each cited location rather than trusting the prior report's text. All eight are
confirmed fixed (five closed via filed issues #471-#475, two via unrelated commits
whose issue numbers were found by grep). Ran the CC65-gated anchor suites directly
(`TestCA65CompilationIntegration`, `TestJukeboxCompilationIntegration`,
`test_rom_validation_integration.py`) to confirm PASS, not skip, per this skill's
standing instruction. Ran the full suite once (`-m "not slow" -rs`) to check for any
newly-introduced skip-masking. Self-reviewed the ~10 tests this session's own two fix
commits added, since this audit's job is to catch weak assertions and a same-session
author is the least likely to catch their own.

## Coverage map

| Subsystem | Test module(s) | Status this run |
|---|---|---|
| CC65-gated suites (`TestCA65CompilationIntegration`, `TestJukeboxCompilationIntegration`, `test_rom_validation_integration.py`) | same | Ran directly: 9/9, 4/4, 11/11 pass, **zero skips**. `TestJukeboxCompilationIntegration` now has 4 tests (was 3 at the last audit) — `test_split_prepare_compile_route_links_jukebox_asm_without_song_count` (REG-35's fix) confirmed present and passing. |
| `main.py:run_song_build` (backup/restore + typed-exception contract) | `tests/test_main.py::TestRunSongBuild` (17 tests, up from 8) | REG-33's suggested tests (capacity/prepare/compile/validate failure, `prepare_project` falsy-return) all now exist and pass. **New gap found this run**: the generic `except Exception` catch-all, `verbose=True` traceback printing, and the successful-rebuild backup-cleanup branch remain uncovered — see REG-37. |
| `main.py` step-by-step wrong-stage-input guard | `tests/test_main.py` (`test_run_frames_wrong_stage_parse_file_errors`, `test_run_export_wrong_stage_parse_file_errors`, `test_run_detect_patterns_wrong_stage_parse_file_errors`) | REG-31's stranded fix (#377/PIPE-2026-08-21-2) is merged on master via `#485`; all 4 wrong-stage tests pass. |
| `dpcm_sampler/enhanced_drum_mapper.py` direction-blindness | `tests/test_enhanced_drum_mapper.py` | REG-30 fixed (#471) — melodic-input-produces-no-drums coverage confirmed present. |
| `arranger/voice_allocator.py` DPCM catalog ids | `tests/test_voice_allocator.py` | REG-32 fixed (#472) — tests now assert catalog-resolved ids via a real fixture (`tests/fixtures/test_dpcm_index.json`), not raw positional slots; explicit regression comments cite #445/DPCM-2026-08-21-2. |
| `exporter/exporter_famistudio.py` SEQUENCE↔PATTERN consistency | `tests/test_famistudio_export.py` | REG-34 fixed (#473). |
| Jukebox export (`export_song_bank_bytecode`) | `tests/test_ca65_export.py::TestExportSongBankBytecode` (18 tests, up from ~14) | This session added 9 new tests for #505/#506/#509/#511/#512 (lazy-generator support, DPCM guard, song-identified errors, song_count both-direction mismatch). **One of the 9 is a weak assertion** — see REG-38. |
| `nes/visualizer.py` (new module, not in the last audit's map) | `tests/test_visualizer.py` | 100% line coverage (13 tests), confirmed this run. No finding. |
| `nes/song_bank.py` | `tests/test_song_bank.py` (30 tests, up from ~15) | 92% coverage; misses are `debug_size_info` (dead/dev-only method, not a regression finding — cross-ref `/audit-tech-debt`) and a couple of `add_song`/`import_bank` guard branches already covered by 9 sibling `test_import_bank_*_raises_clear_error` tests of the same shape — not flagged individually. |
| Fixture hygiene (REG-36's target, `test_ca65_export.py`) | same | REG-36 fixed (#475); this session's own 9 new tests in the same file all use the existing `self.temp_dir` fixture (verified via re-read, no bare `Path("test_*.asm")` reintroduced). |
| Everything else (`tracker/`, `mappers/`, `compiler/`, `nes/emulator_core.py`, `config/`, `debug/`) | per 2026-08-21 map | No commits touched these modules' source since 2026-08-21 except `nes/emulator_core.py` (#481, same-pitch-retrigger fix) and `nes/audio_engine.asm`/`tracker/pattern_detector_parallel.py`/`tracker/pattern_detector.py` (all already re-verified with regression tests in this session's earlier performance and exporters audits) — unchanged coverage picture. |

No subsystem in `_audit-common.md`'s project layout lacks a test module.

## Verification of prior findings (all hold)

- **REG-30 (#471), REG-32 (#472), REG-34 (#473), REG-35 (#474), REG-36 (#475)**: all
  CLOSED on GitHub; re-read each fix's target code/tests directly rather than trusting
  the closed label — all five genuinely landed with the suggested tests present and
  passing.
- **REG-31** (stranded #377 fix): the underlying defect was independently re-fixed and
  merged as `#485` (`934b597`, 2026-08-22) with its own three regression tests, which
  are on master and pass. Not the same commit the 2026-08-21 audit expected
  (`c4894d2` was apparently abandoned in favor of a fresh fix), but the net effect —
  guard present, tests present, both on master — is what mattered.
- **REG-33** (untested `run_song_build` failure branches): `#486`/`#467` added exactly
  the suggested tests (`test_capacity_failure_exits_cleanly_not_raw_traceback`,
  `test_compile_failure_exits_cleanly_not_raw_traceback`,
  `test_prepare_project_falsy_return_exits_with_prepare_error_not_compile`,
  `test_validation_failure_restores_a_preexisting_good_rom`, and siblings). Confirmed
  via re-reading `TestRunSongBuild`: 17 tests now cover every failure branch REG-33
  named — except a small residual tail found fresh this run (REG-37 below).

## Findings

### REG-37: `run_song_build`'s catch-all exception handler, verbose-traceback printing, and successful-rebuild backup cleanup remain untested
- **Severity**: LOW
- **Dimension**: 1 (untested subsystem) + 3 (round-trip gap on a historically-buggy control-flow path)
- **Location**: `main.py:1105-1121` — `except MIDI2NESError as e:` (`:1105-1110`, the `if verbose: traceback.print_exc()` branch at `:1107-1109` untested), `except Exception as e:` (`:1111-1116`, the entire branch untested), `finally:` block's `elif backup_path: backup_path.unlink(missing_ok=True)` (`:1120-1121`, the successful-rebuild-over-a-pre-existing-ROM cleanup path)
- **Status**: NEW
- **Description**: `TestRunSongBuild` (17 tests) now covers every *named* failure mode
  from REG-33 (capacity, prepare, compile, validate) — each raising a typed
  `MIDI2NESError` subclass, caught by the `except MIDI2NESError` branch. But:
  (a) every test in the class uses the fixture default `verbose=False`
  (`_args()`'s `defaults` dict, `tests/test_main.py:1979`), so the `if verbose:
  traceback.print_exc()` lines under *both* except branches have never executed;
  (b) no test raises a plain (non-`MIDI2NESError`) exception from inside the `try`
  block, so the generic `except Exception as e: print(f"[ERROR] Unexpected failure
  building jukebox ROM: {e}")` catch-all — the exact backstop meant to prevent a raw
  traceback from ever reaching the user on an exception type nobody anticipated — has
  itself never been exercised; (c) no test has both a pre-existing `output_rom` (so
  `backup_path` is truthy) *and* a successful build, so the `elif backup_path:
  backup_path.unlink(missing_ok=True)` success-path cleanup line is unreached — the
  suite has never proven a successful rebuild actually removes its backup file rather
  than leaving a stale `.nes.backup` behind forever.
- **Evidence**: `python -m pytest tests/test_main.py -k RunSongBuild --cov=main
  --cov-report=term-missing` (scoped to this class only) reports `1108-1109,
  1112-1116, 1121` in the Missing list. `grep -n "verbose=True" tests/test_main.py`
  inside the `TestRunSongBuild` region returns nothing; `grep -n "output_rom.write_bytes"`
  matches only the two validation-failure tests, both of which fail the build (so
  `build_succeeded` stays `False` and the `if not build_succeeded:` branch runs, not
  the `elif backup_path:` one).
  Same shape as REG-33 — one control-flow region, several still-uncovered edges after
  the main branches were filled in.
- **Impact**: Low today: the catch-all is defense-in-depth (every currently-reachable
  failure is already a typed `MIDI2NESError`), and a leaked `.nes.backup` file is a
  cosmetic annoyance, not a correctness bug. But this is exactly the kind of control
  flow that has broken before on this path (`#486`/PIPE-2026-08-22-2, the backup/
  restore contract itself was a MEDIUM finding two audits ago) — a future refactor
  that lets a bare `KeyError`/`AttributeError` escape `build_and_validate_rom`, or a
  typo in the cleanup condition, would ship silently.
- **Related**: REG-33 (2026-08-21, same location, now mostly closed); `#486`/
  PIPE-2026-08-22-2 (the fix this control flow implements).
- **Suggested Fix**: Three small additions to `TestRunSongBuild`: (1) a test with
  `verbose=True` and any failure mode already covered (e.g. compile failure),
  asserting `traceback.print_exc()` was called (patch `main.traceback.print_exc` or
  assert multi-line output); (2) a test making `build_and_validate_rom` raise a plain
  `RuntimeError` (not a `MIDI2NESError` subclass) and asserting the
  `"[ERROR] Unexpected failure building jukebox ROM: ..."` message, not a raw
  traceback; (3) a test with a pre-existing `output_rom` and a fully mocked-successful
  build, asserting the `.nes.backup` file no longer exists afterward.

### REG-38: A laziness test added this session can't actually distinguish lazy consumption from eager materialization — the property it claims to pin is proven only by two sibling tests, not by itself
- **Severity**: LOW
- **Dimension**: 2 (weak assertion)
- **Location**: `tests/test_ca65_export.py:1128-1158`
  (`test_generator_songs_are_pulled_one_at_a_time_not_materialized_upfront`, added by
  this session's `394cddb`/#505 commit)
- **Status**: NEW (self-review of this session's own work)
- **Description**: The test builds a generator that appends to `yielded_so_far` before
  each `yield`, runs `export_song_bank_bytecode` to completion, and asserts
  `yielded_so_far == [1, 2, 3, 4]`. But this final-state assertion cannot distinguish
  "the exporter pulled one song at a time, interleaved with building each song's
  bytecode" (the property `#505`/PERF-B-02 actually fixed) from "the exporter (or
  something upstream) fully drained the generator into a list *before* processing
  anything" — both produce the identical end state `[1, 2, 3, 4]`. The test's own
  docstring/inline comment (written by this session, honestly) already flags this:
  *"What this actually pins is the loop shape... proven by the multi-song generator
  producing the correct final asm output above and this generator being fully drained
  (4 songs) only because the export loop pulled all 4, not because something forced
  it eagerly."* That's a description of what the test *can't* prove, serving as a
  built-in admission of the gap. The actual laziness property — that a later song is
  never pulled once an earlier one fails — IS rigorously proven by two sibling tests
  added in the same commit batch:
  `test_bank_overflow_on_generator_input_stops_before_later_songs_are_pulled`
  (`:1160-1191`) and `test_dpcm_bearing_song_stops_before_later_songs_are_pulled`
  (`:1248-1268`, added by the follow-up #509 commit), both of which *do* have a
  discriminating assertion (`pulled == ['big']`/`['dpcm']`, not `['big', 'never']`).
  So the overall claim in the PR/commit message ("proven lazy") is true and backed by
  real evidence — this one test just isn't where that evidence lives, despite its name
  claiming otherwise.
- **Evidence**: Re-read `tests/test_ca65_export.py:1128-1158`; the only assertion is
  `self.assertEqual(yielded_so_far, [1, 2, 3, 4])` after the full call returns — no
  interleaving check.
- **Impact**: None today — the property is real and covered by its sibling tests. But
  this specific test would stay green through a regression that reintroduced eager
  `list(songs)` materialization inside `export_song_bank_bytecode` (as long as the
  count still matched), silently losing its stated purpose while still reading as
  "laziness is tested" in the suite.
- **Related**: `#505`/PERF-B-02 (the fix this test was meant to pin);
  `test_bank_overflow_on_generator_input_stops_before_later_songs_are_pulled` and
  `test_dpcm_bearing_song_stops_before_later_songs_are_pulled` (the tests that
  actually carry this weight).
- **Suggested Fix**: Either strengthen it to assert interleaving (patch
  `CA65Exporter._build_song_bytecode` to also append to a shared order-tracking list,
  and assert the merged sequence alternates `yield, build, yield, build, ...` rather
  than `yield*4, build*4`), or delete it as redundant with the two overflow-style
  tests and note in the commit that laziness is proven there instead.

## Prioritized backlog

1. **REG-37** (LOW) — round out `TestRunSongBuild`'s three remaining untested tail
   branches (verbose traceback, generic exception catch-all, success-path backup
   cleanup). Cheap: three small test additions to an already-well-structured class.
2. **REG-38** (LOW) — either strengthen or delete the one weak laziness test; the
   property itself is already safe.

Both findings are LOW and neither guards a currently-known live bug — this audit's
overall conclusion is that the test suite is in materially better shape than the last
audit found it: all eight 2026-08-21 findings (REG-30 through REG-36, plus the two
MEDIUM carries REG-31/REG-33) are now genuinely fixed with real regression tests, the
CC65-gated suites remain skip-free, and this session's own ~14 new tests (across the
song-build-memory and exporters-DPCM-guard fix batches) are of good quality apart from
the one noted above.

## Suggested next step

```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-08-23.md
```
