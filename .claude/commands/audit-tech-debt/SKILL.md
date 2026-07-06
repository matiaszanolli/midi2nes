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
serialization; per-channel handling copy-pasted across `nes/`; the two parsers
(`tracker/parser.py` vs `tracker/parser_fast.py`) drifting; the two pattern detectors
(`tracker/pattern_detector.py` vs `tracker/pattern_detector_parallel.py`). `grep` for
near-identical blocks; report the canonical home.

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
One known, still-open marker: the DPCM `.incbin` TODO in the macro-bytecode export path
at `exporter/exporter_ca65.py:988` (TD-08/#137). It is stale rather than describing
real unfinished work — the actual `.incbin` lines and lookup tables are produced by
`dpcm_sampler/dpcm_packer.py`'s `generate_assembly` and appended to `music.asm` in
`main.py:597` (the `export` path) and `main.py:961` (the full pipeline). Confirm this is
still the only TODO/FIXME/HACK/XXX in non-test source before reporting new ones.

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
Oversized modules or functions doing too much. Two still-open, previously-identified
monoliths (TD-11/#136):
- `main.py` is ~1480 lines total: argparse-based dispatch (`main()`, from line 1077)
  layered with hand-rolled pre-subcommand argv scanning for global flags like
  `--arranger`/`--debug`/`--verbose` (`main.py:1237-1344`). `run_full_pipeline`
  (`main.py:744-1076`) alone is ~330 lines threading parse → map/arrange → frames →
  patterns → export → DPCM-pack → prepare → compile → validate inline.
- `exporter/exporter_ca65.py` is ~1290 lines total; `export_direct_frames`
  (`exporter/exporter_ca65.py:187-925`, next method `_compress_macro` at line 926)
  is ~738 lines emitting pitch tables, per-channel playback routines
  (pulse/triangle/noise/DPCM), and data tables all inline.

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
