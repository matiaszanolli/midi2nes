# Tech-Debt Audit — MIDI2NES — 2026-07-03

Audit: `/audit-tech-debt` (all 8 dimensions, whole repo).
Scope: maintainability debt — duplication, dead code, stale docs, stale markers, stubs,
magic numbers, error-handling debt, module/function size. Correctness is owned by the
subsystem audits and is only flagged here when debt actively hides a bug.

Dedup baseline: `/tmp/audit/issues.json` (47 open issues, fetched live via
`gh issue list --repo matiaszanolli/midi2nes --limit 200 --json number,title,state,labels`)
plus `/tmp/audit/issues_closed.json` (100 closed issues) and every prior report in
`docs/audits/`, most directly `docs/audits/AUDIT_TECH_DEBT_2026-06-29.md`.

## A note on the "injection" warning

Per instructions, I watched for any embedded instruction in tool output (file content,
command output, etc.) attempting to steer me into hiding data from the user. **I did not
encounter any such injection in this session.** The only anomaly found is TD-19 below — a
genuinely corrupted, checked-in file (leaked tool-call syntax appended to a prior audit
report) — which is inert text, not an instruction, and is reported plainly rather than
acted on covertly. I also want to flag one thing for transparency: partway through
dedup I misread a terminal listing and briefly believed issue #89 (ARR-06) appeared in
both the open and closed issue lists — a live re-query (`gh issue view 89`) showed it is
simply OPEN and was never in the closed set. That was my own transcription error, not a
data or tool anomaly; noted here only in the interest of full disclosure since the task
asked me to watch closely for exactly this class of discrepancy.

## Summary

| Dimension | New Findings |
|-----------|--------------|
| 1. Logic Duplication | 0 (all prior debt fixed or tracked — see Verification Notes) |
| 2. Dead Code & Cruft | 3 (TD-15, TD-16, TD-19) |
| 3. Stale Documentation & Comments | 3 (TD-13, TD-14, TD-17) |
| 4. Stale Markers (TODO/FIXME) | 0 (unchanged — see Verification Notes) |
| 5. Stub & Placeholder | 0 (no live-path stub found — see Verification Notes) |
| 6. Magic Numbers | 0 (unchanged — see Verification Notes) |
| 7. Error-Handling Debt | 0 (unchanged — see Verification Notes) |
| 8. Module / Function Size | 0 (unchanged, not regressed — see Verification Notes) |

**Severity totals (new findings):** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 6.
**New:** 6. **Existing (verified, not regressed):** 8 items re-checked, all still accurate.

### Three highest-leverage cleanups
1. **TD-19 — Strip the corrupted trailing XML tags from `AUDIT_TECH_DEBT_2026-06-29.md`.**
   A checked-in audit report ends with leaked `</content>`/`</invoke>` tool-call syntax —
   a one-line `git` fix that removes a confusing, unprofessional artifact from `docs/`.
2. **TD-13 — Fix `MEMORY.md`'s self-contradicting claims.** The "durable knowledge" doc
   was already stale on the day it was authored: it warns `__version__.py` "still reads
   0.4.0-dev" when the very same commit that created `MEMORY.md` bumped it to 0.5.0-dev,
   and its "586 tests across 45 files" figure is now 789 tests / 50 files. Cheap fix,
   meaningfully restores trust in the one doc meant to be authoritative.
3. **TD-15/TD-16 — Delete five dead imports** (`main.py`: `typing.Dict`,
   `EnhancedDrumMapper`; `debug/`: unused `typing` imports in three files plus one unused
   dataclass import in `debug/__init__.py`). Zero-risk, mechanical, ~7-line diff total.

---

## Findings

### TD-13: `MEMORY.md` is self-contradicting on the day it was authored
- **Severity**: LOW
- **Dimension**: 3 — Stale Documentation & Comments
- **Location**: `MEMORY.md:10-11` (test count), `MEMORY.md:28-29` (`__version__.py` gotcha)
- **Status**: NEW
- **Description**: `MEMORY.md` states "**586 tests** across 45 files" — the live count is
  **789 tests across 50 files** (`python -m pytest --collect-only -q` → "789 tests
  collected"; `ls tests/test_*.py | wc -l` → 50). Separately, `MEMORY.md`'s "Gotchas worth
  remembering" section says `__version__.py` "lags reality... still reads `0.4.0-dev`" —
  but `midi2nes/__version__.py` currently reads `"0.5.0-dev"`. Both `MEMORY.md` and
  `midi2nes/__version__.py` were last touched in the **same commit**
  (`a359e03 feat: Bump version to 0.5.0-dev for upcoming release`, 2026-06-28), so this
  file misstated its own commit's content from the moment it was created — it was never
  accurate, not merely drifted since.
- **Evidence**: `git log -1 --format=%cd --date=short -- MEMORY.md midi2nes/__version__.py`
  → both `2026-06-28`; `git show --stat a359e03` includes both files.
  `python -m pytest --collect-only -q` → `789 tests collected`.
- **Impact**: `MEMORY.md` is explicitly positioned (in its own header) as the durable,
  authoritative doc pairing with `CLAUDE.md` — a wrong "current status" section undermines
  exactly the trust it's meant to provide. No runtime/ROM impact.
- **Related**: None open; not covered by any existing issue (`grep` for `MEMORY.md`/
  `586 tests` across `docs/audits/*.md` and both issue-list snapshots found nothing).
- **Suggested Fix**: Update the test count and delete/rewrite the `__version__.py` gotcha
  to reflect current state; consider a lightweight pre-commit check (or just discipline)
  that `MEMORY.md`'s "Current status" block is updated in the same commit as version bumps.

### TD-14: `docs/DEBUG_ROM_VISUAL_GUIDE.md` still assumes MMC1 ROM size — sibling drift to the fixed M-10
- **Severity**: LOW
- **Dimension**: 3 — Stale Documentation & Comments
- **Location**: `docs/DEBUG_ROM_VISUAL_GUIDE.md:121`
- **Status**: NEW (related to Existing #35/M-10, which is fixed but scoped only to
  `CLAUDE.md`/`README.md`)
- **Description**: Under "Scenario 4: ROM Doesn't Boot", the troubleshooting guide tells
  the reader to check "ROM file size (should be ~131KB for MMC1)". `python main.py --debug
  song.mid` (the exact command this guide's own opening line references) now builds against
  the **MMC3** default (512KB PRG in 8KB banks per `CLAUDE.md`), not MMC1/131KB. M-10 fixed
  this same MMC1-vs-MMC3 drift in `CLAUDE.md` and confirmed README was already consistent,
  but did not touch this file — `grep -rn "MMC1" docs/*.md` still shows this one live
  instance presented as current debugging guidance (the rest are historical/comparative
  mentions in `MAPPER_MMC3_REFERENCE.md`, `2A03_CPU_REFERENCE.md`, `APU_DMC_REFERENCE.md`,
  which correctly discuss MMC1 as an alternative, not the default).
- **Evidence**: `docs/DEBUG_ROM_VISUAL_GUIDE.md:121` — `- 🔍 **Check:** ROM file size
  (should be ~131KB for MMC1)`; `CLAUDE.md:197` — `PRG-ROM: MMC3 default is 512KB in 8KB
  banks (MMC1 is 128KB in 16KB banks; NROM is 32KB)`.
- **Impact**: A developer following this guide today to debug a non-booting debug ROM
  would look for the wrong file size and could misdiagnose a correctly-sized MMC3 ROM as
  broken (or vice versa). LOW — troubleshooting guidance only, no code/ROM impact.
- **Related**: Existing #35 (M-10, closed/fixed but scoped to `CLAUDE.md`/README).
- **Suggested Fix**: Update to "~512KB for the default MMC3 build (128KB/131KB if built
  with `--mapper mmc1`)" or point at the mapper-specific capacity instead of a bare number.

### TD-17: `docs/WORK_PLAN_1.0.0.md` "Current Status Assessment" is 18+ months stale and unlabeled as historical
- **Severity**: LOW
- **Dimension**: 3 — Stale Documentation & Comments
- **Location**: `docs/WORK_PLAN_1.0.0.md:3-8`
- **Status**: NEW
- **Description**: The doc opens with "## Current Status Assessment (December 2024)" and
  asserts "**Current Version**: v0.3.5" and "**Test Coverage**: 177/177 tests passing
  (100%)". The project is now on v0.5.0-dev with 789 tests. The date qualifier is present,
  so a careful reader isn't outright misled, but the doc is titled `WORK_PLAN_1.0.0.md` (no
  "archived"/"superseded" marker) and sits alongside `docs/ROADMAP.md`, which
  `.claude/commands/_audit-common.md` names as the authoritative forward-looking doc —
  `docs/WORK_PLAN_1.0.0.md` isn't cross-referenced from `ROADMAP.md` or `HISTORY.md` as
  superseded, so it reads as still-live planning rather than a historical snapshot.
- **Evidence**: `docs/WORK_PLAN_1.0.0.md:3-8`; `python -m pytest --collect-only -q` → 789
  tests (vs the doc's 177); `grep -n "WORK_PLAN" docs/ROADMAP.md HISTORY.md` → no hits (no
  cross-link marking it superseded).
- **Impact**: LOW — a contributor skimming `docs/` could treat 1.0.0 milestone items as
  still-open work without realizing most of "Phase 1" is long since done (patterns,
  arranger, DPCM, MMC3 all shipped per `HISTORY.md`/`MEMORY.md`).
- **Related**: TD-13 (same family: docs asserting stale test counts/status).
- **Suggested Fix**: Add an "Archived — superseded by `docs/ROADMAP.md`" banner at the top,
  or fold any still-relevant open items into `ROADMAP.md` and delete the rest.

### TD-15: `main.py` imports two names it never uses (`typing.Dict`, `EnhancedDrumMapper`)
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `main.py:6`, `main.py:24`
- **Status**: NEW
- **Description**: `from typing import Dict, Optional` — only `Optional` is ever referenced
  (`grep -n "Dict\[" main.py` → no hits). `from dpcm_sampler.enhanced_drum_mapper import
  EnhancedDrumMapper, DrumMapperConfig` — only `DrumMapperConfig` is used (`load_config` at
  `main.py:462-466`); `EnhancedDrumMapper` has zero references anywhere else in the file.
  Confirmed via `pyflakes`: `main.py:6:1: 'typing.Dict' imported but unused` and
  `main.py:24:1: 'dpcm_sampler.enhanced_drum_mapper.EnhancedDrumMapper' imported but
  unused`.
- **Evidence**: `python -m pyflakes main.py`; `grep -n "EnhancedDrumMapper" main.py` → only
  the import line.
- **Impact**: Misleading (implies `main.py` instantiates a drum mapper directly; it
  doesn't) and pulls the class into the CLI's import graph for nothing. Same category as
  the already-fixed TD-06/#112 (`tracker.parser` unused import), different symbols.
- **Related**: Existing #112 (P-04, closed — the same "unused top-level import" pattern in
  `main.py`, different names).
- **Suggested Fix**: Drop `Dict` from the typing import and drop `EnhancedDrumMapper` from
  the `enhanced_drum_mapper` import, keeping only `DrumMapperConfig`.

### TD-16: Unused `typing`/dataclass imports scattered across `debug/` tooling
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `debug/rom_diagnostics.py:23` (`Optional`, `Any`), `debug/nes_devtools.py:10`
  (`List`, `Tuple`, `Optional`), `debug/pipeline_integration_example.py:16` (`pathlib.Path`),
  `debug/__init__.py:32` (`ROMDiagnosticResult`)
- **Status**: NEW
- **Description**: `pyflakes` over `debug/` (after excluding `tests/` and the local
  `venv/`) reports four unused-import sites, all in developer tooling rather than the
  pipeline: `rom_diagnostics.py` imports `Optional`/`Any` from `typing` without using
  either; `nes_devtools.py` imports `List`/`Tuple`/`Optional` without using any; the
  example script imports `pathlib.Path` and never references it; `debug/__init__.py`
  imports `ROMDiagnosticResult` into its public surface but nothing re-exports or uses it
  internally.
- **Evidence**: `python -m pyflakes debug/` output (filtered to non-test, non-venv paths):
  4 distinct `imported but unused` warnings at the locations above.
- **Impact**: LOW — confined to `debug/` diagnostic tooling, no pipeline/ROM effect. Purely
  a lint/navigation cost.
- **Related**: TD-15 (same pattern, pipeline side instead of tooling side).
- **Suggested Fix**: Remove the unused names from each import line; if
  `debug/__init__.py`'s `ROMDiagnosticResult` re-export is intentional public API, add
  `__all__` so linters (and readers) recognize it as deliberate rather than dead.

### TD-19: A prior audit report is corrupted with leaked tool-call syntax
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `docs/audits/AUDIT_TECH_DEBT_2026-06-29.md:295-296`
- **Status**: NEW
- **Description**: The last two lines of the checked-in report are `</content>` and
  `</invoke>` — XML-like tags from some tool-call/harness serialization that leaked into
  the markdown body instead of being stripped before the file was written. This is
  committed at `HEAD` (`git show HEAD:docs/audits/AUDIT_TECH_DEBT_2026-06-29.md | tail -2`
  reproduces both lines), not a local/uncommitted artifact.
- **Evidence**: `git log --oneline -- docs/audits/AUDIT_TECH_DEBT_2026-06-29.md` →
  `9b4f3f8 Add tech-debt and tempo audits for 2026-06-29`; the tags are part of that
  commit's blob.
- **Impact**: Cosmetic only — the corruption is after the report's closing `---` divider,
  so it doesn't affect the readable content above it. But it is confusing cruft in a
  checked-in doc and, worth naming explicitly given this audit's brief: it is exactly the
  shape of thing a reader might mistake for an embedded instruction (it isn't one — it's
  inert leftover markup, not natural-language text, and contains no directive).
- **Related**: None.
- **Suggested Fix**: Delete the two trailing lines in a follow-up commit; consider a
  sanity check (e.g. `grep -L '</invoke>\|</content>'`) before committing future
  audit-generated docs.

---

## Verification Notes (existing debt re-checked, none regressed)

Per the mandatory dedup process, every item the SKILL flagged as "already fixed, verify
before re-reporting" was re-checked against current source, not assumed:

- **Dimension 1 (Logic Duplication)**:
  - `ThreadedPatternDetector` — confirmed gone (`grep -rn "ThreadedPatternDetector"` only
    hits a regression test asserting its absence, `tests/test_patterns.py:935`, and an
    explanatory comment in `tracker/pattern_detector.py:12`). TD-03/#131 not regressed.
  - Duplicate MIDI-note→note-name converter — confirmed `exporter/exporter.py` no longer
    exists; `exporter/exporter_famistudio.py:165 midi_note_to_famistudio` is the sole
    implementation; `exporter/exporter_ca65.py` only has the unrelated
    `midi_note_to_timer_value`. TD-07/#134 not regressed.
  - Arranger's hand-rolled `CPU_CLOCK = 1789773` / `midi_note_to_nes_pitch`
    (`arranger/pipeline_integration.py:288-315`) still duplicates
    `nes/pitch_table.py`'s `CPU_CLOCK_RATE`/`PitchProcessor` formula exactly as before —
    but this is **Existing #89 (ARR-06, OPEN)**, not a new finding.
  - Per-channel frame compilation in `nes/emulator_core.py` is correctly centralized
    (`compile_channel_to_frames(self, events, channel_type=..., ...)` at line 48) —
    parameterized by `channel_type`, not copy-pasted per channel. No new duplication found.
- **Dimension 2 (Dead Code & Cruft)**: Repo root now holds only
  `main.py`, `constants.py`, `validate_rom.py` at the top level (plus non-code files:
  `CLAUDE.md`, `HISTORY.md`, `MEMORY.md`, `README.md`, `requirements.txt`, `dpcm_index.json`,
  `input.mid` — a legitimate, long-standing test fixture, not scratch cruft). The five
  scratch scripts and duplicate `check_rom.py` (TD-04/#132, TD-05/#133) remain deleted; only
  `debug/check_rom.py` exists now. `.nes`/`.log`/`.s` build artifacts remain gitignored
  (`.gitignore` lines 18/23/25/61), so still not tracked cruft.
- **Dimension 3**: `CLAUDE.md` and `README.md` no longer assert MMC1-as-default anywhere
  (`grep -niE "always use mmc1|128KB|MMC1 ROM"` → zero hits in either) — #35/M-10 fix holds.
- **Dimension 4 (Stale Markers)**: `grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py' .`
  (excluding `tests/`) still returns exactly one hit, now at
  `exporter/exporter_ca65.py:892` (line number shifted from the prior report's 858 as the
  file grew, same TODO text). Still the sole marker; still Existing #137 (TD-08), not
  re-reported.
- **Dimension 5 (Stub & Placeholder)**: `exporter/exporter_nsf.py`'s `NotImplementedError`
  is self-documented and explicitly cites #81 in its own docstring — not new debt, already
  tracked. `nes/project_builder.py:667-683`
  (`prepare_multi_song_project`/`add_song_bank`) are honest, self-documented no-op
  placeholders ("Placeholder for multi-song ROM builds... not implemented yet") with zero
  production callers (`grep` shows only their own definitions and their own unit tests) —
  not on the default `main.py input.mid out.nes` path, and already covered by the
  song-bank-is-storage-only resolution of Existing #30 (F-13, closed). Not reported as a
  new stub finding; noted here for completeness.
- **Dimension 6 (Magic Numbers)**: `1789773`/`CPU_CLOCK` duplication unchanged (see
  Dimension 1 above, Existing #89). `MIN_ROM_SIZE = 32768` (`compiler/compiler.py:27`) and
  `LARGE_FILE_THRESHOLD = 10000` (`main.py:551`) remain named constants (the latter is
  function-local rather than module-level, but still named, not bare) — no new bare
  hardware-magic-number instance found.
- **Dimension 7 (Error-Handling Debt)**: `utils/profiling.py`'s three bare `except:`
  clauses are still at the **exact same line numbers** (89, 196, 300) as the prior report —
  Existing #135 (TD-10), unchanged. The sibling bare-`except:` sites it names
  (`debug/rom_tester.py:71`, `benchmarks/performance_suite.py:103`) are also unchanged;
  `nes_devflow.py` (the third sibling in the original TD-10 write-up) no longer exists,
  consistent with its deletion under TD-04.
- **Dimension 8 (Module/Function Size)**: `exporter/exporter_ca65.py:export_direct_frames`
  is still lines 88-815 (727 lines, matching the SKILL's own note); the file overall grew
  from ~1154 to 1200 lines but the method itself is unchanged. `main.py:run_full_pipeline`
  is lines 468-748 (~280 lines, matching prior measurement); `main.py` overall grew from 997
  to 1119 lines (net growth elsewhere in the file, e.g. the new global-flag argv scanning),
  but neither monolith method grew further. Existing #136 (TD-11), not regressed, not
  re-reported.

---

## Dedup notes

- All six new findings (TD-13 through TD-19, minus the reused TD-01–TD-12 numbering from
  the 2026-06-29 report) were checked against `/tmp/audit/issues.json` (47 open),
  `/tmp/audit/issues_closed.json` (100 closed), and every file under `docs/audits/` by
  keyword (`MEMORY.md`, `DEBUG_ROM_VISUAL`, `WORK_PLAN`, `pyflakes`/unused-import phrasing,
  `</invoke>`) — none matched an existing issue or report.
- TD-14 is deliberately scoped as *sibling drift* to the already-fixed #35/M-10, not a
  reopening of it — M-10's own fix was correct and scoped to `CLAUDE.md`/README; this is a
  different file the original audit didn't check.
- No finding here overlaps the open correctness issues (patterns/NH/pipeline/etc.); this
  report is maintainability-only, consistent with the tech-debt skill's scope boundary.

---

Suggest:
```
/audit-publish docs/audits/AUDIT_TECH-DEBT_2026-07-03.md
```
