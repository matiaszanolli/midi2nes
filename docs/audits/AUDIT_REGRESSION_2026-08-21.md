# Regression / Test-Hygiene Audit — 2026-08-21

Scope: full test-suite health sweep per `.claude/commands/audit-regression/SKILL.md`,
against master @ `949f0c6`. The code delta since the last regression audit
(`AUDIT_REGRESSION_2026-08-07.md`) is two commits: `8ea7ac3` (jukebox fixes for
REG-27/REG-28 + their regression tests) and `ffccf51` (drum-mapper `volume`-key fix +
tests). `949f0c6` touches only audit-skill prose.

Cross-audit context (verified independently on this tree, not taken on faith): today's
suite found two live regressions the test suite failed to catch — `ffccf51` un-gated
`EnhancedDrumMapper.map_drums`'s channel-blind scan (**PIPE-2026-08-21-1**, CRITICAL),
and the #377 wrong-stage-JSON guard fix was never merged (**PIPE-2026-08-21-2**, HIGH).
Both underlying defects are deduped against those IDs; the findings below cover the
test-suite gaps that let them ship/persist.

**Methodology note**: the full-suite `--cov` sweep (`-m "not slow"`) was launched but
stalled around the 73% mark (in the alphabetical `test_m*`–`test_p*` region, where
coverage instrumentation multiplies the already-slow pattern tests) and was killed
per the no-unscoped-runs policy rather than relaunched. The coverage map below
therefore combines: (a) the aborted run's first ~73% — **all green, exactly one skip**
(a platform-gated Unix/Windows pair in `tests/test_nes_project_builder.py`); (b) fresh
*scoped* runs of every anchor suite past that point (all pass, zero skips, toolchain
present at `/usr/bin/ca65`/`/usr/bin/ld65`); and (c) the 2026-08-07 report's per-module
coverage figures as baseline where no code changed since (only `8ea7ac3`/`ffccf51`
touched code). Suite size: 1230 tests collected across 62 `test_*.py` files.

## Coverage map

| Subsystem | Test module(s) | Status this run |
|---|---|---|
| `dpcm_sampler/enhanced_drum_mapper.py` | `tests/test_enhanced_drum_mapper.py` (31 tests) | Changed by `ffccf51`; new tests are drum-positive only — **direction-blind, see REG-30** |
| `main.py` step-by-step guards (`run_frames`/`run_export`/`run_detect_patterns`) | `tests/test_main.py` | Wrong-stage-input rejection has **zero coverage on master** — the tests exist only on an unmerged branch, see REG-31 |
| `main.py:run_song_build` | `tests/test_main.py::TestRunSongBuild` (8 tests, all pass) | Scoped `--cov=main` re-measured today: failure branches `999-1001, 1008-1010, 1019-1020, 1024-1025` still uncovered — REG-29 carried, see REG-33 |
| `arranger/voice_allocator.py` DPCM slots | `tests/test_voice_allocator.py` | Tests pin slot ids 0/1 as expected values; nothing crosses to the packer — see REG-32 |
| `exporter/exporter_famistudio.py` | `tests/test_famistudio_export.py` (incl. `TestFamiStudioGoldenBytes`) | Golden fixture caps at frame 2 (tail branch only); SEQUENCE↔PATTERN consistency unasserted — see REG-34 |
| Jukebox export/build (`export_song_bank_bytecode`, `prepare_project(song_count=…)`) | `tests/test_ca65_export.py::TestExportSongBankBytecode`/`::TestJukeboxCompilationIntegration`, `tests/test_nes_project_builder.py::TestJukeboxSongCount` | REG-27/REG-28 fixes verified landed with real regression tests (segment-placement assertion + 1-song real-compile); 3/3 jukebox compile tests pass. Split CLI `prepare`/`compile` route untested — see REG-35 |
| CC65-gated suites | `tests/test_ca65_export.py` compile classes, `tests/test_rom_validation_integration.py`, `tests/test_e2e_pipeline.py` | Scoped runs today: 17/17, 11/11, 12/12 pass, **zero skips** (`-rs`) — REG-10/11/26 gates hold; `conftest.py:19,35-43` still a real `shutil.which` gate |
| `tracker/pattern_detector_parallel.py` | `tests/test_pattern_detector_parallel.py` | 12/12 pass today (scoped) — REG-06 determinism tie-break holds |
| Golden-bytes anchors | `tests/test_exporter_integration.py::TestCA65GoldenBytes`, `tests/test_famistudio_export.py::TestFamiStudioGoldenBytes` | Present and passing (REG-05/REG-14 hold); no bare `assertIn("PATTERNS")` anywhere (REG-20 holds) |
| Everything else (`tracker/`, `mappers/`, `compiler/`, `nes/`, `arranger/`, `config/`, `debug/`) | per 2026-08-07 map | Unchanged code since 08-07 baseline (71–96% module coverage there); first ~73% of today's aborted sweep all green |

No subsystem in `_audit-common.md`'s project layout lacks a test module.

## Findings

### REG-30: Drum-mapper tests are direction-blind — `ffccf51`'s tests prove drums map, but nothing asserts melodic input maps to NOTHING, so the channel-blind phantom-DPCM regression shipped green
- **Severity**: HIGH
- **Dimension**: 1 (untested path) + 2 (weak assertions)
- **Location**: `tests/test_enhanced_drum_mapper.py:85-125` (the two tests added by `ffccf51`); code under test `dpcm_sampler/enhanced_drum_mapper.py:294-360` (`map_drums` — no channel filter anywhere in the loop); integration entry `tracker/track_mapper.py` (`map_drums_to_dpcm` receives the full parsed input)
- **Status**: NEW (underlying defect: Existing — **PIPE-2026-08-21-1** / DPCM-2026-08-21-1, CRITICAL, not re-filed here)
- **Description**: `ffccf51` fixed DP-DPCM-12 (the `velocity`-only guard that made `map_drums` dead on real `'volume'`-keyed input) and added exactly two tests — both feeding drum-shaped fixtures (notes 36/38 under key `9`). Neither the new tests nor any of the other 29 tests in the file feed a *melodic* event stream and assert it produces **no** drum output; nor does any integration test run a melodic MIDI through `parse → assign_tracks_to_nes_channels` asserting `dpcm`/`noise` stay empty. Because `map_drums` scans every track's every event with no `channel == 9` filter, un-deadening it turned every melodic note-on into a phantom GM-percussion lookup — and the suite stayed green. The positive test itself is also weak: it asserts only `len(dpcm_events) + len(noise_events) == 2`, so it cannot distinguish DPCM from noise routing nor verify sample identity.
- **Evidence**: `grep -i melodic tests/test_enhanced_drum_mapper.py` → no matches; the two `ffccf51` tests assert combined counts only (`tests/test_enhanced_drum_mapper.py:104,124`). PIPE-2026-08-21-1's live repro: `test_midi/simple_loop.mid` (channel 0, zero percussion) → `map` emits `dpcm: 12 events`; the full pipeline packs 3 DPCM samples into a drumless ROM with no warning. All 31 tests in the file pass on this tree.
- **Impact**: A CRITICAL silent-song-corruption defect on effectively every legacy-mode melodic build was undetectable by the suite; the same blindness will hide any future regression in the drum/melody routing boundary. This is the exact false-positive direction DP-DPCM-11 (2026-08-07) predicted would need a test once DP-DPCM-12 was fixed.
- **Related**: PIPE-2026-08-21-1, DPCM-2026-08-21-1, DP-DPCM-11/12 (`docs/audits/AUDIT_DPCM_2026-08-07.md`), `ffccf51`
- **Suggested Fix**: Two tests. (1) Unit: in `tests/test_enhanced_drum_mapper.py`, feed `map_drums` a melodic stream (`{0: [{'note': 60, 'volume': 100, 'frame': 0, 'channel': 0}, …]}`, notes 60/64/67) and assert `([], [])` — red today, green once the channel-9 filter lands. (2) Integration: parse `test_midi/simple_loop.mid` through `assign_tracks_to_nes_channels` and assert `nes_tracks['dpcm'] == []` and `nes_tracks['noise'] == []`. Also strengthen `test_map_drums_reads_volume_key_not_just_velocity` to assert *which* list each event landed in and its resolved `sample_id`.

### REG-31: #377's wrong-stage-JSON guard AND its three regression tests are stranded on an unmerged branch — the issue is closed, master is unguarded and untested
- **Severity**: MEDIUM
- **Dimension**: 3 (round-trip gaps) + 4 (stale/wrong-target — tracker state contradicts the tree)
- **Location**: `main.py:248,646,732` (`load_json_stage(args.input, [], …)` — empty `required_keys`, no `expected_any_of` parameter exists on master at `main.py:76-105`); stranded fix+tests: branch `fix/issue-377-wrong-stage-json-guard` commit `c4894d2` (adds `test_run_frames_wrong_stage_input_rejected`, `test_run_export_wrong_stage_input_rejected`, `test_run_detect_patterns_wrong_stage_input_rejected` to `tests/test_main.py`)
- **Status**: Regression of #377 (closed 2026-08-05 "Fixed in c4894d2"; `git merge-base --is-ancestor c4894d2 master` fails — re-verified this run). Underlying defect deduped to **PIPE-2026-08-21-2**, not re-filed.
- **Description**: The guard rejecting parse-stage JSON fed to `frames`/`export`/`detect-patterns` was written, tested (three regression tests), and the issue closed — but the branch was never merged, so master still silently emits empty frames/music.asm on wrong-stage input, and the suite has zero coverage of the rejection behavior. The only similarly-named test on master (`tests/test_main.py:995`, `test_run_export_wrong_stage_patterns_file`) covers the `--patterns` argument, not the stage-input guard. Process lesson: a closed issue's fix commit must be ancestry-checked, and its regression tests are only protection once they run on master.
- **Evidence**: `grep -n "expected_any_of\|NES_CHANNEL_KEYS" main.py tests/test_main.py` → no matches on master; branch commit `c4894d2` shows `tests/test_main.py | 84 ++++…` with the three test defs. PIPE-2026-08-21-2's live repro: parse-stage JSON → `frames` → `{}` output, exit 0.
- **Impact**: The documented step-by-step debugging path can still silently produce an empty (silent) ROM; any future fix has no test guarding it until `c4894d2`'s tests land. Gap on a path with a known live bug → MEDIUM per `_audit-severity.md`.
- **Related**: #377, PIPE-2026-08-21-2, #120/SAFE-01
- **Suggested Fix**: Merge or re-land `c4894d2` (guard + all three tests) onto master. When closing it, verify with `git merge-base --is-ancestor`. Optionally add the ancestry check to the fix-issue workflow.

### REG-32: Arranger DPCM tests pin the raw slot ids as the expected values — codifying the very id-space mismatch that makes every `--arranger` kick play the wrong sample, with no test crossing to the packer
- **Severity**: MEDIUM
- **Dimension**: 4 (tests asserting now-known-wrong behavior) + 2 (weak assertions)
- **Location**: `tests/test_voice_allocator.py:35-55` (`assertEqual(self.va._allocate_dpcm(…), 0)` / `, 1)` — slot ids asserted as ground truth); no test in `tests/test_arranger*.py` or `tests/test_voice_allocator.py` references `dpcm_sample_map` or a packed sample filename (grep-verified)
- **Status**: NEW (underlying defect: Existing — **ARR-2026-08-21-1** = DPCM-2026-08-21-2, HIGH, regression of #87/ARR-04; not re-filed here)
- **Description**: The arranger emits slot numbers (0 = kick, 1 = snare) that the pack stage interprets as *catalog* ids — in the shipped `dpcm_index.json`, id 0 is "(Konami, Contra Force) Hit 1" and id 1 is a kick, so every `--arranger` kick plays a generic hit and every snare plays a kick. The unit tests assert the slot values themselves (so they pass — and will need touching when the fix lands), and no test anywhere follows an arranger drum through `pipeline_integration` → `get_dpcm_sample_ids_from_frames` → packed filename. The suite is green while the audible output is wrong on every `--arranger` build with kick/snare. Distinct from ARR-2026-08-21-5 (which covers allocator floor/clamp edge cases, filed by today's arranger audit — not duplicated here).
- **Evidence**: `grep -rln dpcm_sample_map tests/` matches 7 files, none of them arranger tests; `tests/test_voice_allocator.py:38-42` pins ids 0/1. Catalog id mapping per DPCM-2026-08-21-2 (`kick` = catalog 1318, `snare` = 1620).
- **Impact**: A HIGH wrong-audio defect is invisible to the suite, and the existing assertions actively entrench the wrong contract. Any fix must update these tests, and without an end-to-end identity test the same class of id-space drift (the legacy path's long-fixed D-02/#65) can recur unobserved.
- **Related**: ARR-2026-08-21-1, DPCM-2026-08-21-2, #87, #65, ARR-2026-08-21-5 (sibling test-gap finding, different scope)
- **Suggested Fix**: Add an end-to-end test: arrange a channel-9 kick+snare MIDI (or synthetic events) via `arrange_for_nes`, run the frames through the pack-stage id extraction, and assert the resolved catalog entries are the curated `kick`/`snare` samples (e.g. packed filename endswith `kick.dmc`) — red today. Rewrite the slot-id unit assertions in terms of the corrected contract (catalog ids or a `dpcm_sample_map`) when the fix lands.

### REG-33: `run_song_build`'s four real-failure branches remain uncovered — REG-29 carried, now compounded by the unchecked `prepare_project` return
- **Severity**: MEDIUM
- **Dimension**: 1 (untested subsystem) + 3 (round-trip gaps)
- **Location**: `main.py:999-1001` (export ValueError), `:1008-1010` (capacity ValueError), `:1019-1020` (compile failure), `:1024-1025` (validate failure); also `:1014` (`builder.prepare_project(...)` return value ignored — cross-ref SAFE-2026-08-21-5). Tests: `tests/test_main.py:1617` (`TestRunSongBuild`, 8 tests)
- **Status**: Existing — REG-29 in `docs/audits/AUDIT_REGRESSION_2026-08-07.md` (never filed on GitHub), re-measured this run
- **Description**: Every `TestRunSongBuild` test that reaches the compile stage mocks `NESProjectBuilder`/`compile_rom`/`validate_rom` to succeed. Re-measured today with scoped coverage (`pytest tests/test_main.py -k RunSongBuild --cov=main`): 8/8 pass and lines 999-1001, 1008-1010, 1019-1020, 1024-1025 are still in the Missing list — no test has ever observed `run_song_build` handling a failed export, capacity check, compile, or validation. `8ea7ac3` fixed the jukebox defects but did not add these CLI-level tests. The gap now also hides SAFE-2026-08-21-5: `prepare_project`'s return value is ignored at `main.py:1014`, so a prepare failure silently proceeds to compile — a `prepare_project`-returns-False test would have flagged that on day one.
- **Evidence**: Scoped coverage output this run: `main.py … 16% … 999-1001, 1008-1010, 1019-1020, 1024-1025 …` with only `TestRunSongBuild` selected.
- **Impact**: The suite cannot prove `song build` degrades gracefully (clean `[ERROR]` + exit 1, no partial/stale ROM) on any real build failure — the very branches REG-27's live bug exercised in production for a month.
- **Related**: REG-29 (2026-08-07), SAFE-2026-08-21-4/-5, PIPE-2026-08-21-4 (no backup/restore contract — same untested tail)
- **Suggested Fix**: Add `TestRunSongBuild` tests mocking `main.compile_rom` → `False` (assert `SystemExit` + `"[ERROR] Compilation failed"`), `main.validate_rom` → `False` under `skip_validation=False`, `check_mapper_capacity` raising `ValueError`, and `prepare_project` → `False` (the last is red until SAFE-2026-08-21-5's one-line fix lands — file them together).

### REG-34: FamiStudio tests never assert SEQUENCE↔PATTERN consistency, and every fixture dodges the buggy ≥64-frame multi-channel branch — the export is broken for realistic songs while the golden tests pass
- **Severity**: MEDIUM
- **Dimension**: 2 (weak assertions) + 1 (untested branch)
- **Location**: `tests/test_famistudio_export.py:127-197` (`TestFamiStudioGoldenBytes` — fixture `max_frame = 2`, one tail-branch pattern per channel), `:107-124` (the 400-frame side-table test asserts only two negative substrings); code under test `exporter/exporter_famistudio.py:129` (mid-loop pattern key uses **global** `len(patterns)`) vs `:135` (tail key uses per-channel count) vs `:167` (SEQUENCE references per-channel indices), and `:101` (`if str(frame) in events` — int-keyed frames silently export as all rests)
- **Status**: NEW (underlying defects: Existing — **EXP-2026-08-21-2** and **EXP-2026-08-21-3**, filed by today's exporters audit; not re-filed here)
- **Description**: The golden-bytes class (the #232/REG-14 fix) pins exact rows — but only for a 3-frame song, where every channel emits exactly one pattern via the tail branch (`:135`, per-channel counter), never the mid-loop branch (`:129`, global counter). For any song where a channel *after the first* fills a 64-row pattern, the mid-loop key (`pulse2_<global>`) diverges from the SEQUENCE references (`pulse2_0..n`), producing a project whose sequences reference patterns that don't exist. Ironically the suite already *generates* this broken output — `test_dpcm_sample_map_side_table_does_not_crash` builds 400 frames of pulse1+dpcm — but asserts only that two substrings are absent. Nothing anywhere asserts "every name in a SEQUENCE line appears as a PATTERN block", and no test feeds int-keyed frames (valid for the CA65 exporter) to catch the silent all-rests export.
- **Evidence**: `grep -n SEQUENCE tests/test_famistudio_export.py` → no matches; fixture at `tests/test_famistudio_export.py:140-147` (`max_frame` 2); exporter key mismatch read directly at `exporter/exporter_famistudio.py:129/135/167`.
- **Impact**: FamiStudio export is wrong for any multi-channel song ≥ 64 frames — i.e. essentially all real exports — and the suite cannot see it. The same self-consistency assertion would guard all future pattern-splitting changes.
- **Related**: EXP-2026-08-21-2, EXP-2026-08-21-3, #232/REG-14, #339/REG-20
- **Suggested Fix**: Add a test exporting multi-channel frames with ≥ 64 frames per channel (e.g. pulse1+pulse2+triangle over 130 frames) asserting (a) every SEQUENCE-referenced name has a matching `PATTERN "<name>"` block and (b) the per-channel pattern count equals `ceil(frames/64)`. Add a second test that int-keyed frames either raise or export identically to their str-keyed twin.

### REG-35: The CLI split `prepare`/`compile` route has no jukebox test — the music.asm marker is written but never consumed, and no test drives the documented two-step flow on a jukebox export
- **Severity**: MEDIUM
- **Dimension**: 3 (round-trip gaps) + 1 (untested path)
- **Location**: `tests/test_main.py` (`TestRunPrepare`/`TestRunCompile` — no jukebox-asm case; grep for `export_song_bank_bytecode` in the file matches only `TestRunSongBuild` mocks); defect location per MAP-2026-08-21-1: `nes/project_builder.py` (`prepare_project` never reads the jukebox marker `export_song_bank_bytecode` embeds in music.asm; only the explicit `song_count=` parameter — which the CLI `prepare` subcommand never passes — triggers `JUKEBOX_BUILD`)
- **Status**: NEW (underlying defect: Existing — **MAP-2026-08-21-1**, filed by today's mappers audit; not re-filed here)
- **Description**: `run_song_build` works because it passes `song_count=len(songs)` in-process, but the documented step-by-step route (`main.py prepare` on a jukebox music.asm, then `main.py compile`) fails at ld65 with 8 unresolved externals — the same failure signature REG-27 had — because the CLI path has no way to learn the file is a jukebox export. No test exercises `prepare`/`compile` (the CLI subcommands or `prepare_project` without `song_count`) on `export_song_bank_bytecode` output, so the suite proves nothing about the split flow the jukebox docs/CLI still offer. This is the third distinct jukebox linking/placement defect to ship in this feature; each lived in a path combination no test covered (1-song bank → REG-27; 2+-song segment placement → REG-28; split CLI flow → this).
- **Evidence**: MAP-2026-08-21-1 (live ld65 repro in today's mappers audit); test inventory: `TestJukeboxCompilationIntegration` (3 tests) always calls `prepare_project(..., song_count=N)` directly; `TestRunPrepare`/`TestRunCompile` never use jukebox asm.
- **Impact**: The split debugging flow — the one a user reaches for precisely when the one-shot build misbehaves — hard-fails on every jukebox project with a cryptic linker error, and any fix (marker-sniffing in `prepare_project`) will land untested unless this test exists first.
- **Related**: MAP-2026-08-21-1, REG-27/REG-28 (pattern: jukebox path-combination gaps), #362 (the direct-export analog of marker-driven re-forcing)
- **Suggested Fix**: Add a `requires_cc65`-gated test: `export_song_bank_bytecode` a 2-song bank to music.asm, run `run_prepare` (or `prepare_project` with **no** `song_count`), then `compile_rom`, asserting link success — red until MAP-2026-08-21-1's marker-consumption fix lands. A cheaper non-CC65 companion: assert `prepare_project` on marker-bearing asm emits `JUKEBOX_BUILD = 1` in main.asm.

### REG-36: `test_ca65_export.py` writes 17 scratch `.asm` files into the repo root via CWD-relative paths instead of the shared `temp_dir` fixture
- **Severity**: LOW
- **Dimension**: 6 (fixture & isolation hygiene)
- **Location**: `tests/test_ca65_export.py:203,316,352,402,420,441,469,482,526-527,579,625,647,668,706,735,758` (`Path("test_*.asm")` — resolves against the process CWD, i.e. the repo root under the documented `python -m pytest` invocation)
- **Status**: NEW (distinct from the closed #231/REG-13, which was `test_drum_mapping.py` — that fix holds: `tests/test_drum_mapping.py:21,75-80` now uses `tests/fixtures/` + `tempfile.TemporaryDirectory`)
- **Description**: Seventeen tests across `TestCA65Exporter`-family classes and `TestExportSongBankBytecode` write their exporter output to bare relative paths. Each is wrapped in `try/finally: out.unlink()`, so the steady-state leak #231 had is absent (verified: no `test_*.asm` in the repo root after running the file today) — but the files still transit the repo root: a hard kill between write and `finally` leaves them behind, two tests using the same name would collide under `pytest-xdist`/parallel CI, and a same-named checked-in file would be silently clobbered. `tests/conftest.py` already provides the `temp_dir` fixture these classes ignore.
- **Evidence**: `grep -n 'Path("test_' tests/test_ca65_export.py` → 17 sites; conftest `temp_dir` at `tests/conftest.py:50-54`.
- **Impact**: Hygiene/parallel-safety only on currently-working tests — LOW.
- **Related**: #231/REG-13 (precedent), Dimension 6 of this skill
- **Suggested Fix**: Convert the `unittest.TestCase` classes to create `self.tmp = tempfile.TemporaryDirectory()` in `setUp` (mirroring `TestJukeboxCompilationIntegration`, which already does this) and write outputs under it, dropping the per-test `try/finally` boilerplate.

## Reverified — no regression (not re-filed)

- **REG-27/REG-28** (2026-08-07, jukebox 1-song link failure + per-song CODE_8000 placement): both fixed by `8ea7ac3` *with the exact tests the report specified* — `test_one_song_jukebox_bank_compiles_and_links` (real-compile, `requires_cc65`) and `test_each_songs_instrument_table_lands_in_code_8000_not_a_bank` (segment-placement regex, forces a bank spill so it can't pass by accident). All 3 `TestJukeboxCompilationIntegration` tests pass with the toolchain present.
- **REG-26/#414, REG-10/#128, REG-11/#129** (CC65 gating / masked skips): `tests/conftest.py:19,35-43` still a genuine `shutil.which` gate; scoped runs today: `TestCA65CompilationIntegration` + jukebox class + `test_exporter_integration.py` 17/17, `test_rom_validation_integration.py` 11/11, `test_e2e_pipeline.py` 12/12 — all PASS, zero skips under `-rs`.
- **REG-06/#46** (`ParallelPatternDetector` determinism): 12/12 pass.
- **REG-05/#45, REG-14/#232, REG-20/#339** (golden-bytes anchors, no bare `assertIn("PATTERNS")`): `TestCA65GoldenBytes` + `TestFamiStudioGoldenBytes` present and passing; grep clean.
- **REG-13/#231** (`test_drum_mapping.py` repo-root leak): fix holds; no `invalid.json` in repo root.
- **Skip/xfail hygiene**: no `@unittest.skip`/`xfail` without cause; remaining `pytest.skip` calls are genuine environment gates (CC65 absent, `dpcm_index.json` absent, platform-specific) — none fire in this environment except the platform pair.

## Prioritized backlog (tests to write first, by blast radius)

1. **REG-30** (HIGH) — melodic-negative drum tests (unit + parse→map integration). Guards the shipped CRITICAL PIPE-2026-08-21-1 fix and the whole drum/melody routing boundary.
2. **REG-31** (MEDIUM) — land `c4894d2`'s three wrong-stage-rejection tests by merging the stranded branch; ancestry-check the closure.
3. **REG-32** (MEDIUM) — end-to-end arranger drum identity test (kick resolves to the catalog `kick` sample); rewrite the slot-id pins with the fix.
4. **REG-34** (MEDIUM) — FamiStudio SEQUENCE↔PATTERN self-consistency test on a ≥64-frame multi-channel song + int-keyed-frames parity test.
5. **REG-35** (MEDIUM) — `requires_cc65` split `prepare`/`compile` jukebox test (red until MAP-2026-08-21-1 lands).
6. **REG-33** (MEDIUM) — four failure-branch tests for `run_song_build` (compile/validate/capacity/prepare), filed together with SAFE-2026-08-21-5's fix.
7. **REG-36** (LOW) — migrate `test_ca65_export.py`'s 17 CWD writes onto `temp_dir`.

## Summary

7 findings: **REG-30 (HIGH)**, REG-31/32/33/34/35 (MEDIUM), REG-36 (LOW). The
two headline items are coverage-gap post-mortems of regressions found live by today's
sibling audits (defects deduped to PIPE-2026-08-21-1 and PIPE-2026-08-21-2 — not
re-filed): the drum-mapper suite proves the positive direction only, and a closed
issue's guard + tests never reached master. All eight previously-fixed regression items
re-verified and holding; `8ea7ac3` closed REG-27/REG-28 with real, well-aimed tests.
Full-suite coverage sweep was aborted (stall at ~73% under instrumentation; not
relaunched per policy) — per-module numbers above are scoped re-measurements plus the
unchanged 2026-08-07 baseline.

Suggested next step:
```
/audit-publish docs/audits/AUDIT_REGRESSION_2026-08-21.md
```
