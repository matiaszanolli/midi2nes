---
description: "Audit end-to-end pipeline integrity and inter-stage data contracts"
argument-hint: "[--focus <dims>]"
---

# Pipeline Integrity Audit

Audit the end-to-end conversion chain — parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate — as a single contract-bound system. The job is not to
re-audit each stage's internal correctness (the subsystem skills own that); it is to verify
that **each stage emits exactly what the next stage consumes**, that the subcommand-less
`run_full_pipeline` path stays in lockstep with the step-by-step subcommands, that global
flags route into both paths, and that a failure at any stage stops the run instead of leaving
a stale or broken `.nes` on disk.

Read `.claude/commands/_audit-common.md` first — it defines the project layout, the
**Inter-Stage Data Contracts** table (the authority for what each stage hands off), the
Python-specific drift rules, the dedup protocol, and the per-finding format. Read
`.claude/commands/_audit-severity.md` for the severity scale and the Special-Rules floors.
Do **not** restate either file here; this skill only adds the pipeline-specific dimensions.

A large batch of pipeline bugs (F-01..F-13, SAFE-01, SAFE-04, PL-01, PL-02) was fixed in a
recent sprint — several dimensions below now describe **verify-the-fix** checks rather than
live bugs. A few new, narrower issues (PL-03..PL-06) were found while verifying those fixes
and remain open; they're called out where they apply.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 1,4`). Default: all.

## Extra Per-Finding Field
- **Dimension**: one of the dimensions below.
- **Both paths?**: does the finding affect the default `run_full_pipeline` path, the
  step-by-step subcommands, or both? (A divergence between the two is itself the finding.)

## Dimensions

### Dimension 1: Stage JSON Contract Integrity
Every step-by-step subcommand reads a JSON file written by the previous one. Confirm each
producer key matches each consumer's read. Concrete checks in `main.py`:
- `run_parse` writes `{"events": ..., "metadata": ...}` (from `tracker/parser_fast.py`
  `parse_midi_to_frames`). `run_map` reads it via `load_json_stage(args.input, ['events'],
  'parse')` (`main.py:76`), which now fails with a clean `[ERROR]` message and exit 1 —
  rather than a bare `KeyError`/`FileNotFoundError`/`JSONDecodeError` — on a missing/corrupt/
  wrong-stage file (`load_json_stage`, `main.py:36-65`; SAFE-01/#120, closed). Verify: every
  call site's `required_keys` list actually names what that stage's body indexes next —
  `run_frames`/`run_export`/`run_detect_patterns` pass `[]` since they only iterate the
  (all-optional) channel dict rather than a fixed key; confirm that's genuinely safe rather
  than a gap in the guard.
- `run_map` → `assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)`
  (`tracker/track_mapper.py`). `run_frames` (`main.py:84-91`) feeds that JSON straight into
  `NESEmulatorCore.process_all_tracks`. No change observed here; verify the mapped shape the
  emulator expects still equals what the mapper emits.
- `run_detect_patterns` (`main.py:389-393`) still saves only `{'patterns','references','stats'}`
  and omits `variations`, which both detectors (`tracker/pattern_detector.py`,
  `tracker/pattern_detector_parallel.py`) return. Confirm no consumer (`run_export`,
  `main.py:280-299`; `CA65Exporter.export_tables_with_patterns`) ever needs it — unresolved
  question, not a filed bug; keep checking on each audit pass.
- **The old "references-format gap" is now moot, for a different reason than expected**:
  `main.py` no longer builds a position→frame `ca65_references` map anywhere.
  `run_full_pipeline` (`main.py:611-618`) passes a bare empty dict `{}` for `references`
  regardless of what pattern detection produced; `run_export` (`main.py:292-299`) passes the
  detector's native `{'pattern_id': [positions]}` shape straight through unmodified. Both are
  inert: `CA65Exporter.export_tables_with_patterns` (`exporter/exporter_ca65.py:866-875`)
  explicitly documents that its `references` argument is **not consumed** — "retained for
  call-site compatibility" (F-01/#4, confirmed **intentional, documented behavior** per
  CLAUDE.md's Assembly Export section, not a bug to report). There is therefore no live
  format mismatch. The only residual risk worth a note: if `references` is ever wired up to
  actually affect output, the two call sites currently pass different shapes (`{}` vs.
  detector-native) — flag that latent inconsistency as a forward-looking risk, not a current
  finding.
- `grep` each contract key (`events`, `patterns`, `references`, `stats`, `compression_ratio`)
  across producer and consumer; a key renamed on one side only is the finding.

### Dimension 2: `run_full_pipeline` vs Step-by-Step Parity
- **Parser consistency (fixed)**: the old top-level `from tracker.parser import
  parse_midi_to_frames` import (the older full parser) no longer exists in `main.py`. Both
  entry points now import `parser_fast` locally and identically: `run_parse` (`main.py:69`)
  and `run_full_pipeline` (`main.py:504`), both as `from tracker.parser_fast import
  parse_midi_to_frames as parse_fast`. The wrong-parser divergence this bullet used to flag
  is gone. Verify no other stage reintroduces a third parser (see Dimension 8 — song-bank
  ingestion was independently fixed to use `parser_fast` too).
- **Pattern-detector parameter divergence (F-08/#19, closed)**: `main.py` now defines shared
  module-level constants `PATTERN_MIN_LENGTH = 3` / `PATTERN_MAX_LENGTH = 12` (`main.py:33-34`),
  and both `run_detect_patterns` (`main.py:358-359`) and `run_full_pipeline`'s parallel/
  fallback detector construction (`main.py:559`, `main.py:565`) use these same constants.
  Verify no other call site (arranger path, any test-only helper) still hardcodes different
  bounds that could reintroduce the drift.
- **`stats` schema divergence (fixed)**: the `--no-patterns` stub in `run_full_pipeline`
  (`main.py:590-599`) now uses exactly the key set both detectors emit —
  `original_size`/`compressed_size`/`compression_ratio`/`unique_patterns`
  (`tracker/pattern_detector.py:794-797`) — not the old `original_events`/`patterns_found`
  mismatch. Verify every `stats` reader (success banner `main.py:721-722`,
  `run_detect_patterns`'s banner `main.py:396`) only relies on keys present in both schemas.
- **Default-vs-step-by-step stage coverage (F-06/#15, closed)**: this gap is now closed by
  the `compile` subcommand (`main.py:217-239`), which runs `compile_rom` + `validate_rom`
  together — giving `prepare` → `compile` parity with the default path's compile+validate
  steps. The one residual asymmetry: `run_compile` has no backup/restore contract the default
  path has (see Dimension 6, PL-05/#178) — that is the piece of "parity" still missing.

### Dimension 3: Flag Routing (`--arranger` / `--no-patterns` / `--debug` / `--skip-validation` / `--version`)
Flags are parsed twice: argparse declares `--verbose`/`--debug`/`--arranger`/`--version` as
global options (`main.py:755-758`), but the hand-rolled dispatch in `main()` (the
`SimpleArgs` builder, `main.py:971-982`) re-derives them from a manually whitelisted
`global_args` list (`main.py:924-956`). Audit both:
- **Unknown/typo flags (F-03/#8, closed)**: the manual loop now `sys.exit(2)`s with
  `"Error: Unknown option: <arg>"` (`main.py:948-953`) for anything starting with `-` that
  isn't in the whitelist (`--verbose/-v`, `--debug/-d`, `--arranger/-a`, `--version`,
  `--no-patterns`, `--skip-validation`), instead of silently dropping it. Verify the
  whitelist stays in sync with the argparse-declared globals — a legitimate new global flag
  not yet added here would now hard-error rather than silently no-op (a usability regression
  risk, much lower severity than the original silent-song-change bug it replaced).
- **NEW, OPEN — `--version` combined with other args (#179/PL-06)**: `--version` is collected
  into `global_args` (`main.py:939-941`) but `SimpleArgs` (`main.py:971-980`) never reads it,
  so `python main.py --version song.mid` silently runs the full pipeline instead of printing
  the version and exiting — only the bare `python main.py --version` (argv length 2,
  special-cased at `main.py:892-894`) works. Confirm still reproducible; the fix direction is
  to check for `--version` in the manual loop and exit immediately, matching argparse's own
  `action='version'` semantics.
- **`--skip-validation` argparse parity (partially fixed)**: it is now also a first-class
  argparse argument on the `compile` subcommand (`main.py:829`, part of the #15 fix), not
  manual-default-path-only anymore. `--no-patterns` remains manual-default-path-only with no
  subcommand equivalent — this appears intentional (the per-subcommand analogue is simply
  omitting `--patterns` on `export`); flag only if you find an input where the default path's
  pattern-compression decision can't be reproduced via the step-by-step subcommands.
- **`--arranger` before a subcommand (#174/PL-01, closed)**: now rejected with a clear
  `sys.exit(2)` error (`main.py:903-914`) instead of being silently discarded. Verify the
  positive case still works: `--arranger` on the default path reaches `arrange_for_nes`
  (`main.py:514-518`) and produces a `{channel: {frame: {...}}}` structure the downstream
  pattern/export code accepts identically to `process_all_tracks`'s output (no drift
  observed; worth re-checking after any arranger refactor).
- **`--debug` → `run_prepare` parity (#175/PL-02, closed)**: `run_prepare` now passes
  `debug_mode=getattr(args, 'debug', False)` into `NESProjectBuilder` (`main.py:252`),
  matching the default path's `debug_mode` derivation (`main.py:682`). No divergence found.
- **`run_map --config`/`--dpcm-index` (F-05/#13, closed)**: `--dpcm-index` is honored
  (`main.py:78`, `getattr(args, 'dpcm_index', None) or 'dpcm_index.json'`); `--config` was
  removed from the `map` subcommand entirely (comment at `main.py:772-774`) rather than left
  declared-but-ignored — `detect-patterns`'s `--config` was dropped the same way
  (`main.py:803-806`). Verify no other subcommand still declares a flag its handler silently
  ignores (grep every `add_argument` call against the body of its `func=`).

### Dimension 4: Error Propagation & Fail-Fast (no broken ROM on stage failure)
The cardinal rule: a stage failure must abort before a stale/garbage `.nes` is left where the
user expects a good one.
- `run_full_pipeline`'s body is one `try` (`main.py:501`) / `except Exception` (`main.py:735`)
  / `finally` (`main.py:743-747`). Verify no inner `except` still swallows a fatal error and
  lets the run reach ROM emission:
  - The DPCM-pack block (`main.py:627-676`) catches broadly but is genuinely non-fatal by
    design — it records `dpcm_pack_warning` and surfaces it prominently in the success banner
    rather than burying it (SAFE-04/#123, closed); the ROM still builds without drums.
  - **NEW, OPEN — `validate_rom`'s own diagnostics-import guard (#177/PL-04)**: the
    `try/except Exception` around `ROMDiagnostics(...).diagnose_rom(...)` (`main.py:183-189`)
    returns `True` (ROM accepted) on *any* exception, and only prints a warning when
    `verbose=True`. This is meant for a bad ROM (which `diagnose_rom` already handles
    internally, returning an `"ERROR"` health), but it also fires on genuine infrastructure
    failures (e.g. an import error in `debug/rom_diagnostics.py`) — exactly the case where the
    boot-fatal vector/APU gate should NOT silently stand down. Flag as the one remaining
    "continues past a real failure" case in this dimension.
- CC65 failure surfacing (confirmed correct): `compile_rom` (`compiler/compiler.py:149-176`)
  converts `CompilationError`/`ValidationError`/any other exception into a `False` return with
  a printed `[ERROR]`; `compiler/cc65_wrapper.py` raises `ToolchainError`/`CompilationError`
  on a missing tool or nonzero `ca65`/`ld65` exit code (`compiler/cc65_wrapper.py:64-79,
  162-167, 225-230`; see `core/exceptions.py:88` `CompilationError`, `:158` `ToolchainError`).
  Both `run_full_pipeline` (`main.py:704-706`) and `run_compile` (`main.py:230-232`)
  `sys.exit(1)` on a `False` return. No gap found here.
- **`run_prepare` silent-exit-0 (F-06/#15, closed)**: `prepare_project`
  (`nes/project_builder.py:75`) is now called inside a `try/except Exception` that exits 1 on
  a raised exception, AND separately checks `if not prepared: sys.exit(1)` for a
  falsy-but-non-raising return (`main.py:256-263`). Verify `prepare_project`'s real failure
  modes (bad path, permissions) are covered by one of these two branches, not a third one that
  falls through silently.
- **ROM-validation gate only blocking on `ERROR` (F-02/#6, closed)**: `validate_rom`
  (`main.py:174-214`) now checks `reset_vectors_valid` and `apu_pattern_count == 0` as
  explicit `fatal_defects` (`main.py:191-200`) **before** consulting `overall_health` — a
  bad-vector or no-APU-init ROM is rejected regardless of what health score the diagnostics
  engine assigns it, closing the original gap. POOR/FAIR health with no fatal defect still
  only warns (`main.py:202-209`), which remains correct (non-boot-fatal). Verify completeness:
  `ROMDiagnosticResult` (`debug/rom_diagnostics.py:40-44`) only exposes
  `reset_vectors_valid`/`apu_pattern_count`/`assembly_code_score`/`overall_health` — a
  different boot-fatal condition (e.g. a mapper-number/`nes.cfg` mismatch, undetected PRG-bank
  overflow) would have to route through `overall_health`/`issues`, which is only ever a
  warning path here. Worth probing whether such a condition can occur and slip through.

### Dimension 5: Temp-File / Intermediate Handling
The default path writes intermediates into a `tempfile.TemporaryDirectory(prefix="midi2nes_")`
(`main.py:498`); the step-by-step path writes user-named JSON/asm files.
- Confirm the temp dir is the parent of `music.asm` (`main.py:604`) and `nes_project/`
  (`main.py:679`), and that `compile_rom(project_path, output_rom)` (`main.py:704`) writes the
  final ROM to `output_rom` — the user's path, outside the temp dir — so it survives
  `TemporaryDirectory` cleanup. Confirmed by reading the call; no late read of anything inside
  `temp_path` after the `with` block observed.
- **DPCM append-mode double-write (F-10/#23, STILL OPEN)**: `run_full_pipeline` appends to the
  fresh temp `music.asm` (`main.py:652`), which is safe (new file every run). `run_export`'s
  step-by-step path still does `with open(args.output, 'a') as f` (`main.py:339`) *after*
  `export_tables_with_patterns` has already (over)written that same file. Re-running the
  `export` subcommand onto a path that already contains a DPCM block from a previous run still
  risks duplicate `dpcm_*` symbols at assemble time — unchanged from the original finding;
  location updated to `main.py:339` (previously reported around 118-119).
- Step-by-step intermediates (`parsed.json`, `mapped.json`, etc.) remain user-managed and
  uncleaned — confirm no stage overwrites an input it still needs.

### Dimension 6: Backup & Overwrite Safety
- Backup path: `output_rom.with_suffix('.nes.backup')` (`main.py:484`). Re-verified directly:
  `Path('my.song.nes').with_suffix('.nes.backup')` → `my.song.nes.backup` —
  `Path.with_suffix` only replaces the text after the *last* dot, so a dotted stem does not
  cause an unexpected clobber as previously suspected. No finding here; this bullet can be
  dropped from future passes unless the naming scheme changes.
- **Restore-on-failure (F-11/#26, closed)**: now a single `finally` block
  (`main.py:743-747`) calls `_restore_backup` (`main.py:166-171`) whenever `build_succeeded`
  is still `False`. Because it's in `finally`, it covers every `sys.exit(1)` reached inside
  the `try` — compile failure, prepare failure, validation failure — **and** the top-level
  `except Exception` (`main.py:735-741`), unlike before where several exit points bypassed
  restore. Confirmed fixed; verify no code path returns out of the function before the `with`
  block's `finally` would run (none found).
- **Backup cleanup on success (F-12/#29, closed)**: `main.py:732-733` now does
  `backup_path.unlink(missing_ok=True)` immediately after `build_succeeded = True` is set.
  `.nes.backup` no longer lingers after a successful run; on a failed run it correctly stays
  in place (only the success branch deletes it). Confirmed fixed.
- **NEW, OPEN — a validation-failed ROM can still be left at the output path (#178/PL-05)**:
  `run_compile` (`main.py:217-239`) creates **no backup at all** before `compile_rom` writes
  to `output_rom`, so (a) any pre-existing good ROM at that path is overwritten with no
  restore option, and (b) on a validation failure the just-written unbootable ROM is left
  sitting at `output_rom` with only a nonzero exit code as the signal — parity with the
  default path's backup contract is missing here. Even on the default path, the same failure
  mode exists whenever no backup was created in the first place (a first-time build to a
  path that didn't exist yet — `backup_path` stays `None`, `main.py:482-486`): `_restore_backup`
  (`main.py:166-171`) is a no-op when `backup_path` is `None`, so a first build that fails
  validation leaves the bad ROM at the output path. Report this against Dimension 6, floor
  MEDIUM per `_audit-severity.md` (recoverable — the nonzero exit is the workaround signal —
  but violates the "no stale/broken `.nes` left where a good one is expected" rule in spirit).
- Step-by-step `export`/`prepare`/`frames` still silently overwrite their `output` with no
  backup — unchanged; acceptable for intermediate files, flag only if `export` clobbers a
  hand-edited `music.asm` in a way that's surprising.

### Dimension 7: Large-File Threshold & Pattern-Detector Fallback Hand-off
`run_full_pipeline` has a `LARGE_FILE_THRESHOLD = 10000` (`main.py:550`) and a
parallel→sequential fallback (`main.py:556-580`).
- The threshold only **prints a suggestion** to use `--no-patterns` (`main.py:552-554`); it
  does not change behavior. Still true, still intentional — confirm the message stays
  accurate as sampling behavior changes elsewhere.
- **Truncation-to-2000 (F-04/#10, closed — but see PL-03 below)**: the fallback no longer
  does `events = events[:2000]`. It now calls `sample_events_for_detection(events,
  DETECTOR_MAX_EVENTS)` (`main.py:572`; `DETECTOR_MAX_EVENTS = 1000`,
  `tracker/pattern_detector.py:23`), which samples *uniformly* across the whole song
  (`np.linspace`, `tracker/pattern_detector.py:26-38`) rather than head-cutting it, so
  musical structure is preserved in what pattern detection sees. This closes the literal
  silent-truncation/song-shortening bug F-04 described.
- **NEW, OPEN — the fallback's warning message is itself wrong (#176/PL-03)**: when sampling
  triggers, `main.py:574-579` still prints "the ROM is INCOMPLETE... Re-run with
  --no-patterns for full fidelity." This is false: the sampled `events` list feeds only
  pattern-detection's compression *analysis*; every emitted ROM byte still derives from the
  full `frames` dict regardless of `patterns` (per CLAUDE.md's Assembly Export section and
  `exporter/exporter_ca65.py:873-875`, where `patterns` truthiness only selects
  `export_direct_frames` vs. the macro-bytecode serializer — both iterate the complete frame
  range). The ROM is not incomplete, and the advice to re-run with `--no-patterns` makes the
  ROM *larger* for zero fidelity gain (no compression at all). This replaces the old F-04
  framing: don't hunt for data loss here (there isn't any), hunt for the message's accuracy.
  Also flag the inconsistency with the parallel detector's own internal sampling
  (`tracker/pattern_detector_parallel.py:47-50`, `MAX_PATTERN_EVENTS = 15000`), which prints
  only an inline "lossy" percentage note with no "INCOMPLETE" framing for the same class of
  event — two sampling events of the same kind get opposite messaging.
- **`run_detect_patterns` asymmetry (F-09/#21, closed)**: the step-by-step subcommand now
  also samples via `sample_events_for_detection(events, DETECTOR_MAX_EVENTS)`
  (`main.py:380`) with an equivalent warning (`main.py:381-383`), matching the default path's
  fallback behavior — the old "no fallback, no threshold, processes the full set unbounded"
  asymmetry is gone. Verify: the *parallel* detector (used by default when it succeeds) still
  has a different, higher cap (`MAX_PATTERN_EVENTS = 15000`, `tracker/pattern_detector.py:16`)
  than the sequential detector/subcommand (`DETECTOR_MAX_EVENTS = 1000`) — this remains an
  intentional, documented complexity-driven difference (comments at
  `tracker/pattern_detector.py:14-23`: parallel is O(n) hash-grouping, sequential is
  O(n^2)-ish), not a bug.
- Confirm the fallback's `except Exception` (`main.py:562`) still genuinely catches what
  `ParallelPatternDetector` can realistically raise (pickling/worker errors) rather than only
  trivial exceptions — no change observed here; still worth a real multiprocessing-failure
  spot-check. A parallel crash with no fallback firing is a HIGH floor.

### Dimension 8: Song-Bank Path
The `song` subcommands (`run_song_add`/`run_song_list`/`run_song_remove`) operate on a JSON
bank via `nes/song_bank.py` (`SongBank.add_song_from_midi`, `export_bank`, `import_bank`).
- **Disjoint from the main pipeline (F-13/#30)**: this remains true, and per project status
  is a **known roadmap gap, not a bug to hunt for** — `docs/ROADMAP.md` (lines 54-61)
  explicitly lists "Song banks → ROM" as an open item, and `SongBank` (`nes/song_bank.py:30-188`)
  has no build/compile method. Only flag this dimension if `docs/ROADMAP.md`'s stated status
  drifts from what the code actually supports (doc-rot, LOW/MEDIUM) — not as a functional
  defect.
- `run_song_add` derives `metadata` from CLI args and defaults the bank to `song_bank.json`
  when `--bank` is omitted (`main.py:403-420`); `run_song_list`/`run_song_remove`
  (`main.py:422-460`) require a positional `bank`. Unchanged; verify the add-default and the
  list/remove-required asymmetry can't silently write to a different file than the user reads.
- **Parser drift (fixed)**: `add_song_from_midi` (`nes/song_bank.py:72-89`) now calls
  `parse_midi_to_frames` imported from `tracker.parser_fast` (`nes/song_bank.py:11`) instead
  of an independent third parser — fixed by commit `d8f6a0e` (#33/#34). Verify the segment
  shape `_process_segments` (`nes/song_bank.py:91`) expects from `parse_midi_to_frames`'s
  output still matches what `run_parse`/`run_map` treat as canonical, since this is now a
  second, independent consumer of that output shape.

## Output
Write the report to **`docs/audits/AUDIT_PIPELINE_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — finding counts per dimension; the single most dangerous contract break; an
   explicit yes/no on "does the step-by-step path produce the same ROM as the default path?".
2. **Contract Map** — a short table of each stage boundary (producer fn → key(s) → consumer
   fn) with a ✓/✗ for "verified matching".
3. **Findings** — base per-finding format from `_audit-common.md` plus `Dimension` and
   `Both paths?`. Apply the `_audit-severity.md` floors: contract break = HIGH, silent song
   change (truncation, ignored flag, wrong refs) = CRITICAL.

Then suggest:
```
/audit-publish docs/audits/AUDIT_PIPELINE_<TODAY>.md
```
