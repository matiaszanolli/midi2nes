# Tech-Debt Audit — MIDI2NES — 2026-06-29

Audit: `/audit-tech-debt` (all 8 dimensions, whole repo).
Scope: maintainability debt — duplication, dead code, stale docs, stale markers, stubs,
magic numbers, error-handling debt, module/function size. Correctness is owned by the
subsystem audits (NES-hardware, mappers, pipeline, regression) and is only flagged here
when debt actively hides a bug.

Dedup baseline: `/tmp/audit/issues.json` (22 open issues) plus prior reports
`docs/audits/AUDIT_{MAPPERS,NES_HARDWARE,PIPELINE,REGRESSION}_2026-06-28.md`.

## Summary

| Dimension | Findings |
|-----------|----------|
| 1. Logic Duplication | 4 (TD-01, TD-02, TD-03, TD-12) |
| 2. Dead Code & Cruft | 3 (TD-04, TD-05, TD-06) |
| 3. Stale Documentation | 1 (TD-07) |
| 4. Stale Markers (TODO/FIXME) | 1 (TD-08) |
| 5. Stub & Placeholder | 0 (see TD-08; no live-path stub found) |
| 6. Magic Numbers | 1 (TD-09) |
| 7. Error-Handling Debt | 1 (TD-10) |
| 8. Module / Function Size | 1 (TD-11) |

**Severity totals:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 12.
**New:** 12. **Existing/Regression:** 0.

### Three highest-leverage cleanups
1. **TD-04 — Delete the five tracked root scratch `.py` files** (`implementation_examples.py`,
   `show_greeting.py`, `batch_test.py`, `nes_devflow.py`, `generate_test_midi.py`). Zero
   importers, zero pipeline role; `show_greeting.py` is an unrelated stray. One commit,
   removes ~40 KB of confusing surface.
2. **TD-01 — Centralize the NES CPU clock + MIDI-note→timer conversion.** `arranger/`
   re-derives the timer formula with its own `CPU_CLOCK = 1789773` and `2047` clamp instead
   of reusing `nes/pitch_table.py`; this is exactly the kind of drift that already produced
   the octave-apart pitch tables (NH-03). Route the arranger through `PitchProcessor`.
3. **TD-03 — Drop the dead `ThreadedPatternDetector` class and de-dupe `_find_pattern_matches`.**
   The parallel module carries an entire unused detector and a copy-pasted match routine that
   has already drifted in comments from the sequential one — a future bug-fix will land in
   only one copy.

---

## Findings

### TD-01: Arranger re-implements MIDI-note→NES-timer conversion with its own CPU clock constant
- **Severity**: LOW
- **Dimension**: 1 — Logic Duplication
- **Location**: `arranger/pipeline_integration.py:258-291` vs `nes/pitch_table.py:19-46`
- **Status**: NEW
- **Description**: `midi_note_to_nes_pitch()` hardcodes `CPU_CLOCK = 1789773`, recomputes
  `440 * 2**((n-69)/12)`, applies the pulse `/16` and triangle `/32` dividers, and clamps to
  `2047` — duplicating `PitchProcessor` / `CPU_CLOCK_RATE` in `nes/pitch_table.py`. This is on
  the live `--arranger` path (called at `pipeline_integration.py:227,236`). Two independent
  implementations of the same hardware formula are how the pulse/triangle tables already drifted
  an octave apart (see `AUDIT_NES_HARDWARE_2026-06-28.md` NH-03).
- **Evidence**: `arranger/pipeline_integration.py:270` `CPU_CLOCK = 1789773`;
  `:281` `period = int(CPU_CLOCK / (16 * frequency) - 1)`; `:284` triangle `/32`; `:291`
  `max(0, min(2047, period))`. `nes/pitch_table.py:19` `CPU_CLOCK_RATE = 1789773`;
  `:41` `timer = int(CPU_CLOCK_RATE / (divider * freq) - 1)`.
- **Impact**: Maintenance hazard on the polyphonic front-end; a pitch-table fix in
  `nes/pitch_table.py` silently does not reach `--arranger` output.
- **Related**: TD-09 (the duplicated `1789773` literal); NH-03 (drift this pattern caused).
- **Suggested Fix**: Have `midi_note_to_nes_pitch` delegate to `PitchProcessor` (or a shared
  `note_to_timer`) and import `CPU_CLOCK_RATE` rather than redefining it.

### TD-02: Two parallel ROM-validators — root `validate_rom.py` vs `main.py:validate_rom`
- **Severity**: LOW
- **Dimension**: 1 — Logic Duplication
- **Location**: `validate_rom.py:6` (root) and `main.py:115`
- **Status**: NEW
- **Description**: The root `validate_rom.py` is a standalone iNES header/reset-vector/zero-fill
  checker; `main.py:validate_rom` is the pipeline's post-build gate (delegating to
  `debug.rom_diagnostics`). They validate overlapping properties (reset vectors, header) with
  separate, divergent logic. The root script is referenced only by tests
  (`tests/test_validate_rom_script.py`, `tests/test_main_pipeline.py`), not by any pipeline path.
- **Evidence**: `grep` for importers of `validate_rom` finds only test files; `main.py:115`'s
  gate calls `ROMDiagnostics(...).diagnose_rom`, a different code path entirely.
- **Impact**: A validation rule fixed in one is not reflected in the other; the root script's
  tests give false confidence that "ROM validation" is centrally covered.
- **Related**: F-02 (ROM-validation gate only blocks on ERROR), TD-06.
- **Suggested Fix**: Either fold the root checker's checks into `debug.rom_diagnostics` and make
  `validate_rom.py` a thin CLI over it, or document it as a deliberately minimal independent
  cross-check.

### TD-03: Copy-pasted `_find_pattern_matches` across the two pattern detectors (already drifting)
- **Severity**: LOW
- **Dimension**: 1 — Logic Duplication
- **Location**: `tracker/pattern_detector.py:277-292` vs `tracker/pattern_detector_parallel.py:202-217`
- **Status**: NEW
- **Description**: Both detectors carry an effectively identical `_find_pattern_matches`
  (same algorithm, same `pos += pattern_len` overlap-skip), differing only in comments — i.e.
  the copies have already begun to drift. The two detectors must agree on match semantics for the
  fallback (`ParallelPatternDetector` → `EnhancedPatternDetector`) to produce equivalent output;
  a fix to one will silently not reach the other.
- **Evidence**: `diff` of the two slices shows only docstring/comment differences
  (`# Skip the length of the pattern to avoid overlaps` vs `# Skip to avoid overlaps`).
- **Impact**: Future correctness fix lands in one detector only; the parallel/serial paths can
  diverge in which matches they find.
- **Related**: TD-04 (dead `ThreadedPatternDetector` in the same module), REG-06.
- **Suggested Fix**: Extract `_find_pattern_matches` (and `_find_matches` in the dead threaded
  class) to a shared module-level helper.

### TD-04: Five tracked root scratch `.py` files with zero importers (plus a dead detector class)
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `implementation_examples.py`, `show_greeting.py`, `batch_test.py`,
  `nes_devflow.py`, `generate_test_midi.py` (all repo root); `tracker/pattern_detector_parallel.py:314`
  (`ThreadedPatternDetector`)
- **Status**: NEW
- **Description**: All five root `.py` files are checked into git and have **zero** importers
  across the codebase (and zero references from `tests/`). `show_greeting.py` is an unrelated
  stray (`print(f"Hey {name}")`). `implementation_examples.py` is a 16 KB obsolete parser
  prototype superseded by `tracker/parser_fast.py`. `ThreadedPatternDetector`
  (`pattern_detector_parallel.py:314`) has no caller anywhere.
- **Evidence**: `git ls-files` lists all five; `grep -rln "import <name>"` returns 0 non-self
  hits for each. `grep -rn "ThreadedPatternDetector"` finds only its own definition.
- **Impact**: Confuses navigation and audits; `implementation_examples.py` looks like a real
  parser. No runtime impact.
- **Related**: TD-05 (duplicate `check_rom.py`), TD-03.
- **Suggested Fix**: Delete the five root scripts (move any still-wanted helper into `debug/` or
  `tools/`) and remove `ThreadedPatternDetector`.

### TD-05: Duplicate `check_rom.py` — root copy diverges from `debug/check_rom.py`
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `check_rom.py` (root) vs `debug/check_rom.py`
- **Status**: NEW
- **Description**: Two files named `check_rom.py` exist. The root one is a self-contained iNES
  header/vector dumper hardcoded to read `input.nes` in its `__main__`; `debug/check_rom.py` is
  the documented tool (CLAUDE.md references `python debug/check_rom.py`) that wraps
  `rom_diagnostics`. They are entirely different implementations sharing a name.
- **Evidence**: `diff check_rom.py debug/check_rom.py` shows no shared body; root `__main__`
  calls `check_rom('input.nes')` (hardcoded path).
- **Impact**: Ambiguity over which `check_rom` is authoritative; root copy is effectively dead
  (no caller, hardcoded input).
- **Related**: TD-04, TD-02.
- **Suggested Fix**: Delete the root `check_rom.py`; keep the documented `debug/check_rom.py`.

### TD-06: `main.py:16` imports the full parser but every call site shadows it with `parser_fast`
- **Severity**: LOW
- **Dimension**: 2 — Dead Code & Cruft
- **Location**: `main.py:16`
- **Status**: NEW
- **Description**: `from tracker.parser import parse_midi_to_frames` at module level is never
  used: both real parse sites (`main.py:41`, `main.py:421`) do a local
  `from tracker.parser_fast import parse_midi_to_frames as parse_fast` and call `parse_fast`.
  The top-level name `parse_midi_to_frames` is never referenced, so the slow legacy parser is
  imported into `main.py` purely as dead weight (and as a misleading signal that `main.py` uses it).
- **Evidence**: `grep -n "parse_midi_to_frames" main.py` → only the import line and the two
  aliased local re-imports; no bare call.
- **Impact**: Misleading; pulls `tracker/parser.py` (and its `mido` import) into the CLI startup
  path for nothing.
- **Related**: F-14 / TD-12 (the third-parser-drift family); the legacy parser's only real
  consumers are `nes/song_bank.py`, `benchmarks/`, and tests.
- **Suggested Fix**: Remove the `main.py:16` import.

### TD-07: `nes/audio_constants.py` / scattered note-name tables vs the exporters' inline copies
- **Severity**: LOW
- **Dimension**: 3 — Stale Documentation & Comments (note-name table consistency)
- **Location**: `exporter/exporter.py:11` (`NOTE_TABLE`/`midi_note_to_ft`) and
  `exporter/exporter_famistudio.py:160-163` (`midi_note_to_famistudio`)
- **Status**: NEW
- **Description**: `midi_note_to_ft` and `midi_note_to_famistudio` are near-identical
  MIDI-note→note-name converters (`octave = (note // 12) - 1`, index a 12-name table), each with
  its own inline note-name array. They differ only in formatting (`C` vs `C-`), so the shared
  octave/index logic is duplicated and the two name tables can drift independently.
- **Evidence**: `exporter/exporter.py:9-13` vs `exporter/exporter_famistudio.py:158-163` — same
  formula, two separate `NOTE`/`NOTE_NAMES` literals.
- **Impact**: Cosmetic export drift only (FamiTracker/FamiStudio text), not ROM output. Low.
- **Related**: TD-01 (the same duplicate-formula pattern on the pitch path).
- **Suggested Fix**: Factor a shared `midi_note_to_name(note, sep)` helper in a common exporter
  util and pass the separator.

### TD-08: Stale `; TODO: Insert actual .incbin statements for DPCM files here` marker (work done elsewhere)
- **Severity**: LOW
- **Dimension**: 4 — Stale Markers
- **Location**: `exporter/exporter_ca65.py:858`
- **Status**: NEW
- **Description**: The macro-bytecode export (the **default** patterns path) emits a
  `.segment "DPCM"` block whose only content is a TODO comment claiming `.incbin` statements are
  not yet inserted. In practice the real DPCM `.incbin` lines and lookup tables are produced by
  `dpcm_sampler/dpcm_packer.py:88` and appended to `music.asm` by the pipeline
  (`main.py:531-565`). The TODO is therefore stale: it describes work that is done in another
  module, and the surrounding comment at `exporter_ca65.py:865-868` already explains the packer
  owns those tables. This is the only TODO/FIXME/HACK/XXX in non-test source.
- **Evidence**: `grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py' .` → single hit at
  `exporter_ca65.py:858`. DPCM `.incbin` actually emitted at `dpcm_packer.py:81-88`; packed into
  the project at `main.py:255` (`DpcmPacker`) and `main.py:531`.
- **Impact**: Misleading — implies a missing feature on the default path when DPCM packing exists.
  Not a stub on the live path (the work happens); hence LOW, not MEDIUM. The empty `.segment "DPCM"`
  here vs the packer's `DPCM_NN` segments is a separable correctness concern, not in scope for this
  audit.
- **Related**: TD-12; mapper/segment findings M-1/M-6 in `AUDIT_MAPPERS_2026-06-28.md`.
- **Suggested Fix**: Replace the TODO with a comment stating DPCM `.incbin`/tables are appended by
  `DpcmPacker` (with a pointer), or remove the empty segment if the packer owns it entirely.

### TD-09: `1789773` NES CPU-clock literal hardcoded in three places instead of one named constant
- **Severity**: LOW
- **Dimension**: 6 — Magic Numbers & Hardcoded Constants
- **Location**: `nes/pitch_table.py:19` (`CPU_CLOCK_RATE = 1789773`),
  `arranger/pipeline_integration.py:270` (`CPU_CLOCK = 1789773`)
- **Status**: NEW
- **Description**: The NTSC 2A03 clock (`docs/2A03_CPU_REFERENCE.md` — 1.789773 MHz) is named once
  as `CPU_CLOCK_RATE` in `nes/pitch_table.py` but re-typed as a bare `CPU_CLOCK = 1789773` in the
  arranger, with two different names for the same hardware constant. By contrast, the 60 Hz frame
  rate **is** centralized correctly in `constants.py` (`FRAME_RATE_HZ`/`FRAME_MS`), used by both
  parsers and the tempo map — the model to follow.
- **Evidence**: `grep -rnE "1789773|CPU_CLOCK"` → the two definitions above; `constants.py:1-2`
  shows the centralized-constant pattern already in use elsewhere.
- **Impact**: LOW (the literal is correct today, per `docs/2A03_CPU_REFERENCE.md`); the risk is a
  future PAL/value change touching only one copy. Cited doc confirms the value is right.
- **Related**: TD-01 (the formula that consumes it).
- **Suggested Fix**: Import `CPU_CLOCK_RATE` from `nes/pitch_table.py` (or hoist it next to
  `FRAME_RATE_HZ` in `constants.py`) and delete the arranger's local copy.

### TD-10: `except: break` / `except: pass` idiom in `utils/profiling.py` swallows all errors
- **Severity**: LOW
- **Dimension**: 7 — Error-Handling Debt
- **Location**: `utils/profiling.py:89`, `:196`, `:300` (and a paired `except Exception` at
  `nes_devflow.py:107`, `debug/rom_tester.py:71`, `benchmarks/performance_suite.py:103`)
- **Status**: NEW
- **Description**: `utils/profiling.py` uses three bare `except:` clauses that silently `break`
  or fall back (memory-sampling loop at `:89`, `tracemalloc.get_traced_memory()` at `:196` and
  `:300`). Bare `except:` also catches `KeyboardInterrupt`/`SystemExit`. None of these are on the
  MIDI→ROM pipeline (profiling/benchmark/debug tooling only), so the blast radius is limited to
  benchmark accuracy — hence LOW, not MEDIUM. The pattern is the shared remedy worth noting:
  catch `Exception` (or the specific error), not a bare `except`.
- **Evidence**: `grep -rnE 'except\s*:'` in non-test source → `utils/profiling.py:89,196,300`,
  `debug/rom_tester.py:71`, `nes_devflow.py:107`, `benchmarks/performance_suite.py:103`.
  The core pipeline (`compiler/`, `tracker/parser_fast.py`) already uses typed/`except Exception`
  guards, so this debt is confined to tooling.
- **Impact**: Profiling/benchmark numbers can be silently wrong; a `KeyboardInterrupt` inside the
  sampler loop is swallowed. No effect on generated ROMs.
- **Related**: Overlaps `/audit-safety`; M-9 (broad `except` in `compile_rom`).
- **Suggested Fix**: Replace bare `except:` with `except Exception:` (or the specific exception)
  and log at debug level rather than silently discarding.

### TD-11: `exporter_ca65.export_direct_frames` is a ~773-line method; `run_full_pipeline` ~260 lines
- **Severity**: LOW
- **Dimension**: 8 — Module / Function Size & Structure
- **Location**: `exporter/exporter_ca65.py:59-831` (`export_direct_frames`, ~773 lines);
  `main.py:386-645` (`run_full_pipeline`, ~260 lines)
- **Status**: NEW
- **Description**: `export_direct_frames` is a single method spanning ~773 lines that emits pitch
  tables, per-channel playback routines (pulse/triangle/noise/DPCM), and the data tables inline —
  the file is 1154 lines total. `run_full_pipeline` is a ~260-line procedure threading parse →
  map/arrange → frames → patterns → export → DPCM-pack → prepare → compile → validate with inline
  branching. Both concentrate too much in one frame and are hard to test in isolation (cf. REG-05:
  exporter tests assert shape, not bytes, partly because the per-channel emitters aren't separately
  callable).
- **Evidence**: `awk` span of `export_direct_frames` → 773 lines; `wc -l` main.py = 997 with the
  pipeline occupying lines 386-645; per-channel blocks are inline string lists (e.g. the DPCM
  channel at `exporter_ca65.py:390`, `:684`).
- **Impact**: High change-cost and weak testability on the two hottest modules; correctness audits
  (NH-*, M-*) repeatedly point into these monoliths.
- **Related**: REG-05, TD-12.
- **Suggested Fix**: Extract per-channel emitters (`_emit_pulse`, `_emit_triangle`, `_emit_noise`,
  `_emit_dpcm`) from `export_direct_frames`, and split `run_full_pipeline` into per-stage helpers
  returning artifacts, so stages can be unit-tested.

### TD-12: Three drifting MIDI parsers with overlapping `parse_midi_to_frames` surface
- **Severity**: LOW
- **Dimension**: 1 — Logic Duplication
- **Location**: `tracker/parser_fast.py:8`, `tracker/parser.py:10`, `implementation_examples.py:3`
- **Status**: NEW (the *consolidation* debt; the song-bank consumer is Existing: #33 / F-14)
- **Description**: Three implementations of MIDI→frames coexist: the live `parser_fast.py`, the
  legacy `parser.py` (still imported by `nes/song_bank.py:7` and `benchmarks/`), and the
  abandoned root prototype `implementation_examples.py:parse_midi_with_tempo_changes`. Two expose
  the same public name `parse_midi_to_frames`. The song-bank consuming the *slow* parser is already
  tracked as issue **#33 / F-14** (third-parser drift); this finding records the broader
  consolidation debt and the dead prototype (overlaps TD-04/TD-06).
- **Evidence**: `grep` for `parse_midi_to_frames` importers: `parser_fast` (main + tests),
  `parser` (`nes/song_bank.py`, `benchmarks/performance_suite.py`, several tests),
  `implementation_examples.py` (no importers).
- **Impact**: A parse-behavior fix must be replicated across up to three places, or behavior
  diverges between the pipeline (fast) and song-bank analysis (slow).
- **Related**: Existing **#33 / F-14** (`SongBank` uses the old parser); TD-04, TD-06.
- **Suggested Fix**: Delete `implementation_examples.py` (TD-04); migrate `nes/song_bank.py` and
  benchmarks to `parser_fast`; retire `tracker/parser.py` once no consumer remains.

---

## Dedup notes

- **TD-08** (DPCM TODO) is *not* the mapper segment finding M-6/M-1 — those are about
  double-declared `.segment` directives (correctness); this is the stale comment only.
- **TD-12** explicitly defers the song-bank parser consumer to **Existing #33 / F-14** and only
  claims the consolidation/dead-prototype angle as NEW.
- No tech-debt finding here overlaps the open correctness issues (#22–#49); those are behavior
  bugs, this report is maintainability. The error-handling note TD-10 is scoped to tooling to
  avoid colliding with M-9 (`compile_rom` broad except, already open).
- `.nes` / `.log` / `.s` artifacts in the repo root are **gitignored** (`.gitignore` lines
  18-85), so they are not tracked cruft and are not reported.
</content>
</invoke>
