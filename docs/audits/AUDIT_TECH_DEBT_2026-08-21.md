# Tech-Debt Audit — 2026-08-21

Audit type: `/audit-tech-debt` (all 8 dimensions, whole repo)
Baseline: master @ `949f0c6` ("Enhance jukebox engine paths and audit processes")
Prior report: `docs/audits/AUDIT_TECH_DEBT_2026-08-07.md` (TD-31..TD-37; none were filed as issues)
Dedup sources: `/tmp/audit/issues.json` (2 open, both unrelated user questions), all-issue list
(300 issues), and today's 8 sibling reports in `docs/audits/*2026-08-21*.md`.

## Summary

**13 findings: 0 CRITICAL / 0 HIGH / 1 MEDIUM / 12 LOW.**

The tree is in unusually good tech-debt shape for its size: zero TODO/FIXME/HACK/XXX
markers in non-test source, only two (documented, narrow) broad-except sites, a pyflakes
run that is clean apart from two dead locals, and every structural fix from prior cycles
(#131/#132/#133/#134/#135/#136/#137/#380/#406/#412) verified still in place.

The one systemic problem this cycle is **stranded fix branches**: three closed issues'
fixes exist only on unmerged `fix/*` branches, so master still contains the exact debt
their CLOSED state says is gone. Sibling PIPE-2026-08-21-2 found the functional one
(#377, HIGH); this audit adds #352 (a live ~26s `detect-patterns` stall, MEDIUM) and
#346/#347 (dead `tracker/parser.py` + orphaned `src/` NSF scaffolding, LOW). All 13
unmerged branches were classified by content: every other closed issue's fix landed on
master via other commits.

### Findings by dimension

| Dimension | Count | IDs |
|---|---|---|
| 1 — Logic duplication | 3 | TD-40 (new), TD-31, TD-32 (carried) |
| 2 — Dead code & cruft | 5 | TD-38, TD-41, TD-44, TD-45 (new), — |
| 3 — Stale docs & comments | 3 | TD-42, TD-43 (new), TD-33 (carried) |
| 4 — Stale markers | 0 | grep clean in non-test source |
| 5 — Stubs & placeholders | 0 | only the documented NSF stub (#81, existing) |
| 6 — Magic numbers | 1 | TD-36 (carried) |
| 7 — Error-handling debt | 1 | TD-39 (regression, MEDIUM) |
| 8 — Module/function size | 1 | TD-37 (carried, observational) |

### Three highest-leverage cleanups

1. **Re-land the three stranded fix commits** (TD-38, TD-39 here; #377 per
   PIPE-2026-08-21-2). One `git merge` each; restores the invariant that a CLOSED issue
   means fixed-on-master, which every future audit's dedup step depends on.
2. **Extract one shared event-velocity helper** (TD-40): the
   `e.get('velocity', e.get('volume', …))` idiom is copy-pasted at 15 sites across 6
   modules with *inconsistent key precedence and defaults* — the exact drift the user's
   standing no-duplication rule exists to prevent.
3. **Make `run_song_build` reuse `build_and_validate_rom`** (TD-32): kills the duplicated
   capacity→prepare→compile→validate sequence and simultaneously gives the jukebox path
   the single-recovery-point error handling PIPE-2026-08-21-4 (HIGH) asks for.

---

## Findings

### TD-38: Closed #346/#347 fixes never reached master — dead `tracker/parser.py` and orphaned `src/` NSF scaffolding still ship
- **Severity**: LOW
- **Dimension**: 2 (Dead Code & Cruft)
- **Location**: `tracker/parser.py` (whole module); `src/music_driver.s`, `src/nsf_main_driver.s`, `src/nes.inc`; branch `fix/issues-346-347` (commit `197e0e3`)
- **Status**: Regression of #346 and #347 (both CLOSED "Fixed in 197e0e3" — but `git cherry master fix/issues-346-347` shows the commit is not on master, and no equivalent change landed via any other commit)
- **Description**: Commit `197e0e3` deletes `tracker/parser.py` (retargeting its three
  test importers to `tracker.parser_fast`) and removes the unreferenced NSF-player
  scaffolding in `src/`. It exists only on the unmerged branch `fix/issues-346-347`.
  On master, all of it is still present: `tests/test_midi_parser_integration.py:5`,
  `tests/test_integration.py:6`, and `tests/test_pattern_integration.py:6` still import
  `tracker.parser`, and `git ls-files src/` still lists the three `.s`/`.inc` files that
  `grep -rn "music_driver\|nsf_main_driver" --include='*.py'` confirms nothing reads.
- **Evidence**: `ls tracker/parser.py` → exists; `git branch --contains 197e0e3` →
  only `fix/issues-346-347`; issue #347's closing comment says "Fixed in 197e0e3".
- **Impact**: The exact drift risk #346 was filed for (a production-dead parser kept
  alive by tests, silently diverging from the real front-end) persists, while the issue
  tracker says it is gone. Developer-confusion blast radius only; no runtime effect.
- **Related**: PIPE-2026-08-21-2 (same stranded-branch pattern for #377, HIGH), TD-39
  (same pattern for #352). #346/TD-26, #347/TD-27.
- **Suggested Fix**: Merge (or cherry-pick) `197e0e3` onto master. If merging is
  undesirable, reopen #346/#347 so the tracker state is honest.

### TD-39: Closed #352's `DETECTOR_MAX_EVENTS` recalibration never reached master — the measured ~26s sequential-detector stall is still live
- **Severity**: MEDIUM
- **Dimension**: 7 (Error-Handling Debt / latency debt hiding behind a closed issue; cross-dimension: performance)
- **Location**: `tracker/pattern_detector.py:23` (`DETECTOR_MAX_EVENTS = 1000`); branch `fix/issue-352` (commit `e645cc9` sets it to 300)
- **Status**: Regression of #352 (CLOSED "Fixed in e645cc9 (branch fix/issue-352)"; the branch was never merged and `git log -L` on the line shows master's `1000` is unchanged since the #100/#99 fix)
- **Description**: #352's closing analysis measured the sequential
  `PatternDetector.detect_patterns` path (inherited unchanged by
  `EnhancedPatternDetector`, used by the `detect-patterns` subcommand and the pipeline's
  sequential fallback) at ~26s for n=1000 — the current cap — and recalibrated the cap
  to 300 (~2.5s worst case) because the constant's own stated purpose is to bound
  worst-case latency. That recalibration lives only on the unmerged branch; master still
  caps at 1000, so the user-facing stall the issue was closed for remains reproducible.
- **Evidence**: `tracker/pattern_detector.py:23` reads `DETECTOR_MAX_EVENTS = 1000`;
  `git show fix/issue-352:tracker/pattern_detector.py` reads `= 300`; issue #352's final
  comment documents the 26s→2.86s live measurement and the "hangs at n≈1000" root cause.
- **Impact**: `python main.py detect-patterns …` (a documented step-by-step debugging
  command) and the parallel detector's fallback path can stall ~26s on inputs at the
  cap. Workaround exists (default pipeline uses `ParallelPatternDetector`,
  `MAX_PATTERN_EVENTS=15000` sampling path, unaffected) → MEDIUM, not HIGH.
- **Related**: TD-38, PIPE-2026-08-21-2 (the stranded-branch cluster); #352/REG-21;
  #355/REG-22 and #394/REG-24 (the *test-suite* handling of the same slowness — marking
  tests `slow` did not fix the production cap).
- **Suggested Fix**: Merge/re-land `e645cc9` (a one-line constant change plus its test).

### TD-40: `velocity`/`volume` dual-key event read copy-pasted at 15 sites across 6 modules — with inconsistent precedence and defaults
- **Severity**: LOW
- **Dimension**: 1 (Logic Duplication)
- **Location**: `nes/emulator_core.py:32,37,40,72,86,94,157,211,229` (velocity-first, default 0); `tracker/track_mapper.py:16,29,302` (volume-first, default 0); `tracker/pattern_detector.py:615` (volume-first, default **100**); `arranger/pipeline_integration.py:196` (velocity-first, default **100**); `dpcm_sampler/enhanced_drum_mapper.py:324` (velocity-first, default 0)
- **Status**: NEW (the idiom predates this cycle, but `ffccf51` added the 15th site and
  a comment claiming a uniformity that does not exist)
- **Description**: Parsed events carry `volume` (from `tracker/parser_fast.py`) while
  synthetic/legacy events carry `velocity`, so every consumer defensively reads both.
  The fallback is hand-rolled at each site and has already diverged on both axes:
  key precedence (velocity-first in `nes/`/`dpcm_sampler/`/`arranger/`, volume-first in
  `tracker/`) and missing-key default (0 at 13 sites, 100 at 2). The comment added in
  `ffccf51` (`dpcm_sampler/enhanced_drum_mapper.py:318-322`) says it matches "the
  defensive dual-key idiom used everywhere else in this codebase (e.g.
  tracker/track_mapper.py…)" — but it wrote velocity-first while `track_mapper` is
  volume-first, demonstrating the drift is already invisible to authors.
- **Evidence**: `grep -rn "get('velocity'.*get('volume'\|get('volume'.*get('velocity'" --include='*.py' .`
  (excluding tests) returns the 15 sites above.
- **Impact**: An event carrying both keys with different values, or missing both, is
  interpreted differently per module (note kept vs dropped; loudness 0 vs 100). Today's
  producers appear to emit exactly one of the keys, so this is drift *risk*, not a live
  bug — hence LOW.
- **Related**: `ffccf51` (site 15); DPCM-2026-08-21-1 / PIPE-2026-08-21-1 (the same
  commit's CRITICAL functional bug — separate root cause, reported by siblings).
- **Suggested Fix**: Add one helper (e.g. `core/events.py: event_velocity(e, default=0)`)
  with a single documented precedence, and migrate all 15 sites; the 2 default-100 sites
  should justify or drop their divergent default at migration time.

### TD-41: `nes/linker_mmc3.cfg` is an orphan — and a stale 128KB-era snapshot that contradicts the live 512KB config generator
- **Severity**: LOW
- **Dimension**: 2 (Dead Code & Cruft; cross-dimension: 3 — the file's own header comment is doc-rot)
- **Location**: `nes/linker_mmc3.cfg` (tracked; header: "MMC3 Linker Configuration (128KB PRG-ROM)")
- **Status**: NEW (long noted as "Orphan cfg" in `_audit-common.md`'s layout map, but
  never reported in any prior audit report nor filed as an issue — verified against all
  `docs/audits/*.md` and the 300-issue list)
- **Description**: `grep -rn linker_mmc3` across the tree finds no reference outside
  audit-skill prose — no Python module, build script, or test reads it; every mapper
  emits `nes.cfg` programmatically via `generate_linker_config()`. It also fails the
  "deliberately-kept reference copy" test: it describes a **128KB** PRG layout, while
  `mappers/mmc3.py` generates a **512KB**, 60-swap-bank (`SWAP_BANK_COUNT = 60`,
  8KB windows) configuration — so as a reference it is actively misleading.
- **Evidence**: `head nes/linker_mmc3.cfg` → "128KB PRG-ROM"; `mappers/mmc3.py:15-16,32`
  → 60 banks, `0x2000` windows, `512 * 1024`. Zero code references.
- **Impact**: A newcomer editing linker behavior may edit this file and see no effect,
  or trust its 128KB layout. Developer-confusion blast radius only.
- **Related**: NH-28/#203 (`nes/mmc3_init.asm`, the same orphaned-file class, since
  deleted); `_audit-common.md:34`.
- **Suggested Fix**: Delete it (git history preserves it). If kept intentionally, fix
  its header to match the generated 512KB layout and add a comment stating it is a
  non-authoritative reference copy — but deletion is the better fit given it has
  already gone stale once.

### TD-42: `CLAUDE.md` cites `PROJECT_STATUS.md`, which was deleted
- **Severity**: LOW
- **Dimension**: 3 (Stale Documentation)
- **Location**: `CLAUDE.md:277` ("✅ Fully operational end-to-end pipeline (see PROJECT_STATUS.md)")
- **Status**: NEW
- **Description**: `PROJECT_STATUS.md` was removed in commit `419885e` ("Codebase
  cleanup.") but the Project Status section of `CLAUDE.md` still points readers (and
  every Claude session, via the system prompt) at it.
- **Evidence**: `ls PROJECT_STATUS.md` → no such file; `git log --oneline -- PROJECT_STATUS.md`
  → last touch is the deletion commit.
- **Impact**: Dangling pointer in the most-read doc in the repo. Cosmetic.
- **Related**: TD-43 (other doc/prose rot found this cycle).
- **Suggested Fix**: Drop the parenthetical or point it at `docs/ROADMAP.md`, which is
  current (its "Song banks → ROM … ✅ v1 shipped" section matches the code).

### TD-43: audit-tech-debt SKILL.md prose is stale — describes fixed #135 as "still-open" and understates `exporter_ca65.py`'s size by 240 lines
- **Severity**: LOW
- **Dimension**: 3 (Stale Documentation)
- **Location**: `.claude/commands/audit-tech-debt/SKILL.md:116-118` (Dimension 7 text) and `:130` ("~1445 lines total")
- **Status**: NEW — `/audit-sync` candidate
- **Description**: Two claims no longer match master:
  1. "A concrete, still-open instance: `utils/profiling.py` has a bare `except:` clause
     (line 120) … (TD-10/#135)". #135 is CLOSED and the fix **did** land on master:
     `grep -n "except" utils/profiling.py` shows no bare `except:` anywhere — only
     narrow `(psutil.NoSuchProcess, psutil.AccessDenied)` and a commented
     `except Exception` (`:139`,`:145`) that explicitly lets
     `KeyboardInterrupt`/`SystemExit` propagate; the module docstring (`:19`) refers to
     the bare except in the past tense.
  2. "`exporter_ca65.py` is now ~1445 lines total" — the file is 1685 lines. The growth
     is the jukebox feature (`_build_song_bytecode` + `export_song_bank_bytecode`, added
     in `c864426`/`8ea7ac3`), not a re-inlining regression, but the number sends the
     next auditor chasing a phantom 240-line change.
- **Evidence**: See locations; verified this cycle as part of the Dimension 7/8 passes.
- **Impact**: Future tech-debt audits either re-report a fixed bug or burn time
  disproving stale prose. No runtime impact.
- **Related**: Same stale-skill-prose class as TEMPO-2026-08-21-1, PAT-2026-08-21-7,
  and the arranger/dpcm/performance drift noted by today's siblings — those cover
  *their* skill files; this finding covers only `audit-tech-debt/SKILL.md`. #135/TD-10.
- **Suggested Fix**: Run `/audit-sync` over `audit-tech-debt/SKILL.md`: rewrite the
  Dimension 7 example as a verify-the-fix note and refresh the Dimension 8 line counts
  (1685 for `exporter/exporter_ca65.py`, with the jukebox methods as the explanation).

### TD-44: `input.mid` — a 31KB third-party copyrighted MIDI tracked at the repo root, and it isn't the file README's benchmarks describe
- **Severity**: LOW
- **Dimension**: 2 (Dead Code & Cruft; cross-dimension: 3 — README mismatch)
- **Location**: `input.mid` (repo root, tracked); `README.md:37,44` ("51KB, 15 tracks, 13,362 events")
- **Status**: NEW
- **Description**: The tracked `input.mid` is a third-party sequenced song (track names:
  "Sequenced by Steven Picken", "Edited by MaliceX", "(C) 2002-2003 Steven Picken";
  14 tracks, 31,146 bytes, file mtime 2007). README's "Test Results (input.mid — 51KB,
  15 tracks)" benchmark section describes a different file, so the tracked sample is
  not even the documented baseline. No test depends on the file existing (test
  references use the name only as a CLI-args placeholder).
- **Evidence**: `mido` inspection of the tracked file (14 tracks, 31146 bytes) vs
  `README.md:44`; `git ls-files | grep -v /` shows it among root-tracked files.
- **Impact**: A copyrighted asset of unclear provenance distributed with the repo, plus
  benchmark numbers that can't be reproduced against the file that ships. Legal/repro
  hygiene, no runtime impact.
- **Related**: TD-29/#397 (prior stray root file, fixed); #372/#373 (deterministic
  benchmark fixtures — the synthetic-fixture machinery that could replace this).
- **Suggested Fix**: Remove `input.mid` from tracking (the benchmark suite already has
  deterministic synthetic fixtures per #372/#373) and update README's example section
  to reference a generated fixture; or replace it with an original, license-clean demo
  MIDI whose stats match the README table.

### TD-45: Two dead locals — `results` in `run_benchmarks.py`, `e` in `profiling.py`
- **Severity**: LOW
- **Dimension**: 2 (Dead Code & Cruft)
- **Location**: `benchmarks/run_benchmarks.py:210` (`results = benchmark.run_batch_benchmarks(valid_files)` — never read); `utils/profiling.py:337` (`except Exception as e:` — body is `success = False; raise`, `e` unused)
- **Status**: NEW
- **Description**: The only two non-cosmetic pyflakes hits in non-test source (the
  repo-wide unused-import cleanup #264/TD-20 otherwise holds). Both are harmless:
  `run_batch_benchmarks` is called for its side effects; the `except` re-raises.
- **Evidence**: `python3 -m pyflakes $(git ls-files '*.py' | grep -v tests/)` filtered
  to `never used|imported but unused|redefinition` returns exactly these two lines.
- **Impact**: None at runtime; lint noise only.
- **Related**: #264/TD-20, #320/TD-24, #321/TD-25 (prior instances of the same class).
- **Suggested Fix**: Drop `results =` and the `as e`. One-line changes; suitable to fold
  into any nearby commit rather than a dedicated issue.

### TD-31: Duplicated music.asm preamble between `export_tables_with_patterns` and `export_song_bank_bytecode` (carried)
- **Severity**: LOW
- **Dimension**: 1 (Logic Duplication)
- **Location**: `exporter/exporter_ca65.py:1463-1492` vs `:1576-1592`
- **Status**: Carried from 2026-08-07 (TD-31) — unfixed, never filed
- **Description**: The ~15-line header block (`.importzp` line, DPCM `$C000` segment
  banner + `.align 64`, `CODE_8000` segment banner) is emitted verbatim by both bytecode
  exporters. Verified still duplicated this cycle; the single-song copy additionally
  carries the #137 explanatory comment the jukebox copy lacks.
- **Evidence**: Side-by-side read of the two ranges above.
- **Impact**: A future segment/preamble change (e.g. a new `.importzp` symbol) applied
  to one path silently skews the other; single-song vs jukebox `music.asm` drift.
- **Related**: TD-37 (same file); EXP-2026-08-21-4 (jukebox-path guard asymmetry —
  a sibling symptom of the two paths not sharing code).
- **Suggested Fix**: Extract a `_emit_bytecode_preamble(lines, jukebox=False)` helper
  used by both methods.

### TD-32: `run_song_build` re-implements the capacity→prepare→compile→validate sequence instead of reusing `build_and_validate_rom` (carried)
- **Severity**: LOW
- **Dimension**: 1 (Logic Duplication)
- **Location**: `main.py:1003-1025` (`run_song_build`) vs `main.py:1261-1293` (`build_and_validate_rom`)
- **Status**: Carried from 2026-08-07 (TD-32) — unfixed, never filed
- **Description**: The #406 extraction gave `run_full_pipeline` a tested, raise-based
  `build_and_validate_rom` helper covering exactly the steps `run_song_build` inlines
  with its own `sys.exit`-per-step copies (`check_mapper_capacity` → `NESProjectBuilder`
  → `compile_rom` → `validate_rom`). Verified still duplicated this cycle (the jukebox
  path was untouched by any commit since the prior report except `8ea7ac3`'s
  `song_count` gate, which widened the drift surface).
- **Evidence**: The two ranges above; `run_song_build` also inline-imports
  `MapperFactory` at `:1003` instead of using the module-level import path.
- **Impact**: Fixes to the build sequence (capacity messaging, validation policy) land
  in one path only. This duplication is also *why* the jukebox path lacks the
  single-recovery-point error contract — the HIGH-severity consequence is
  PIPE-2026-08-21-4's finding; this entry tracks the duplication root cause.
- **Related**: PIPE-2026-08-21-4 (HIGH, error-contract angle of the same code), #406.
- **Suggested Fix**: Parameterize `build_and_validate_rom` (it already takes mapper,
  music_asm, project path, output, flags; add `song_count`/`debug_mode` pass-through)
  and call it from `run_song_build` inside a try/except that owns error reporting.

### TD-33: `SongBank`'s virtual capacity model still disconnected from the real ROM capacity `song build` uses (carried; now documented)
- **Severity**: LOW (downgraded from MEDIUM: the disconnect is now explicitly documented, and the real build path catches overflow)
- **Dimension**: 3 (Stale/misleading model — documented-but-unreconciled)
- **Location**: `nes/song_bank.py:53-54` (`max_bank_size = 16384`, `total_banks = 8` model) vs `main.py:1007` (`check_mapper_capacity` against real MMC3 512KB/60-bank model)
- **Status**: Carried from 2026-08-07 (TD-33) — partially addressed (the class docstring
  rewritten in `8ea7ac3` now states the two models are "independent of — and not
  reconciled with" each other and points at docs/ROADMAP.md); never filed
- **Description**: `song add` still accepts/rejects songs against a 16KB×8 virtual-bank
  model sized off raw MIDI event counts, while `song build` builds against emitted
  bytecode vs the MMC3 pool — so bank-level acceptance guarantees nothing about
  buildability. Since the prior report the docstring honestly documents this, but the
  code paths remain unreconciled.
- **Evidence**: Docstring at `nes/song_bank.py:30-49`; unchanged allocator fields below it.
- **Impact**: A user can fill a bank that later fails at `song build` (clear error, late
  feedback). The runtime-cost angle (overflow detected only after all songs parse) is
  PERF-B-04's finding.
- **Related**: PERF-B-04 (2026-08-21), docs/ROADMAP.md follow-ups list.
- **Suggested Fix**: Either drop the virtual model (accept everything at `add`, size at
  `build`) or make `add_song` estimate against the real exporter-byte model; the
  docstring's pointer makes clear which model must win.

### TD-36: Jukebox 5-channel stride is a bare `5` with no shared named constant (carried)
- **Severity**: LOW
- **Dimension**: 6 (Magic Numbers)
- **Location**: `nes/audio_engine.asm:267-271` (`asl`/`asl`/`adc current_song` = ×5) and `exporter/exporter_ca65.py:1624` (comment "song_index*5 + channel")
- **Status**: Carried from 2026-08-07 (TD-36) — unfixed, never filed
- **Description**: The `song_table` stride (5 = `len(SEQUENCE_CHANNELS)`) is a contract
  shared between the Python exporter and the 6502 engine, expressed as raw shift/add
  math on one side and an f-string index on the other, with only comments tying them.
  Adding a 6th channel stream (e.g. DPCM variants) breaks playback silently.
- **Evidence**: Ranges above; no `.define`/constant on the asm side, no named constant
  referenced from both sides.
- **Impact**: Latent cross-language drift trap; also the code where siblings found the
  real 8-bit overflow bug this cycle.
- **Related**: NH-HW-2026-08-21-3 / PIPE-2026-08-21-3 (the `current_song*5` 8-bit
  overflow at 52+ songs, CRITICAL/MEDIUM — fixing those should introduce this constant
  as part of the remedy).
- **Suggested Fix**: Emit `SONG_TABLE_STRIDE = 5` into the generated asm from
  `len(self.SEQUENCE_CHANNELS)` and use it in `audio_engine.asm`'s comments/math
  (and in the overflow fix's widened index computation).

### TD-37: `_build_song_bytecode` is the largest method in `exporter_ca65.py` and grew again (carried, observational)
- **Severity**: LOW
- **Dimension**: 8 (Module/Function Size & Structure)
- **Location**: `exporter/exporter_ca65.py:1102-1446` (~345 lines; was ~330 on 2026-08-07)
- **Status**: Carried from 2026-08-07 (TD-37) — observational; grew via `8ea7ac3`'s
  per-song `CODE_8000` segment resets
- **Description**: The method serializes instruments, macros, and all five channel
  sequence streams with inline bank-overflow bookkeeping. The #136 lesson (per-channel
  emitters) applies directly: a per-channel sequence-stream emitter plus an
  instrument/macro-table emitter would mirror the direct-frames split that worked.
- **Evidence**: Method span above; `wc -l` = 1685 for the file.
- **Impact**: Change amplification on the highest-traffic export path (both single-song
  bytecode and jukebox builds flow through it).
- **Related**: #136/TD-11 (the successful sibling extraction), TD-31, EXP-2026-08-21-6
  (bank-overflow message quality — easier to fix per-emitter).
- **Suggested Fix**: When next touched for a functional change, extract per-channel
  stream emission and table emission; verify with the same golden-file diff harness
  #136 used. Not worth a standalone refactor commit before then.

---

## Verify-the-Fix (closed items re-checked against master this cycle)

| Item | Verdict |
|---|---|
| TD-03/#131 + #100/#103/#104 — shared `score_pattern`, `_collect_length_candidates` | **Holds** (parallel module imports `score_pattern`; no `_find_pattern_matches` copy) |
| TD-07/#134 — single MIDI-note→name converter | **Holds** (`midi_note_to_famistudio` sole instance; `arranger`'s `midi_note_to_nes_pitch` correctly *delegates* to `nes/pitch_table.py` per #89 — not a duplicate) |
| TD-04/#132, TD-05/#133 — stray root scripts removed | **Holds** (root-tracked .py = `main.py`, `constants.py`, `validate_rom.py`; but see TD-44 for `input.mid`) |
| TD-08/#137 — DPCM segment TODO replaced with accurate comment | **Holds** (`exporter/exporter_ca65.py:1473-1479`) |
| TD-10/#135 — bare `except:` in `utils/profiling.py` | **Holds on master** (no bare except; narrow catches with #336/#375 comments) — but skill prose stale, see TD-43 |
| TD-11/#136 — 8 per-channel emitters | **Holds** (all 8 present at `:213-601`; `export_direct_frames` still `:603-1027`, not re-inlined) |
| #406 — 3 `run_full_pipeline` stage helpers | **Holds** (`:1060/:1181/:1261`; `main.py` untouched since the prior report; raise-not-exit contract intact) |
| TD-28/#380 — single `pack_dpcm_into_asm` | **Holds** (one definition in `main.py`) |
| TD-30/#412 — duplicate `defaultdict` import | **Holds** (single import in `nes/emulator_core.py`) |
| TD-34 — `SongBank` docstring "no ROM route" claim | **Fixed** by `8ea7ac3` (docstring now accurately describes `song build`, and documents TD-33's disconnect) |
| TD-20/#264 — unused imports repo-wide | **Holds** (pyflakes clean except TD-45's two locals) |
| Retired placeholders `prepare_multi_song_project`/`add_song_bank` | **Not reintroduced** (only a historical mention in a test docstring) |
| TD-26/#346, TD-27/#347 | **REGRESSED / never landed** → TD-38 |
| #352 | **REGRESSED / never landed** → TD-39 |
| Dimension 4 markers | **Clean** — zero TODO/FIXME/HACK/XXX in non-test source |

### Stranded-branch classification (all 13 unmerged `fix/*` branches, by content)

Landed on master via other commits (branch is a stale leftover, safe to delete):
`fix/issue-374-cpu-percent-accuracy`, `fix/issue-388-mmc1-debug-bank-overlay`,
`fix/issues-372-373-benchmark-baseline-gate`, `fix/issues-389-390-mapper-capacity-preflight`,
`fix/exporter-clamp-diagnostic-dead-compression-engine-198-199`,
`fix/issue-378-fallback-coverage-lossy-note`, `fix/issue-379-unify-references-shape`
(378/379 per PIPE-2026-08-21-2's spot-check), `fix/issue-392-arranger-noise-mode-bit`,
`fix/macro-loop-control-byte-mismatch-frame-counter-comment-163-164`,
`fix/pitch-timer-clamp-and-dpcm-length-reg-rounding-41-75`.

**Not on master in any form** (closed issue, unfixed tree):
`fix/issue-377-wrong-stage-json-guard` (→ PIPE-2026-08-21-2, HIGH),
`fix/issues-346-347` (→ TD-38), `fix/issue-352` (→ TD-39).

---

## Cross-Audit Dedup (verified, not re-counted here)

- **TD-35** (jukebox `song_table` undocumented in `docs/AUDIO_BYTECODE_SPEC.md`) — now
  carried as EXP-2026-08-21-5; not re-reported.
- `ffccf51`'s un-gated channel-blind drum scan (CRITICAL) — DPCM-2026-08-21-1 /
  PIPE-2026-08-21-1; this audit reports only its duplication side (TD-40) and
  cross-refs.
- `current_song*5` 8-bit overflow — NH-HW-2026-08-21-3 / PIPE-2026-08-21-3; TD-36 here
  is the naming/constant aspect only.
- `run_song_build` missing backup/exception contract — PIPE-2026-08-21-4; TD-32 here is
  the duplication root cause.
- Dead `_WORKER_EVENTS` payload and dead `_optimize_patterns` — PAT-2026-08-21-4/-6;
  dead `print_analysis` — ARR-2026-08-21-4; dead triangle `control: 0x81` —
  NH-HW-2026-08-21-8. None re-reported.
- Stale skill prose in *other* audit skills (tempo #259/#260, dpcm #76, arranger
  #88/#91, performance drift, patterns SKILL line drift) — covered by those audits;
  TD-43 adds only `audit-tech-debt/SKILL.md` itself.

---

## Next Step

```
/audit-publish docs/audits/AUDIT_TECH_DEBT_2026-08-21.md
```
