---
description: "Audit accumulated tech debt — duplication, dead code, stale docs, stubs, magic numbers"
argument-hint: "[--focus <dims>] [--path <dir>]"
---

# Tech-Debt Audit

Find maintainability debt across the Python codebase — the slow-accumulating kind that
no single feature audit owns. Not a correctness audit (that's the subsystem skills); this
is about code that *works* but costs more to change than it should.

Shared protocol: `.claude/commands/_audit-common.md` (layout, dedup, finding format).
Severity: `.claude/commands/_audit-severity.md` — tech-debt findings are usually LOW,
escalating to MEDIUM when the debt actively hides bugs (a swallowed exception, a stub on a
live path) or contradicts a hardware doc.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 2,3`). Default: all.
- `--path <dir>` — restrict to a subtree (e.g. `--path exporter`). Default: whole repo.

## Extra Per-Finding Field
- **Dimension**: one of the 8 below.

## Dimensions

### Dimension 1: Logic Duplication
Repeated logic that should be shared (the user's standing rule: improve existing code, never
duplicate). Hot spots: the four exporters (`exporter/`) re-implementing register/byte
serialization; per-channel handling copy-pasted across `nes/`; the two pattern detectors
(`tracker/pattern_detector.py` vs `tracker/pattern_detector_parallel.py`). `grep` for
near-identical blocks; report the canonical home.

**#346 (TD-26) is CLOSED**: the "two parsers drifting" hot spot — *tracker/parser.py*, a
full parser reachable only by three tests and on no production pipeline path — is gone.
`tracker/parser_fast.py` is now the sole MIDI front-end; its three former callers
(`tests/test_midi_parser_integration.py`, `tests/test_integration.py`,
`tests/test_pattern_integration.py`) were retargeted to it. Verify-the-fix: confirm no new
second parser implementation reappears.

Two prior instances of exactly this pattern are now fixed — verify they haven't
regressed before hunting for new ones:
- The copy-pasted `_find_pattern_matches` between `tracker/pattern_detector.py` and
  `tracker/pattern_detector_parallel.py` (TD-03/#131) is gone: the parallel module now
  has its own O(n) grouping helper, `_collect_length_candidates`, shared between its
  parallel and serial (`_detect_patterns_serial`) code paths, and both detectors share
  `score_pattern` from `tracker/pattern_detector.py` (#100/#103/#104). The sequential
  `EnhancedPatternDetector._find_pattern_matches` (`tracker/pattern_detector.py:291`)
  still exists on its own — it does variation/transposition-aware matching the O(n)
  grouping can't, so this is now a deliberate algorithmic split, not copy-paste drift.
  (`_find_pattern_matches` is at `tracker/pattern_detector.py:320`.)
- The duplicate MIDI-note→note-name converter (TD-07/#134, `midi_note_to_ft` in the old
  *exporter/exporter.py*) was removed entirely as dead code in commit `2bcb780`.
  `exporter/exporter_famistudio.py:midi_note_to_famistudio` (line 164) is now the sole
  implementation of that conversion — confirm no second copy has reappeared (e.g. in
  `exporter/exporter_ca65.py`, which only has the unrelated
  `midi_note_to_timer_value` at line 42) before reporting a new instance of TD-07.

### Dimension 2: Dead Code & Cruft
Unused functions/imports/modules, unreachable branches, root-level scratch files, or
`*.s`/`*.nes`/`*.log` artifacts checked into the tree. Confirm no caller via `grep -rn`
before flagging. Distinguish "dead" from "only called by tests".

Five such root scripts (*implementation_examples.py*, *show_greeting.py*,
*batch_test.py*, *nes_devflow.py*, *generate_test_midi.py*) plus a duplicate,
unrelated-implementation *check_rom.py* at the repo root were removed in commit
`535b7ae` (TD-04/#132, TD-05/#133 — closed). The repo root now holds only
`main.py`, `constants.py`, and `validate_rom.py` at the top level. Treat this as
fixed and reframe the check as: confirm no new stray root-level script, duplicate
`check_rom.py`/`validate_rom.py`, or other dead module has been reintroduced since.

Non-Python files count too, and the current known lead is `nes/linker_mmc3.cfg`: it is
checked in but `grep -rn linker_mmc3` finds **no reference anywhere** in the tree — every
mapper emits its `nes.cfg` programmatically from `generate_linker_config()`, so nothing
reads this file. Confirm that still holds (a build script or test picking it up would make
it live), then judge whether it's a stale leftover or a deliberately-kept reference copy —
if the latter, the fix is a comment saying so, not deletion.

Retired placeholders to watch for a reappearance: `prepare_multi_song_project` and
`add_song_bank` in `nes/project_builder.py` were removed once `song build` gave the song
bank a real ROM route (#30/F-13). Either name coming back is dead code, not a feature.

### Dimension 3: Stale Documentation & Comments
A `docs/*.md`, docstring, or comment that contradicts the code. Highest-value targets:
`CLAUDE.md` (it already notes the MMC1→MMC3 prepare drift — check for more), `docs/ROADMAP.md`,
`docs/WORK_PLAN_1.0.0.md`, `README.md`, and the APU reference docs vs the actual
`nes/pitch_table.py` / `nes/envelope_processor.py` constants. Doc-rot that misstates
hardware behavior is MEDIUM.

### Dimension 4: Stale Markers (TODO / FIXME / HACK / XXX)
```bash
grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py' .
```
Report markers that describe real unfinished work (not just notes). Group by subsystem.
**TD-08/#137 is CLOSED**: the DPCM `.incbin` TODO in the macro-bytecode export path
(`exporter/exporter_ca65.py`, `.segment "DPCM"` block) was itself stale rather than
describing real unfinished work, and has been replaced with an accurate comment
(`exporter/exporter_ca65.py:1090-1094`) explaining the segment is *deliberately* left
empty — the actual `.incbin` lines and lookup tables are produced by
`dpcm_sampler/dpcm_packer.py`'s `generate_assembly` and appended to `music.asm` via the
shared `pack_dpcm_into_asm` helper (`main.py:126-215`, called from both `run_export` and
`run_full_pipeline` — see `/audit-dpcm` Dimension 2 / `/audit-safety` Dimension 1 for
that consolidation, #380/TD-28), not into this fixed `$C000`/R6-window segment. Confirmed
at the time of the fix this was the only TODO/FIXME/HACK/XXX in non-test source — re-run
the grep before reporting new ones.

### Dimension 5: Stub & Placeholder Implementations
Functions that `return None`/`pass`/raise `NotImplementedError`, or hardcode a value where
real logic is implied — especially on a live pipeline path (a stubbed exporter branch, a
no-op validation). A stub on a path the default `main.py input.mid out.nes` run hits is MEDIUM.

### Dimension 6: Magic Numbers & Hardcoded Constants
Bare numeric literals that should be named or sourced from a doc — APU register addresses
($4000–$4017), 11-bit timer maxima, the 60Hz frame rate, NTSC 1.789773 MHz, the MMC1/MMC3
bank sizes, the `LARGE_FILE_THRESHOLD`/`MIN_ROM_SIZE` constants. Where a `docs/APU_*.md`
or `docs/MAPPER_*.md` defines the value, cite it. (LOW unless the magic number is wrong.)

### Dimension 7: Error-Handling Debt
Bare `except:` / `except Exception: pass`, broad catches that hide the real error,
`print`-and-continue where the pipeline should stop. Overlaps `/audit-safety` — here, focus
on the *pattern* prevalence and a shared remedy, not each individual site.

A concrete, still-open instance: `utils/profiling.py` has a bare `except:` clause
(line 120) that also swallows `KeyboardInterrupt`/`SystemExit` (TD-10/#135).
Blast radius is limited to profiling/benchmark tooling, not the MIDI→ROM pipeline, hence LOW.

### Dimension 8: Module / Function Size & Structure
Oversized modules or functions doing too much. TD-11/#136 covered two monoliths;
one half is now closed, the other explicitly deferred:
- **`exporter/exporter_ca65.py`'s `export_direct_frames` half is CLOSED** (#136):
  extracted 8 per-channel emitter methods — `_emit_pulse_or_triangle_table` (`:213`),
  `_emit_noise_table` (`:303`), `_emit_dpcm_table` (`:326`) for frame-data tables, and
  `_emit_pulse1_proc` (`:341`), `_emit_pulse2_proc` (`:399`), `_emit_triangle_proc`
  (`:453`), `_emit_noise_proc` (`:507`), `_emit_dpcm_proc` (`:545`) for playback
  subroutines — cutting `export_direct_frames` (`:603-1027`) from ~750 lines to ~425.
  Verified byte-for-byte identical emitted output via a golden-file diff across 24
  configs at the time of the fix. `exporter_ca65.py` is now ~1445 lines total (grew
  overall — extraction adds method boilerplate — but the one oversized function is
  gone). Verify-the-fix: confirm the 8 emitters stay focused (one channel's table or
  proc each) and a future edit doesn't re-inline them back into
  `export_direct_frames`.
- **`main.py`'s `run_full_pipeline` half is now CLOSED** (#406): three of its stages
  were extracted into independently-testable module-level functions, all defined just
  above `run_full_pipeline` (`main.py:1060-1294`) — `detect_patterns_or_direct_export`
  (`:1060`, Step 4: parallel/sequential pattern detection with fallback + sampling, or
  the direct-export stats stub), `export_frames_and_resolve_mapper` (`:1181`, Steps
  5-5.5: CA65 export, DPCM packing, and `--mapper` resolution — unifying the two
  resolution-timing paths that used to be split across two different points in
  `run_full_pipeline`), and `build_and_validate_rom` (`:1261`, Steps 6-8: capacity
  pre-flight, project prep, compile, validate). `run_full_pipeline` itself
  (`main.py:1295`) dropped from ~335 to ~137 lines. `main.py` is now ~1878 lines
  total (grew further from the helper extraction's own boilerplate and docstrings —
  the same pattern the exporter half's extraction showed, see #136 above — but the one
  oversized function is gone). Each extracted helper raises instead of calling
  `sys.exit` itself; `run_full_pipeline`'s single try/except/finally (still gating
  backup/restore-on-failure, #26) is the only place that decides how to report a
  failure. Steps 1-3 (parse → map/arrange → frames) deliberately remain inline in
  `run_full_pipeline` — the `del midi_data`/`del mapped` calls trimming peak memory
  (#371/PERF-A-01, see `/audit-performance`) only free anything if they execute in the
  frame holding the last reference, so extracting that code into a callee would
  silently break the memory contract. Verify-the-fix: confirm the three extracted
  helpers stay focused on their named steps and aren't re-inlined back into
  `run_full_pipeline`; confirm a future stage addition also raises rather than calling
  `sys.exit` inline, keeping the single-recovery-point contract intact.

Report the split that would help, not just the line count — and flag if either has
grown further since the numbers above.

## Cross-Dimension Dedup
A single root cause can surface in several dimensions (a duplicated block that is also a
stub that also has a stale comment). Report it once, in the most actionable dimension, and
cross-reference.

## Output
Write to: **`docs/audits/AUDIT_TECH_DEBT_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — counts per dimension, the 3 highest-leverage cleanups.
2. **Findings** — base format + `Dimension`.

Then suggest:
```
/audit-publish docs/audits/AUDIT_TECH_DEBT_<TODAY>.md
```
