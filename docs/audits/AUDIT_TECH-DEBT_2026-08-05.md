# Tech-Debt Audit — MIDI2NES — 2026-08-05

Scope: maintainability debt across the Python codebase (duplication, dead code, stale docs,
stale markers, stubs, magic numbers, error-handling debt, module/function size). Correctness
is out of scope (owned by the subsystem audits).

Repo state at audit: `master`, HEAD `3b16c5a`, version `0.5.0-dev`.

This run follows the 2026-07-19 report (`AUDIT_TECH-DEBT_2026-07-19.md`). No commits touched
`main.py`, `exporter/exporter_ca65.py`, `tracker/pattern_detector*.py`, or
`exporter/exporter_famistudio.py` logic in the interim beyond the mapper/DPCM fixes in
`36348ce` and `7853aa4` (already reflected in the numbers below). All standing debt from prior
audits is re-verified intact and unregressed; one new, small finding is reported: a stray
zero-byte file (`skip`) accidentally checked into the repo root.

---

## Summary

### New findings by dimension

| Dimension | New | IDs |
|-----------|-----|-----|
| 1 — Logic Duplication | 0 | — (TD-28/#380 unchanged, still open) |
| 2 — Dead Code & Cruft | 1 | TD-29 |
| 3 — Stale Documentation | 0 | — |
| 4 — Stale Markers | 0 | — (TD-08/#137 still the sole marker) |
| 5 — Stubs & Placeholders | 0 | — |
| 6 — Magic Numbers | 0 | — |
| 7 — Error-Handling Debt | 0 | — |
| 8 — Module/Function Size | 1 (update) | TD-11 growth (Existing #136) |

**Severity totals (findings in this report):** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 2
(1 NEW, 1 existing-update).

The tree remains heavily audited; nearly all standing tech debt is already tracked as open
issues (TD-08/#137, TD-11/#136, TD-26/#346, TD-27/#347, TD-28/#380, EXP-09/#302). The one new
item is trivial (a 0-byte tracked file with no code reference) but is exactly the kind of
accidental-`git add` cruft Dimension 2 exists to catch.

### Three highest-leverage cleanups

1. **Land TD-28/#380** — extract `pack_dpcm_into_asm(...)` out of `run_export` and
   `run_full_pipeline` in `main.py`. Still open, still diverged (verbose passing and
   status-line printing differ between the two copies), and directly shrinks the #136
   monolith while removing the highest-risk duplication in the tree.
2. **Split the two growing monoliths** (TD-11/#136). `exporter/exporter_ca65.py` grew
   again (1341 → 1372 lines; `export_direct_frames` 742 → 760 lines). `main.py` itself
   shrank overall (1584 → 1541) via unrelated cleanup in `36348ce`/`7853aa4`, but
   `run_full_pipeline` is still ~362 lines of inline parse→...→validate orchestration.
3. **Remove the zero-byte `skip` file** (TD-29, NEW) — trivial, but a 30-second fix with
   zero risk; good opportunistic cleanup alongside either of the above.

---

## Verification of prior-fixed items (no regression)

- **`_find_pattern_matches` split (TD-03/#131)** — intact.
  `tracker/pattern_detector.py:348` keeps the variation/transposition-aware
  `_find_pattern_matches`; `tracker/pattern_detector_parallel.py:437` still owns the O(n)
  `_collect_length_candidates`. Both detectors import/share `score_pattern` from
  `tracker/pattern_detector.py:52` (`pattern_detector_parallel.py:8`,
  `pattern_detector_parallel.py:421`). No copy-paste has reappeared.
- **MIDI-note→note-name converter (TD-07/#134)** — single home confirmed:
  `exporter/exporter_famistudio.py:173` (`midi_note_to_famistudio`).
  `exporter/exporter_ca65.py:55` only has the unrelated `midi_note_to_timer_value`. No
  second copy of the note-name converter.
- **Root scripts (TD-04/#132, TD-05/#133)** — repo root still holds only `main.py`,
  `constants.py`, `validate_rom.py` as Python entry points (plus the tracked fixture
  `input.mid` and the config/data files `dpcm_index.json`, `requirements.txt`, `.gitignore`,
  `.python-version`, and the docs `CLAUDE.md`/`HISTORY.md`/`MEMORY.md`/`README.md`). No
  stray root script or duplicate `check_rom.py` reintroduced. (The many `*.mid`/`*.nes`/
  `*.s`/`*.log` files visible via `ls` at the repo root — `NBA.mid`, `NBA.nes`, `poly*.nes`,
  `nba_*.s/.json`, `rebuild.log`, `sultans.log`, `sultans2.mid`, `test_*.nes`, `test_fixed.s`,
  `.aider.*` — are confirmed **git-ignored** (`git status --ignored` shows all with `!!`),
  i.e. local scratch, not checked into the tree. They are out of scope for this dimension,
  which targets tracked cruft; see TD-29 below for the one tracked exception found.)
- **Bare `except:` scan** — still clean in non-test source; the two remaining matches
  (`tests/test_parser_fast.py:582`, `tests/test_rom_tester.py:40`) are doc comments in test
  files describing historical regressions, not live bare-except clauses.
  `utils/profiling.py:129` is `except Exception:` (not bare), consistent with TD-10/#135's
  fix.
- **TD-08/#137** — the stale DPCM `.incbin` TODO is still the **sole**
  TODO/FIXME/HACK/XXX in non-test source, now at `exporter/exporter_ca65.py:1022`
  (shifted +31 lines from the 07-19 report's line 991, consistent with the file's growth).
  Still stale — the real `.incbin` output is produced by `dpcm_sampler/dpcm_packer.py`'s
  `generate_assembly` and appended in `main.py:616` (`run_export`) and `main.py:1022`
  (`run_full_pipeline`).
- **TD-26/#346** — `tracker/parser.py` remains production-dead; only
  `tests/test_midi_parser_integration.py`, `tests/test_integration.py`,
  `tests/test_pattern_integration.py`, and `tests/test_main.py` import it. Unchanged.
- **TD-27/#347** — `src/music_driver.s`, `src/nsf_main_driver.s`, `src/nes.inc` remain
  present and unreferenced by any Python source (`grep` for their filenames across `*.py`
  returns no hits; NSF export is still `NotImplementedError`, #81). Unchanged.
- **EXP-09/#302** — `exporter/compression.py`'s `CompressionEngine` and
  `exporter/base_exporter.py`'s compress/decompress helpers are referenced only from
  `tests/test_compression_integration.py`, `tests/test_compression.py`, and
  `tests/test_exporter_integration.py` — no production call site. Unchanged.
- **Stub scan** — clean. All `pass`/`NotImplementedError` sites in non-test source are
  legitimate: abstract methods in `mappers/base.py`, exception bodies in
  `core/exceptions.py` and `tracker/tempo_map.py:59` (`TempoValidationError`), a narrow
  `except OSError: pass` in the dev-only `debug/rom_tester.py:71-72` (header-read guard,
  not on the ROM-generation path), and the documented `exporter/exporter_nsf.py:75-80`
  `NotImplementedError` stubs (#81).
- **Magic-number scan** — clean. `constants.py` (`FRAME_RATE_HZ`, `FRAME_MS`,
  `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`) remains the shared source; APU register
  addresses are named constants at the top of `exporter/exporter_ca65.py` (e.g.
  `APU_PULSE1_CTRL = 0x4000`, `APU_STATUS = 0x4015`); the NTSC clock is the named
  `CPU_CLOCK_RATE = 1789773` in `nes/pitch_table.py:19`. No un-named regression found.
- **Doc-rot scan** — `docs/ROADMAP.md` and `docs/WORK_PLAN_1.0.0.md` both self-flag their
  status correctly (ROADMAP is current/authoritative; WORK_PLAN explicitly marks itself
  "Archived — historical snapshot... superseded by ROADMAP.md", #226/TD-17). `CLAUDE.md`'s
  mapper-default description (`prepare`/`run_full_pipeline` default to MMC3, `auto` forced
  to MMC3 for macro-bytecode builds) matches the live `resolve_mapper` implementation
  (`main.py:242`) and its call sites — no drift found.

---

## Findings

### TD-29: Stray zero-byte `skip` file checked into repo root
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `skip` (repo root, tracked, 0 bytes)
- **Status**: NEW
- **Description**: A 0-byte file named `skip` is tracked at the repo root, added in commit
  `cadff6d` ("Add new skip file for pipeline audit tracking", 2026-07-06). The commit's other
  eight changed files are unrelated `.claude/issues/*` and `docs/audits/*` additions — `skip`
  appears to be an accidental artifact of an unrelated `touch`/`git add .` swept into that
  commit rather than an intentional addition. No code, test, script, or doc references a file
  named `skip` anywhere in the tree.
- **Evidence**:
  ```
  $ git ls-files | grep -v '/'
  ... constants.py dpcm_index.json input.mid main.py requirements.txt skip validate_rom.py

  $ git show cadff6d -- skip
  diff --git a/skip b/skip
  new file mode 100644
  index 0000000..e69de29

  $ grep -rn "'skip'\|\"skip\"" --include='*.py' .
  (no matches)
  ```
- **Impact**: None functionally — the file is inert. Purely cosmetic/hygiene: a stray
  tracked file at repo root that new contributors may mistake for something meaningful, and
  that clutters `git ls-files` / root directory listings.
- **Related**: None (first report of this specific file).
- **Suggested Fix**: `git rm skip` in a small hygiene commit. If it was meant to mark
  something (its commit message suggests "pipeline audit tracking"), replace it with a real,
  named artifact or drop the intent entirely — a content-less file conveys no information.

### TD-11 (update): the two monoliths — main.py shrank overall, exporter_ca65.py grew again
- **Severity**: LOW
- **Dimension**: 8 — Module/Function Size & Structure
- **Location**: `main.py` (1541 lines; `run_full_pipeline` at `main.py:776-1137`, ~362 lines);
  `exporter/exporter_ca65.py` (1372 lines; `export_direct_frames` at
  `exporter/exporter_ca65.py:200-959`, ~760 lines, next method `_compress_macro` at line 960)
- **Status**: Existing: #136 — reported because Dimension 8 directs flagging further growth.
- **Description**: Since the 2026-07-19 report (`main.py` 1584 / `exporter_ca65.py` 1341):
  - `main.py` **shrank** to 1541 (-43), via unrelated cleanup in `36348ce`
    ("make mapper auto-select export-mode-aware...") and `7853aa4` ("remove dead
    mmc3_init.asm, guard missing DPCM index..."), not a #136 split. `run_full_pipeline`
    itself is unchanged in size (~362 lines, same as 07-19) — still one function inlining
    parse → map/arrange → frames → patterns → export → DPCM-pack (TD-28) → prepare →
    compile → validate.
  - `exporter/exporter_ca65.py` **grew again**: 1341 → **1372** (+31).
    `export_direct_frames` grew from ~742 to **~760** lines (+18), still emitting pitch
    tables + per-channel playback routines (pulse/triangle/noise/DPCM) + data tables
    inline in one method.
  The structural debt #136 describes is unresolved; the exporter side keeps accreting even
  as the CLI side had incidental, unrelated shrinkage.
- **Evidence**:
  ```
  $ wc -l main.py exporter/exporter_ca65.py
  1541 main.py
  1372 exporter/exporter_ca65.py

  $ grep -n "def run_full_pipeline" main.py
  776:def run_full_pipeline(args):
  # next top-level def at line 1138 (def main():) => ~362 lines

  $ grep -n "def export_direct_frames\|def _compress_macro" exporter/exporter_ca65.py
  200:    def export_direct_frames(self, frames, output_path, standalone=True, mapper=None):
  960:    def _compress_macro(self, data):
  # => ~760 lines
  ```
- **Impact**: Compounding change-cost concentrated in `exporter/exporter_ca65.py`; no
  runtime effect. `main.py`'s net shrinkage is good news but incidental — it did not come
  from addressing #136's actual complaint (the size of `run_full_pipeline` itself).
- **Related**: TD-11/#136 (open); TD-28/#380 (a concrete extractable slice of
  `run_full_pipeline`, still open, unchanged this pass).
- **Suggested Fix**: Unchanged from prior reports: (a) land the low-risk TD-28/#380 helper
  extraction first, (b) lift per-subcommand handlers + the global-flag pre-scan out of
  `main.py` into a `cli/` package, (c) extract the per-channel playback-routine emitters out
  of `export_direct_frames` into helper methods (one per channel type) — this is now the
  faster-growing of the two monoliths.

---

## Notes — open issues re-verified (backlog hygiene)

Not new findings; re-confirmed from the tree for accuracy this pass.

- **TD-28/#380** — still open, still diverged. `main.py:608` (`run_export`) omits
  `verbose=` on `load_dpcm_index_into_packer` and prints no status line; `main.py:1014`
  (`run_full_pipeline`) passes `verbose=args.verbose` and prints packed-count /
  no-samples-referenced / no-index status lines. No further drift beyond what 07-19 already
  reported, but also not fixed.
- **TD-08/#137, TD-26/#346, TD-27/#347, EXP-09/#302** — all open, all unchanged (see
  Verification section above for current line numbers / import sites).

`constants.py` continues to be the single source for `FRAME_RATE_HZ`/`FRAME_MS`/
`PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`, shared by `main.py`, `tracker/parser_fast.py`,
`tracker/tempo_map.py`, and `benchmarks/`. No magic-number regression.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_TECH-DEBT_2026-08-05.md
```
