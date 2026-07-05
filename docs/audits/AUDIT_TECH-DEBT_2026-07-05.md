# Tech-Debt Audit — MIDI2NES — 2026-07-05

Audit: `/audit-tech-debt` (all 8 dimensions, whole repo).
Scope: maintainability debt — duplication, dead code, stale docs, stale markers, stubs,
magic numbers, error-handling debt, module/function size. Correctness is owned by the
subsystem audits and is only flagged here when debt actively hides a bug.

Dedup baseline: `/tmp/audit/issues.json` (36 open issues, pre-fetched) plus every prior
report in `docs/audits/`, most directly `docs/audits/AUDIT_TECH-DEBT_2026-07-03.md`.
Per the task instruction, `gh issue list` was **not** re-run.

## Prompt-injection watch

Per protocol I watched for any embedded instruction in tool output attempting to steer
this audit. **None encountered.** The only markup anomaly on record is TD-19/#229 (leaked
tool-call tags in a *prior* report) — already tracked, inert, not re-litigated here.

## Summary

| Dimension | New Findings |
|-----------|--------------|
| 1. Logic Duplication | 0 (prior debt fixed/tracked — see Verification Notes) |
| 2. Dead Code & Cruft | 1 (TD-20 — repo-wide unused imports beyond the tracked two dirs) |
| 3. Stale Documentation & Comments | 2 (TD-21 README/HISTORY test count; TD-22 superseded planning docs) |
| 4. Stale Markers (TODO/FIXME) | 0 (unchanged — still the single tracked TD-08 marker) |
| 5. Stub & Placeholder | 0 (no new live-path stub) |
| 6. Magic Numbers | 0 (unchanged) |
| 7. Error-Handling Debt | 0 (unchanged — TD-10 sites unmoved) |
| 8. Module / Function Size | 0 new; both TD-11 monoliths **grew further** — see Verification Notes |

**Severity totals (new findings):** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 3.
**New:** 3. **Existing (verified, not regressed):** all SKILL-named items re-checked; the two
TD-11 monoliths have grown and should have #136 updated (not a new finding).

### Three highest-leverage cleanups
1. **TD-21 — Fix the "586 tests" claim in `README.md`.** The public-facing README states 586
   tests in three places (badge, tagline, testing section); the live count is **900**. This
   is the most-read doc in the repo and TD-13/#224 fixed only `MEMORY.md`.
2. **TD-20 — Sweep repo-wide unused imports (47 sites in 9 dirs beyond the tracked two).**
   `pyflakes` reports 56 `imported but unused` sites; #227/#228 cover only `main.py` and
   `debug/`. A single mechanical sweep clears the rest (17 alone in `arranger/`).
3. **TD-22 — Mark the superseded v0.4.0 planning docs as historical.** `IMMEDIATE_ACTIONS.md`
   / `COVERAGE_REPORT.md` / `TEST_COVERAGE_IMPROVEMENTS.md` assert 177–186 tests and v0.4.0 as
   *current* status with no archived banner — same family as TD-17 (which covered only
   `WORK_PLAN_1.0.0.md`).

---

## Findings

### TD-20: Unused imports are repo-wide (47 sites in 9 directories) — the tracked issues cover only 2
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: 47 sites across `arranger/` (17), `tracker/` (6), `exporter/` (5),
  `dpcm_sampler/` (4), `core/` (3), `mappers/` (3), `nes/` (3), `utils/` (3),
  `benchmarks/` (2), `config/` (1). Representative: `arranger/pipeline_integration.py:8-13`,
  `tracker/parser.py:4-5`, `tracker/parser_fast.py:4-5`, `mappers/base.py:9-10`,
  `core/dto.py:10-11`, `nes/debug_overlay.py:14`, `config/config_manager.py:3`.
- **Status**: NEW (extends Existing #227/TD-15 `main.py`, #228/TD-16 `debug/`, #112/P-04)
- **Description**: `pyflakes` over all tracked `*.py` (excluding `tests/` and `venv/`) reports
  **56** `imported but unused` sites; only 9 fall in `main.py`/`debug/`, which are already
  tracked (#227, #228). The remaining **47** are untracked. The `arranger/` package is the
  worst offender: `pipeline_integration.py` alone imports `Any`, `Optional`, `defaultdict`,
  `get_instrument_mapping`, `get_drum_mapping`, `NESChannel`, `FrameByFrameAllocator`,
  `VoiceAllocator`, `ArpStyle` — none referenced in that file (verified: `grep -c` returns
  only the import line for `defaultdict` and the `FrameByFrameAllocator`/`VoiceAllocator`
  pair). These are genuine dead imports, not `__all__` re-exports — the package's `__all__`
  lives in `arranger/__init__.py`, which imports *from* the submodules, not the reverse.
- **Evidence**: `python -m pyflakes $(git ls-files '*.py' | grep -v '^tests/' | grep -v venv)`
  → 56 `imported but unused`; filtering out `^main\.py|^debug/` leaves 47. Spot-checks:
  `grep -c defaultdict arranger/pipeline_integration.py` → 1 (import only).
- **Impact**: LOW — no pipeline/ROM effect. Misleads readers about each module's real
  dependency surface and inflates the import graph. Two identical dead-import lines in
  `tracker/parser.py` and `tracker/parser_fast.py` (`FRAME_MS`, `TempoOptimizationStrategy`)
  are a small duplication-drift signal between the two parsers as well.
- **Related**: #227 (TD-15), #228 (TD-16), #112 (P-04) — same pattern, different files.
- **Suggested Fix**: One mechanical `pyflakes`/`ruff --select F401` sweep across the repo;
  add `ruff` (or a `pyflakes` pre-commit hook) so this class stops re-accumulating. Scope the
  fix to imports only — the co-reported `f-string is missing placeholders` warnings are
  cosmetic no-ops (literal strings with a stray `f` prefix, no dropped interpolation) and
  need not block the sweep.

### TD-21: `README.md` and `HISTORY.md` still claim "586 tests" — the live count is 900
- **Severity**: LOW
- **Dimension**: 3 — Stale Documentation & Comments
- **Location**: `README.md:11` (badge), `README.md:14` (tagline), `README.md:298` (testing
  section); `HISTORY.md:99` (`v0.5.0-dev | 586 (45 files)`)
- **Status**: NEW (TD-13/#224 fixed the same number but scoped only to `MEMORY.md`)
- **Description**: The public-facing README asserts "586 tests" in three separate places —
  the Tests shields.io badge (`Tests-586%20passing`), the intro line ("586 tests passing"),
  and the testing section comment ("Run all tests (586 tests across 45 files)"). Live count
  is **900 tests across 50 files** (`python -m pytest --collect-only -q` → "900 tests
  collected"; `ls tests/test_*.py | wc -l` → 50). `HISTORY.md`'s milestone table row for
  `v0.5.0-dev` also reads "586 (45 files)". TD-13/#224 already flagged this exact stale
  number, but its scope and fix were `MEMORY.md`-only — the more visible README was left
  untouched. All three README lines trace to commit `a359e03` (2026-06-28), so they have
  been stale since the 0.5.0-dev bump, and have only drifted further (586 → 900).
- **Evidence**: `grep -n 586 README.md` → lines 11, 14, 298; `HISTORY.md:99`;
  `python -m pytest --collect-only -q` → `900 tests collected`.
- **Impact**: LOW — no runtime/ROM effect, but the README is the first doc a new contributor
  or user reads; a test-count badge that is ~35% low undermines the "stabilization" message
  it sits next to. `HISTORY.md` is a changelog so its stale row is more forgivable, but the
  v0.5.0-dev entry describes an *in-progress* release and could simply say "900+".
- **Related**: #224 (TD-13, `MEMORY.md` — same 586 number, different file, still open).
- **Suggested Fix**: Update the README badge/tagline/testing comment to the current count (or
  drop the hard number from the badge and link to CI), and either update or de-hard-code the
  `HISTORY.md` v0.5.0-dev row. Consider folding the count into a doc-lint that flags when
  `git`-tracked test-count strings diverge from `pytest --collect-only`.

### TD-22: Superseded v0.4.0 planning/coverage docs are unlabeled as historical and assert stale "current" status
- **Severity**: LOW
- **Dimension**: 3 — Stale Documentation & Comments
- **Location**: `docs/IMMEDIATE_ACTIONS.md:1,33,38,61,238`, `docs/COVERAGE_REPORT.md:6,101`,
  `docs/TEST_COVERAGE_IMPROVEMENTS.md:5`
- **Status**: NEW (same family as TD-17, which covered only `docs/WORK_PLAN_1.0.0.md`)
- **Description**: Three docs present long-superseded figures as current status with no
  "archived"/"superseded" banner: `IMMEDIATE_ACTIONS.md` ("Immediate Actions for v0.4.0",
  "All 186 tests passing", "177/177 tests passing", "Update all references … 0.3.5 → 0.4.0-dev",
  `__version__ = "0.4.0-dev"`); `COVERAGE_REPORT.md` ("Total Tests: 186 tests", "All 186 tests
  passing"); `TEST_COVERAGE_IMPROVEMENTS.md` ("bringing total test count from 568 to 582
  tests"). The project is on `0.5.0-dev` with 900 tests. None of the three carry a
  superseded/archived/historical marker (`grep -in "superseded|archived|historical"` → no
  hits), so — exactly like TD-17's `WORK_PLAN_1.0.0.md` — they read as live guidance rather
  than a dated snapshot. TD-17 was documented in the 2026-07-03 report but was **not** filed
  as a GitHub issue, so this whole doc-family remains untracked.
- **Evidence**: `grep -rniE "[0-9]{3} tests|v0\.[0-9]|177/177" docs/IMMEDIATE_ACTIONS.md
  docs/COVERAGE_REPORT.md docs/TEST_COVERAGE_IMPROVEMENTS.md`; `python -m pytest
  --collect-only -q` → 900.
- **Impact**: LOW — documentation only. A contributor skimming `docs/` could treat v0.4.0
  "immediate actions" (version bump, coverage targets) as still-open when they shipped long
  ago, or trust a 186-test coverage snapshot that is 4.8× under-count.
- **Related**: TD-17 (2026-07-03 report, `WORK_PLAN_1.0.0.md`, not filed as an issue);
  #224 (TD-13) and TD-21 (same 586/186/177 stale-count family).
- **Suggested Fix**: Add an "Archived — superseded by `docs/ROADMAP.md`" banner to the top of
  each (and to `WORK_PLAN_1.0.0.md` per TD-17), or move them under a `docs/history/`
  subdirectory so they stop reading as current planning.

---

## Verification Notes (SKILL-named items re-checked; none regressed, two grew)

Per the mandatory dedup process, every item the SKILL flagged as "already fixed/tracked,
verify before re-reporting" was re-checked against current source.

- **Dimension 1 (Logic Duplication)**: `_find_pattern_matches` copy-paste (TD-03/#131) still
  gone — `tracker/pattern_detector_parallel.py` uses `_collect_length_candidates`; both
  detectors share `score_pattern`. The duplicate note→name converter (TD-07/#134) is still
  single-sourced in `exporter/exporter_famistudio.py:midi_note_to_famistudio`;
  `exporter/exporter_ca65.py` has only the unrelated `midi_note_to_timer_value`. Note:
  #134 (TD-07) remains **open** in the issue list despite the code being clean — the
  duplicate `exporter/exporter.py` was already deleted; the issue appears stale-open.
- **Dimension 2 (Dead Code & Cruft)**: Repo root still holds only `main.py`, `constants.py`,
  `validate_rom.py` — no new stray script or duplicate `check_rom.py`/`validate_rom.py`
  reintroduced. `NOISE_PERIODS` (`exporter/exporter_ca65.py:40`) is still dead (defined,
  never referenced) and `is_midi_velocity` is now a **dead local** at line 999 that runs a
  full loop over `channel_frames` to compute a value it never uses — both already covered by
  Existing #165 (NH-23), not re-reported here.
- **Dimension 4 (Stale Markers)**: `grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py'`
  (excluding `tests/`) still returns exactly **one** hit — the DPCM `.incbin` TODO, now at
  `exporter/exporter_ca65.py:928` (drifted from 892 as the file grew). Still Existing #137
  (TD-08); still the sole marker.
- **Dimension 5 (Stub & Placeholder)**: `exporter/exporter_nsf.py`'s `NotImplementedError`
  self-documents #81; `nes/project_builder.py`'s multi-song placeholders remain honest no-ops
  off the default path. No new live-path stub.
- **Dimension 6 (Magic Numbers)**: `MIN_ROM_SIZE = 32768` (`compiler/compiler.py`) and
  `LARGE_FILE_THRESHOLD` (`main.py`) remain named. `CPU_CLOCK = 1789773` duplication in
  `arranger/pipeline_integration.py` unchanged — Existing #89 (ARR-06). No new bare
  hardware-magic-number.
- **Dimension 7 (Error-Handling Debt)**: `utils/profiling.py` bare `except:` clauses remain
  at the tracked locations (Existing #135/TD-10, also #223/SAFE-12). Not re-reported.
- **Dimension 8 (Module/Function Size) — BOTH MONOLITHS GREW**: `main.py` is now **1359**
  lines (was 1119 at the 2026-07-03 audit; +240). `run_full_pipeline` now spans
  `main.py:647-960` (~313 lines, was ~280). `export_direct_frames` now spans
  `exporter/exporter_ca65.py:88-843` (**755** lines, was 727; next method `_compress_macro`
  at line 843); the file overall is 1232 lines (was 1200). This is growth on the exact
  monoliths tracked by **Existing #136 (TD-11)** — recommend updating #136 with the new line
  figures rather than filing a duplicate. The recommended splits are unchanged:
  `run_full_pipeline` → per-stage helpers (parse/map/frames/patterns/export/pack/prepare/
  compile), and `export_direct_frames` → separate emitters for pitch tables vs. the four
  per-channel playback routines vs. data tables.

---

## Dedup notes

- All three new findings checked against `/tmp/audit/issues.json` (36 open) and every file
  under `docs/audits/`. TD-20 extends #227/#228/#112 (imports) to the untracked directories;
  TD-21 extends #224 (which fixed the 586 count only in `MEMORY.md`) to README/HISTORY; TD-22
  extends the 2026-07-03 report's TD-17 (never filed as an issue) to its sibling planning docs.
- The `arranger/pipeline_integration import` line in `AUDIT_ARRANGER_2026-07-03.md` and the
  "586 tests collected" line in `AUDIT_REGRESSION_2026-06-28.md` were checked and are **not**
  matches — the former is an illustrative code snippet, the latter a point-in-time suite
  snapshot, neither a stale-import or stale-doc finding.
- No finding here overlaps the open correctness issues; this report is maintainability-only.

---

Suggest:
```
/audit-publish docs/audits/AUDIT_TECH-DEBT_2026-07-05.md
```
