# Tech-Debt Audit — MIDI2NES — 2026-08-06

Scope: maintainability debt across the Python codebase (duplication, dead code, stale docs,
stale markers, stubs, magic numbers, error-handling debt, module/function size). Correctness
is out of scope (owned by the subsystem audits).

Repo state at audit: branch `fix/issues-136-137-167-202`, HEAD `20f627e`, version `0.5.0-dev`.

This run follows `AUDIT_TECH-DEBT_2026-08-05.md`. Since that report, commit `20f627e` landed
and closed both TD-08/#137 (the stale DPCM `.incbin` TODO) and the `exporter_ca65.py` half of
TD-11/#136 (per-channel emitter extraction). Earlier in the same window, `fe8c5b3` closed
TD-28/#380 (duplicated DPCM-packing block) and `90b4582` closed EXP-09/#302 (dead
`CompressionEngine`). All four closures are verified in place below. One new, small finding
is reported: a duplicate `from collections import defaultdict` import in
`nes/emulator_core.py`, caught by a `pyflakes` sweep this pass.

---

## Summary

### Findings by dimension

| Dimension | New | Notes |
|-----------|-----|-------|
| 1 — Logic Duplication | 0 | TD-03/#131 and TD-07/#134 splits re-verified intact |
| 2 — Dead Code & Cruft | 1 (TD-30) | Duplicate import in `nes/emulator_core.py`; TD-29/#397 (`skip` file) unregressed |
| 3 — Stale Documentation | 0 | CLAUDE.md / ROADMAP / WORK_PLAN / COVERAGE_REPORT all still accurate or self-flagged |
| 4 — Stale Markers | 0 | Repo-wide grep for TODO/FIXME/HACK/XXX in non-test source is now clean (TD-08/#137 closed) |
| 5 — Stubs & Placeholders | 0 | All `pass`/`NotImplementedError` sites in non-test source remain legitimate |
| 6 — Magic Numbers | 0 | `constants.py` / named APU/mapper constants unchanged, no regression |
| 7 — Error-Handling Debt | 0 | No bare `except:` in non-test source; TD-10/#135 fix intact |
| 8 — Module/Function Size | 1 (update) | `exporter_ca65.py` half of TD-11/#136 now CLOSED; `main.py`/#406 half re-verified open, unchanged |

**Total findings in this report: 2** (1 NEW, 1 update-to-existing). **Severity: LOW 2, MEDIUM 0, HIGH 0, CRITICAL 0.**

The tree remains heavily audited and, for the first time across this report series, has a
clean TODO/FIXME/HACK/XXX grep and one of its two long-standing "monolith" findings fully
closed. Remaining tech debt is a short, already-tracked tail (TD-26/#346, TD-27/#347,
TD-29/#397, TD-11-FOLLOWUP/#406) plus the one new item below.

### Three highest-leverage cleanups

1. **Land TD-11-FOLLOWUP/#406** — split `run_full_pipeline` (`main.py:871-1206`, ~335 lines)
   into per-stage helpers per the design contract #406 already files (memory-profile parity
   with #371's baseline, single-recovery-point semantics preserved, stages raising instead of
   calling `sys.exit` inline). This is now the only open module-size finding.
2. **Remove the zero-byte `skip` file** (TD-29/#397) — trivial, zero-risk, still un-landed
   three reports running.
3. **Fix the duplicate `defaultdict` import** (TD-30, NEW) — one-line, zero-risk; good
   opportunistic cleanup alongside either of the above.

---

## Verification of prior-fixed items (no regression except where noted CLOSED)

- **TD-08/#137 (DPCM `.incbin` TODO) — now CLOSED.** `exporter/exporter_ca65.py`'s
  `.segment "DPCM"` block (around line 1090) no longer carries the stale TODO; it now has an
  accurate comment explaining the segment is deliberately left content-free because the real
  `.incbin` data and lookup tables are packed and appended to `music.asm` by
  `dpcm_sampler/dpcm_packer.py`'s `generate_assembly` via the shared `pack_dpcm_into_asm`
  helper (`main.py:126`), not into this fixed `$C000`/R6-window segment. Re-ran
  `grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py' .` restricted to non-test source: **zero
  matches** — this was the last standing marker in the tree.
- **TD-11/#136 — `exporter_ca65.py` half now CLOSED.** `export_direct_frames` is now
  `exporter/exporter_ca65.py:603-1027` (~425 lines, down from ~760), having been split into
  8 focused per-channel emitters: `_emit_pulse_or_triangle_table` (`:213`),
  `_emit_noise_table` (`:303`), `_emit_dpcm_table` (`:326`) for data tables, and
  `_emit_pulse1_proc` (`:341`), `_emit_pulse2_proc` (`:399`), `_emit_triangle_proc`
  (`:453`), `_emit_noise_proc` (`:507`), `_emit_dpcm_proc` (`:545`) for playback subroutines.
  Each emitter is scoped to exactly one channel/table type (15-90 lines each) — no
  re-inlining back into `export_direct_frames`. File total is now 1445 lines (grew overall
  from the extraction's own boilerplate, but the one oversized function is gone), consistent
  with the commit's own byte-for-byte golden-diff verification claim.
- **TD-11/#136 — `main.py` half (tracked as #406) re-verified still OPEN, unchanged.**
  `run_full_pipeline` is `main.py:871-1206` (~335 lines; `main()` starts at `:1207`), matching
  the state already documented in #406 — no further growth since that issue was filed, and no
  attempt to split it landed in this window (commit `20f627e`'s own message explicitly
  confirms this half was investigated but deliberately deferred to #406). `main.py` total is
  now 1610 lines.
- **TD-28/#380 (duplicated DPCM-packing block) — now CLOSED.** `main.py` has a single
  `pack_dpcm_into_asm` helper (`main.py:126`) called from both `run_export` (`main.py:709`)
  and `run_full_pipeline` (`main.py:1097`) — no second inline copy of the packing logic
  remains.
- **EXP-09/#302 (dead `CompressionEngine`) — now CLOSED.** `exporter/compression.py` has been
  deleted entirely (`find . -name compression.py` returns nothing); `exporter/base_exporter.py`
  is now a documented one-line `pass` marker class explaining the removal. Only test files and
  the removal comment itself still mention `CompressionEngine`, both as historical references.
  `docs/COVERAGE_REPORT.md` still lists `exporter/compression.py` in its module table, but that
  doc already self-flags as "Archived — historical snapshot... superseded by
  `docs/ROADMAP.md`" (#266/TD-22), so this is not new doc-rot — it's the archived doc doing
  exactly what its own disclaimer says.
- **TD-03/#131 (`_find_pattern_matches` split)** — intact. `tracker/pattern_detector.py:348`
  keeps the variation/transposition-aware `_find_pattern_matches`;
  `tracker/pattern_detector_parallel.py:437` still owns the O(n) `_collect_length_candidates`.
  Both detectors still share `score_pattern` from `tracker/pattern_detector.py:52`. No
  copy-paste has reappeared.
- **TD-07/#134 (MIDI-note→note-name converter)** — single home confirmed:
  `exporter/exporter_famistudio.py:173` (`midi_note_to_famistudio`).
  `exporter/exporter_ca65.py:55` only has the unrelated `midi_note_to_timer_value`. No second
  copy of the note-name converter.
- **TD-10/#135 (bare `except:` in `utils/profiling.py`)** — still fixed.
  `utils/profiling.py:129` is `except Exception:` (not bare). Repo-wide grep for `except:`
  in non-test source: zero matches. The two remaining `except:` hits are historical doc
  comments inside test files (`tests/test_rom_tester.py:40`, `tests/test_parser_fast.py:582`)
  describing regressions already fixed, not live code.
- **TD-26/#346 (`tracker/parser.py` production-dead)** — unchanged. Still imported only by
  `tests/test_midi_parser_integration.py`, `tests/test_integration.py`,
  `tests/test_pattern_integration.py`, `tests/test_main.py`. Open, unregressed.
- **TD-27/#347 (`src/*.s`/`src/nes.inc` unreferenced NSF scaffolding)** — unchanged.
  `src/music_driver.s`, `src/nsf_main_driver.s`, `src/nes.inc` remain present; `grep` for
  their filenames across `*.py` returns no hits. Open, unregressed.
- **TD-29/#397 (stray zero-byte `skip` file)** — unchanged. `git ls-files | grep -v '/'`
  still lists a tracked 0-byte `skip` at the repo root; no code references it. Open,
  unregressed.
- **Stub scan** — clean. All `pass`/`NotImplementedError` sites in non-test source remain
  legitimate: abstract methods in `mappers/base.py` (7 sites), exception bodies in
  `core/exceptions.py` (6 sites) and `tracker/tempo_map.py:59`
  (`TempoValidationError`), the documented `BaseExporter` marker class discussed above, and
  the documented `exporter/exporter_nsf.py:75-80` `NotImplementedError` stubs (#81). No new
  stub on a live pipeline path.
- **Magic-number scan** — clean. `constants.py` (`FRAME_RATE_HZ`, `FRAME_MS`,
  `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`) remains the shared source; APU register
  addresses are named constants in `exporter/exporter_ca65.py` (e.g. `APU_PULSE1_CTRL =
  0x4000`, `APU_STATUS = 0x4015`); the NTSC clock is `CPU_CLOCK_RATE = 1789773` in
  `nes/pitch_table.py:19`. Mapper PRG-capacity constants (`mappers/mmc1.py:48` → 128KB,
  `mappers/mmc3.py:32` → 512KB) match `CLAUDE.md`'s stated capacities. No regression.
- **Doc-rot scan** — `docs/ROADMAP.md` and `docs/WORK_PLAN_1.0.0.md` both still self-flag
  their status correctly (#226/TD-17). `docs/COVERAGE_REPORT.md` still self-flags as archived
  (#266/TD-22). `CLAUDE.md`'s mapper-default description (`prepare`/`run_full_pipeline`
  default to MMC3, `auto` forced to MMC3 for macro-bytecode builds, PRG capacities per mapper)
  matches the live `resolve_mapper` implementation and mapper classes — no drift found.
- **Unused-import sweep (new this pass)** — ran `pyflakes` across `main.py`, `exporter/`,
  `tracker/`, `nes/`, `mappers/`, `compiler/`, `dpcm_sampler/`, `arranger/`, `core/`. Zero
  "imported but unused" findings; one duplicate-import redefinition found and reported below
  as TD-30 (NEW). Remaining pyflakes output is all "f-string is missing placeholders" style
  warnings (cosmetic, not tech debt in the sense this audit tracks — no logic error, no
  dead/duplicated code) and was not further pursued.

---

## Findings

### TD-30: Duplicate `defaultdict` import in `nes/emulator_core.py`
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `nes/emulator_core.py:1-3`
- **Status**: NEW
- **Description**: `from collections import defaultdict` is imported twice — once on line 1
  and again on line 3, with the unrelated `from .pitch_table import PitchProcessor` import
  sandwiched between them. The second import shadows/redefines the first with no
  functional difference; it is inert cruft rather than a bug, but it is exactly the kind of
  copy-paste-during-edit residue this dimension exists to catch. Confirmed via
  `python3 -m pyflakes nes/emulator_core.py` → `nes/emulator_core.py:3:1: redefinition of
  unused 'defaultdict' from line 1`, and manually re-read the file to confirm both lines are
  identical imports of the same name from the same module (not, e.g., an aliased or
  qualified re-import that would have a purpose).
- **Evidence**:
  ```python
  # nes/emulator_core.py:1-9
  from collections import defaultdict
  from .pitch_table import PitchProcessor
  from collections import defaultdict
  from .envelope_processor import (
      EnvelopeProcessor,
      velocity_to_volume,
      NOISE_DECAY_FRAMES,
      noise_strike_decay_volume,
  )
  ```
- **Impact**: None functionally — Python import caching makes the second `import` a no-op
  after the first. Purely a readability/maintainability nit in a file that is otherwise the
  central frame-generation module (`NESEmulatorCore.process_all_tracks`); a repo-wide
  duplicate-import grep across all other core modules (`nes/`, `exporter/`, `tracker/`,
  `mappers/`, `compiler/`, `dpcm_sampler/`, `arranger/`, `core/`, `main.py`) found this as the
  **only** instance.
- **Related**: None (first report of this specific instance).
- **Suggested Fix**: Delete the redundant `from collections import defaultdict` on line 3;
  keep the line-1 import. One-line diff, zero risk.

### TD-11 (update): `exporter_ca65.py` half CLOSED; `main.py`/#406 half re-verified open, unchanged
- **Severity**: LOW
- **Dimension**: 8 — Module/Function Size & Structure
- **Location**: `exporter/exporter_ca65.py:603-1027` (`export_direct_frames`, now ~425
  lines); `main.py:871-1206` (`run_full_pipeline`, ~335 lines, unchanged from #406's filing)
- **Status**: Existing: #136 (exporter half now closed by commit `20f627e`) / #406 (main.py
  half, still open) — reported to record the status change and confirm the remaining half
  has not grown further.
- **Description**: Since the 2026-08-05 report, commit `20f627e` extracted 8 per-channel
  emitter methods out of `export_direct_frames`, closing the exporter half of TD-11/#136 (see
  Verification section above for the full method list and line ranges — each emitter is
  correctly scoped to one channel/table type, with no sign of being re-inlined). The
  `main.py` half, tracked separately as #406, is unchanged: `run_full_pipeline` is still one
  ~335-line function threading parse → map/arrange → frames → patterns → export → DPCM-pack
  → prepare → compile → validate inline, for the reasons #406 itself documents (single
  try/except/finally recovery point per #26, `del`-based memory trimming per #371, inline
  `sys.exit(1)` validation, no clean byte-for-byte verification story). No further growth
  beyond what #406 already describes.
- **Evidence**:
  ```
  $ wc -l main.py exporter/exporter_ca65.py
  1610 main.py
  1445 exporter/exporter_ca65.py

  $ grep -n "def run_full_pipeline\|def main(" main.py
  871:def run_full_pipeline(args):
  1207:def main():
  ```
- **Impact**: Compounding change-cost is now concentrated solely in `main.py`'s
  `run_full_pipeline`; the exporter side no longer contributes to this dimension's tally.
  No runtime effect either way.
- **Related**: TD-11/#136 (partially closed), TD-11-FOLLOWUP/#406 (open, unchanged), TD-08/#137
  (closed same commit, see Verification section).
- **Suggested Fix**: Land #406 as filed — it already has the specific design contract
  (memory-profile comparison against #371's baseline, preserved single-recovery-point
  semantics, stages raising instead of calling `sys.exit` inline) needed to split
  `run_full_pipeline` safely.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_TECH_DEBT_2026-08-06.md
```
