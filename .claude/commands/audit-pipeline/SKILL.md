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

A large batch of pipeline bugs (F-01..F-13, SAFE-01, SAFE-04, PL-01..PL-06) has since been
fixed — every dimension below now describes **verify-the-fix** checks rather than live bugs.
The narrower issues (PL-03..PL-06) found while verifying the first batch are now closed too;
confirm each fix still holds and treat any regression as a fresh finding.

**Exception — Dimension 8 is not a verify-the-fix dimension.** The `song build` jukebox path
(#30/F-13) shipped recently and is the youngest code in the pipeline; its first audit pass
already found two defects that made it produce zero working ROMs at any bank size
(PL-2026-08-07-1 and friends, fixed in `8ea7ac3`). Audit it as new code, not as a
regression check.

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
  'parse')`, which now fails with a clean `[ERROR]` message and exit 1 —
  rather than a bare `KeyError`/`FileNotFoundError`/`JSONDecodeError` — on a missing/corrupt/
  wrong-stage file (`load_json_stage`, `main.py:88-139`; SAFE-01/#120, closed). **Fixed
  (#485/PIPE-2026-08-22-1, closed; regression of #377/PIPE-2026-07-19-1)**:
  `run_frames`/`run_export`/`run_detect_patterns` still pass `required_keys=[]` (their input's
  channel keys are individually optional, so no single key can be required), but now also
  pass `channel_shape=True` — `load_json_stage` rejects a non-empty JSON object that has none
  of the five NES channel keys (`_PIPELINE_CHANNEL_KEYS`, `main.py:31`, a frozen copy of
  `CA65Exporter.SEQUENCE_CHANNELS` captured at import time so a test's `@patch('main.CA65Exporter')`
  can't silently empty it out), while still accepting a genuinely empty `{}` (an all-rest
  song). This was previously a real gap — a parse-stage or detect-patterns-stage file fed to
  the wrong subcommand silently produced an empty-but-exit-0 result at every stage
  downstream — verify the guard still fires on a wrong-stage file and still passes a
  legitimate empty frames dict.
- `run_map` → `assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)`
  (`tracker/track_mapper.py`). `run_frames` (`main.py:278-313`) feeds that JSON straight into
  `NESEmulatorCore.process_all_tracks`. No change observed here; verify the mapped shape the
  emulator expects still equals what the mapper emits.
- **Fixed (#498/PAT-2026-08-23-1, closed)**: `run_detect_patterns` (`main.py:784-861`) used to
  save only `{'patterns','references','stats'}` and omit `variations`, which both detectors
  (`tracker/pattern_detector.py`, `tracker/pattern_detector_parallel.py`) return. This is now
  fixed — the persisted `output` dict (`main.py:839-844`) includes
  `'variations': pattern_result['variations']`, matching the in-memory 4-key envelope. The
  in-memory `--no-patterns` stub already carried `'variations': {}` since #258/PAT-09 (the
  stub lives in `detect_patterns_or_direct_export`, `main.py:1149-1273`, extracted out of
  `run_full_pipeline` since #406, which calls it for Step 4). Verify-the-fix: confirm the
  on-disk key stays present and that no consumer regresses to requiring only 3 keys.
- **#379/PIPE-2026-07-19-3 is CLOSED**: `export_frames_and_resolve_mapper` (the stage
  helper `run_full_pipeline` calls for Steps 5-5.5 since #406, `main.py:1274-1354`) used to
  hardcode a bare empty dict `{}` for `references` regardless of what pattern detection
  produced, while `run_export` passes the detector's native `{'pattern_id': [positions]}`
  shape (`pattern_data['references']`) straight through unmodified. Both entry points now
  pass `pattern_result['references']` — the real dict, not a hardcoded stand-in. This was
  already inert either way (`CA65Exporter.export_tables_with_patterns`,
  `exporter/exporter_ca65.py:1628-1648`, still documents `references` as **not
  consumed** — "retained for call-site compatibility", F-01/#4, confirmed
  **intentional** per CLAUDE.md's Assembly Export section), so the fix is
  forward-compatibility only: it does not change any emitted byte today. Verify-the-fix:
  if `references` is ever wired up to affect output, confirm both entry points still
  derive it from the same `pattern_result`/`pattern_data` source rather than drifting
  apart again — that was the exact shape of the original bug.
- `grep` each contract key (`events`, `patterns`, `references`, `stats`, `compression_ratio`,
  `variations`) across producer and consumer; a key renamed on one side only is the finding.

### Dimension 2: `run_full_pipeline` vs Step-by-Step Parity
- **Parser consistency (fixed)**: the old top-level `from tracker.parser import
  parse_midi_to_frames` import (the older full parser) no longer exists in `main.py`. Both
  entry points now import `parser_fast` locally and identically: `run_parse` (`main.py:250`)
  and `run_full_pipeline` (`main.py:1434`), both as `from tracker.parser_fast import
  parse_midi_to_frames as parse_fast`. The wrong-parser divergence this bullet used to flag
  is gone. Verify no other stage reintroduces a third parser (see Dimension 8 — song-bank
  ingestion was independently fixed to use `parser_fast` too).
- **Pattern-detector parameter divergence (F-08/#19, closed)**: `constants.py` (imported at
  `main.py:51`) now defines shared module-level constants `PATTERN_MIN_LENGTH = 3` /
  `PATTERN_MAX_LENGTH = 12`, and both `run_detect_patterns` (`main.py:807-809`) and the
  parallel/fallback detector construction `run_full_pipeline` calls into
  (`detect_patterns_or_direct_export`, extracted from `run_full_pipeline` since #406,
  `main.py:1229`/`:1237`) use these same constants. Verify no other call site (arranger path,
  any test-only helper) still hardcodes different bounds that could reintroduce the drift.
- **`stats` schema divergence (fixed)**: the `--no-patterns` stub — now living in
  `detect_patterns_or_direct_export` since #406, not inline in `run_full_pipeline`
  (`main.py:1163-1193`) — uses exactly the key set both detectors emit —
  `original_size`/`compressed_size`/`compression_ratio`/`unique_patterns`
  (`tracker/pattern_detector.py:922-929`) — not the old `original_events`/`patterns_found`
  mismatch. Verify every `stats` reader (success banner `main.py:1517-1521`,
  `run_detect_patterns`'s banner `main.py:850-860`) only relies on keys present in both schemas.
- **Default-vs-step-by-step stage coverage (F-06/#15, closed)**: this gap is now closed by
  the `compile` subcommand (`main.py:602-656`), which runs `compile_rom` + `validate_rom`
  together — giving `prepare` → `compile` parity with the default path's compile+validate
  steps. The former residual asymmetry (no backup/restore on `run_compile`) is now also closed:
  `run_compile` calls the shared `_backup_existing_rom`/`_restore_backup` helpers (Dimension 6,
  PL-05/#178, closed), so `prepare` → `compile` now matches the default path's backup contract too.
  Note a further divergence since #457/SAFE-2026-08-21-3 (see Dimension 4): `run_compile`
  still converts a bool `False` from `compile_rom`/`validate_rom` into a direct `sys.exit(1)`
  (`main.py:635-641`), while `run_full_pipeline`/`run_song_build` now go through the shared
  `build_and_validate_rom` (`main.py:1355-1400`), which *raises* typed `MIDI2NESError`
  subclasses instead, caught by one `except MIDI2NESError` clause in each caller. Both reach
  the same outcome (clean `[ERROR]` + exit 1 + backup restore), just via different
  mechanisms — not a functional gap, but worth knowing before assuming the two paths share
  one code path here.

### Dimension 3: Flag Routing (`--arranger` / `--no-patterns` / `--debug` / `--visualizer` / `--skip-validation` / `--version`)
Flags are parsed twice: argparse declares `--verbose`/`--debug`/`--visualizer`/`--arranger`/
`--version` as global options (`main.py:1576-1580`), but the hand-rolled dispatch in `main()`
(the `SimpleArgs` builder, `main.py:1852-1866`) re-derives them from a manually whitelisted
`global_args` list (`main.py:1783-1831`). Audit both:
- **Unknown/typo flags (F-03/#8, closed)**: the manual loop now `sys.exit(2)`s with
  `"Error: Unknown option: <arg>"` (`main.py:1829`) for anything starting with `-` that
  isn't in the whitelist (`--verbose/-v`, `--debug/-d`, `--visualizer`, `--arranger/-a`,
  `--version`, `--no-patterns`, `--skip-validation`), instead of silently dropping it. Verify
  the whitelist stays in sync with the argparse-declared globals — a legitimate new global
  flag not yet added here would now hard-error rather than silently no-op (a usability
  regression risk, much lower severity than the original silent-song-change bug it replaced).
  **Verified live**: the `--visualizer` flag added alongside this report's cycle is correctly
  present in both the argparse declaration (`main.py:1579`) and this whitelist loop
  (`main.py:1795-1797`) — the class of gap this bullet exists to catch did not recur.
- **`--version` combined with other args (#179/PL-06, closed)**: the manual loop now matches
  argparse's `action='version'` semantics — a `--version` token prints `MIDI2NES <ver>` and
  `sys.exit(0)`s immediately inside the loop (`main.py:1801-1807`), before any input file is
  consumed, so `python main.py --version song.mid` no longer silently runs the full pipeline.
  The bare `python main.py --version` (argv length 2) still short-circuits earlier at
  `main.py:1738`. Verify both forms exit 0 and print the version, and that no path files
  `--version` into `global_args` where `SimpleArgs` would ignore it again.
- **`--skip-validation` argparse parity (partially fixed)**: it is now also a first-class
  argparse argument on the `compile` subcommand (`main.py:1662`, part of the #15 fix) and on
  `song build` (`main.py:1704`), not manual-default-path-only anymore. `--no-patterns` remains
  manual-default-path-only with no subcommand equivalent — this appears intentional (the
  per-subcommand analogue is simply omitting `--patterns` on `export`); flag only if you find
  an input where the default path's pattern-compression decision can't be reproduced via the
  step-by-step subcommands.
- **`--arranger` before a subcommand (#174/PL-01, closed)**: now rejected with a clear
  `sys.exit(2)` error (`main.py:1755-1770`) instead of being silently discarded — and, since
  **#487/PIPE-2026-08-22-3** (closed), the message correctly special-cases `song build
  --arranger` (which now has its own `--arranger`, `main.py:1701`) instead of claiming no
  step-by-step equivalent exists anywhere. Verify the positive case still works: `--arranger`
  on the default path reaches `arrange_for_nes` (`main.py:1444-1448`) and produces a
  `{channel: {frame: {...}}}` structure the downstream pattern/export code accepts identically
  to `process_all_tracks`'s output (no drift observed; worth re-checking after any arranger
  refactor).
- **`--debug`/`--visualizer` → `run_prepare` parity (#175/PL-02, closed; `--visualizer` new)**:
  `run_prepare` now passes `debug_mode=getattr(args, 'debug', False)` and
  `visualizer_mode=getattr(args, 'visualizer', False)` into `NESProjectBuilder`
  (`main.py:672-673`), matching the default path's derivation (`main.py:1500-1501`). Both
  flags are declared only on the top-level parser (no subcommand-local re-declaration for
  either), so both rely on argparse's flag-before-subcommand form (`python main.py --debug
  prepare ...`, confirmed working directly against `argparse`) — `prepare --debug ...` (flag
  *after* the subcommand) is NOT accepted by that subparser and errors with "unrecognized
  arguments", which is pre-existing behavior for `--debug`, not a new gap introduced by
  `--visualizer`. `_reject_debug_visualizer_combo` (`main.py:587-600`) rejects the combination
  with a clear message on both the subcommand-dispatch path (`main.py:1775`) and the default
  pipeline path (`main.py:1869`), in both cases after the flag is populated onto `args`.
- **`run_map --config`/`--dpcm-index` (F-05/#13, closed)**: `--dpcm-index` is honored
  (`main.py:259` `run_map`, reading `getattr(args, 'dpcm_index', None) or 'dpcm_index.json'`);
  `--config` was removed from the `map` subcommand entirely rather than left
  declared-but-ignored. `detect-patterns`'s `--config` was subsequently **re-added** for a
  narrow, genuinely-consumed purpose — it overrides only the pattern-detection sampling caps
  (`processing.pattern_detection.max_events`/`max_pattern_events`, #219) via
  `get_pattern_detection_caps` (`main.py:58-86`), declared at `main.py:1629` and read at
  `main.py:792`; it does **not** touch tempo or `PATTERN_MIN/MAX_LENGTH`. Verify no other
  subcommand still declares a flag its handler silently ignores (grep every `add_argument`
  call against the body of its `func=`).

### Dimension 4: Error Propagation & Fail-Fast (no broken ROM on stage failure)
The cardinal rule: a stage failure must abort before a stale/garbage `.nes` is left where the
user expects a good one.
- `run_full_pipeline`'s body is one `try` (`main.py:1431`) / `except Exception` (`main.py:1554`)
  / `finally` (`main.py:1564-1567`). Verify no inner `except` still swallows a fatal error and
  lets the run reach ROM emission:
  - The DPCM-pack step catches broadly but is genuinely non-fatal by design — it records
    a `DpcmPackResult.warning` and surfaces it prominently in the success banner rather than
    burying it (SAFE-04/#123, closed); the ROM still builds without drums. **#380/TD-28
    closed**: the pack logic used to be duplicated inline in both `run_full_pipeline` and
    `run_export`; it now lives in one shared `pack_dpcm_into_asm` helper (`main.py:159-249`,
    `except Exception as e:` at `:233`) called from both (`run_export` at `main.py:764`;
    `export_frames_and_resolve_mapper` at `:1328` — the stage helper `run_full_pipeline`
    calls for this since #406), so this check only needs verifying once instead of per call
    site. **#367/DP-DPCM-05 closed**: the
    warning used to fire only on an all-samples-missing pack; a partial miss (some but not all
    referenced samples resolve) now also warns, labeled "PARTIAL DPCM MISS" vs "NO DRUMS"
    (`main.py:781` / `:1528`) so a silently-dropped single drum isn't mistaken for "no
    warning printed, so it worked."
  - **`validate_rom`'s own diagnostics-import guard (#177/PL-04, closed)**: the
    `try/except Exception` around `ROMDiagnostics(...).diagnose_rom(...)` (`main.py:554-558`)
    now returns `False` (validation failed) — not `True` — on *any* exception, and prints the
    warning unconditionally (not only under `--verbose`). So an infrastructure failure (e.g. a
    broken import in `debug/rom_diagnostics.py`) is treated as a failed gate rather than a
    silently-accepted ROM. Callers only reach `validate_rom` when the user did NOT pass
    `--skip-validation`, so this is the correct fail-closed direction. Verify the return stays
    `False` and the message stays unconditional; this dimension no longer has an open
    "continues past a real failure" case here.
- CC65 failure surfacing (confirmed correct): `compile_rom` (`compiler/compiler.py:268-312`)
  converts `CompilationError`/`ValidationError`/any other exception into a `False` return with
  a printed `[ERROR]`; `compiler/cc65_wrapper.py` raises `ToolchainError`/`CompilationError`
  on a missing tool or nonzero `ca65`/`ld65` exit code throughout (e.g.
  `compiler/cc65_wrapper.py:47`, `:160`, `:231`; see `core/exceptions.py:88`
  `CompilationError`, `:169` `ToolchainError`). **Two different mechanisms reach the same
  outcome now (see Dimension 2's note)**: `run_compile` (`main.py:635-641`) still does a
  direct `sys.exit(1)` on a bool `False` return from `compile_rom`/`validate_rom`, while
  `run_full_pipeline`/`run_song_build` go through the shared `build_and_validate_rom`
  (`main.py:1355-1400`), which *raises* `ExportError`/`CompilationError`/`ValidationError`
  (all `MIDI2NESError` subclasses, #457/SAFE-2026-08-21-3) instead of returning bool, caught
  by one `except MIDI2NESError` clause in each caller. No gap found — both directions are
  fail-closed — but a future edit to either path should preserve the other's contract rather
  than assuming they share one code path.
- **`run_prepare` silent-exit-0 (F-06/#15, closed)**: `prepare_project`
  (`nes/project_builder.py:89`) is now called inside a `try/except Exception` that exits 1 on
  a raised exception, AND separately checks `if not prepared: sys.exit(1)` for a
  falsy-but-non-raising return (`main.py:677-685`). Verify `prepare_project`'s real failure
  modes (bad path, permissions) are covered by one of these two branches, not a third one that
  falls through silently.
- **ROM-validation gate only blocking on `ERROR` (F-02/#6, closed)**: `validate_rom`
  (`main.py:541-587`) now checks `reset_vectors_valid` and `apu_pattern_count == 0` as
  explicit `fatal_defects` (`main.py:561-567`) **before** consulting `overall_health` — a
  bad-vector or no-APU-init ROM is rejected regardless of what health score the diagnostics
  engine assigns it, closing the original gap. POOR/FAIR health with no fatal defect still
  only warns (`main.py:569-582`), which remains correct (non-boot-fatal). Verify completeness:
  `ROMDiagnosticResult` (`debug/rom_diagnostics.py:28-44`) only exposes
  `reset_vectors_valid`/`apu_pattern_count`/`assembly_code_score`/`overall_health` — a
  different boot-fatal condition (e.g. a mapper-number/`nes.cfg` mismatch, undetected PRG-bank
  overflow) would have to route through `overall_health`/`issues`, which is only ever a
  warning path here. Worth probing whether such a condition can occur and slip through.

### Dimension 5: Temp-File / Intermediate Handling
The default path writes intermediates into a `tempfile.TemporaryDirectory(prefix="midi2nes_")`
(`main.py:1428`; `run_song_build` has its own at `main.py:1077`); the step-by-step path writes
user-named JSON/asm files.
- Confirm the temp dir is the parent of `music.asm` and `nes_project/` (both still assigned
  directly in `run_full_pipeline`), and that `compile_rom(project_path, output_rom)` — called
  from `build_and_validate_rom` since #406 (`main.py:1355-1400`, the stage helper both
  `run_full_pipeline` and `run_song_build` call for the capacity/prepare/compile/validate
  sequence since #486/#467) — writes the final ROM to `output_rom` — the user's path, outside
  the temp dir — so it survives `TemporaryDirectory` cleanup. Confirmed by reading the call; no
  late read of anything inside `temp_path` after the `with` block observed.
- **DPCM append-mode double-write (F-10/#23, closed)**: both call sites append via the shared
  `pack_dpcm_into_asm` helper's `with open(asm_path, 'a') as f` (`main.py:159-249`, extracted in
  #380/TD-28 — previously two separate inline `open(..., 'a')` sites, one per call site).
  `run_full_pipeline` passes it the fresh temp `music.asm` (safe, new file every run);
  `run_export` passes `args.output` *after* `export_tables_with_patterns` already wrote the
  same path via the shared `atomic_write_text` helper first (`core/io_utils.py:13-38`,
  #385/SAFE-2026-07-19-3 — writes to a sibling temp file and `os.replace()`s it into place, so
  the target is fully replaced, not appended to, and never left partially written even on a
  mid-write crash; call sites `exporter/exporter_ca65.py:1129`, `:1703`, `:1850`), so it wipes
  the entire prior file, including any DPCM block appended on an earlier run, before the fresh
  append. A re-run therefore lands the append into a freshly-replaced file and cannot
  accumulate duplicate `dpcm_*` symbols. Verify the exporter still fully replaces the file
  (whether via `atomic_write_text` or a future equivalent) rather than appending; if it ever
  switches to append mode, the original double-write hazard returns — and now only needs
  fixing once at the shared `pack_dpcm_into_asm` call sites, not twice.
- Step-by-step intermediates (`parsed.json`, `mapped.json`, etc.) remain user-managed and
  uncleaned — confirm no stage overwrites an input it still needs.

### Dimension 6: Backup & Overwrite Safety
- Backup path: `output_rom.with_suffix('.nes.backup')`, now created by the shared
  `_backup_existing_rom` helper (`main.py:510-524`). Re-verified directly:
  `Path('my.song.nes').with_suffix('.nes.backup')` → `my.song.nes.backup` —
  `Path.with_suffix` only replaces the text after the *last* dot, so a dotted stem does not
  cause an unexpected clobber as previously suspected. No finding here; this bullet can be
  dropped from future passes unless the naming scheme changes.
- **Restore-on-failure (F-11/#26, closed)**: now a single `finally` block
  (`main.py:1564-1567`) calls `_restore_backup` (`main.py:526-540`) whenever `build_succeeded`
  is still `False`. Because it's in `finally`, it covers every `sys.exit(1)` reached inside
  the `try` — compile failure, prepare failure, validation failure — **and** the top-level
  `except Exception` (`main.py:1554-1561`), unlike before where several exit points bypassed
  restore. Confirmed fixed; verify no code path returns out of the function before the `with`
  block's `finally` would run (none found). **#486/PIPE-2026-08-22-2 (closed) extended this
  same contract to `run_song_build`** (`main.py:999-1118`), which used to have no backup/
  restore at all — it now calls `_backup_existing_rom` up front (`main.py:1074`) and shares
  `build_and_validate_rom` (below) plus an equivalent `try`/`except MIDI2NESError`/
  `except Exception`/`finally` structure (`main.py:1099-1115`), giving all three ROM-build
  entry points (`run_full_pipeline`, `run_compile`, `run_song_build`) the same contract.
- **Backup cleanup on success (F-12/#29, closed)**: `main.py:1536` (in
  `run_full_pipeline`) now does `backup_path.unlink(missing_ok=True)` immediately after
  `build_succeeded = True` is set. `.nes.backup` no longer lingers after a successful run; on
  a failed run it correctly stays in place (only the success branch deletes it). Confirmed
  fixed.
- **Validation-failed ROM left at the output path (#178/PL-05, closed)**: `run_compile`
  (`main.py:602-656`) now backs up a pre-existing ROM via the shared `_backup_existing_rom`
  (`main.py:632`) and, in a `finally`, restores it on any compile/validation failure
  (`main.py:651-656`) — matching the default path's contract. The first-time-build case (no
  pre-existing ROM, so `backup_path` is `None`) is also handled: `_restore_backup`
  (`main.py:526-540`) moves the just-written unbootable ROM aside to `<name>.nes.failed`
  rather than leaving a broken `.nes` at the output path. `run_full_pipeline`, `run_compile`,
  and (since #486) `run_song_build` all share these two helpers, so the contract is uniform
  across all three. Verify the `finally` restore path still fires on a validation-only failure
  (compile OK, `validate_rom` returns False) and that a first-time failed build produces
  `<name>.nes.failed`, not a bootable-looking `<name>.nes`.
- Step-by-step `export`/`prepare`/`frames` still silently overwrite their `output` with no
  backup — unchanged; acceptable for intermediate files, flag only if `export` clobbers a
  hand-edited `music.asm` in a way that's surprising.

### Dimension 7: Large-File Threshold & Pattern-Detector Fallback Hand-off
`detect_patterns_or_direct_export` (`main.py:1149-1273`, Step 4, extracted out of
`run_full_pipeline` by #406) has an advisory `large_file_threshold` check (`main.py:1221`) and
a parallel→sequential fallback (`main.py:1225-1252`).
- The threshold only **prints a suggestion** (`main.py:1222-1223`); it does not change
  behavior. Still true, still intentional — confirm the message stays accurate as sampling
  behavior changes elsewhere. The threshold's default (`LARGE_FILE_THRESHOLD_DEFAULT =
  MAX_PATTERN_EVENTS`, `main.py:56`) and its `--config` override live in
  `get_pattern_detection_caps` (`main.py:58-86`), not a bare module constant any more.
- **Truncation-to-2000 (F-04/#10, closed)**: the fallback no longer
  does `events = events[:2000]`. It now calls `sample_events_for_detection(events,
  max_events)` (`main.py:1244`; default `DETECTOR_MAX_EVENTS = 300`,
  `tracker/pattern_detector.py:36`, lowered from 1000 by #459/TD-39), which samples
  *uniformly* across the whole song (`np.linspace`, `tracker/pattern_detector.py:39-51`)
  rather than head-cutting it, so musical structure is preserved in what pattern detection
  sees. This closes the literal silent-truncation/song-shortening bug F-04 described.
- **The fallback's warning message (#176/PL-03, closed)**: when sampling triggers,
  `main.py:1245-1251` no longer claims "the ROM is INCOMPLETE / re-run with --no-patterns for
  full fidelity." It now states the sampling feeds "compression analysis only — compression
  stats are approximate; ROM content is unaffected (#176/PL-03)", which is the accurate
  framing: the sampled `events` list feeds only pattern-detection's compression *analysis*;
  every emitted ROM byte still derives from the full `frames` dict regardless of `patterns`
  (per CLAUDE.md's Assembly Export section and `exporter/exporter_ca65.py:1628-1648`, where
  `patterns` truthiness only selects `export_direct_frames` vs. the macro-bytecode serializer —
  both iterate the complete frame range). Verify the message still describes analysis-only
  loss (not ROM incompleteness), and that it stays consistent with the parallel detector's own
  internal-sampling note (`tracker/pattern_detector_parallel.py:73`,
  `MAX_PATTERN_EVENTS = 15000`), which prints an inline "lossy" percentage — both now describe
  the same class of event as analysis-only, no longer contradicting each other.
- **`run_detect_patterns` asymmetry (F-09/#21, closed)**: the step-by-step subcommand
  (`main.py:784-861`) now also samples via `sample_events_for_detection(events, max_events)`
  (`main.py:825`) with an equivalent warning (`main.py:826-828`), matching the default path's
  fallback behavior — the old "no fallback, no threshold, processes the full set unbounded"
  asymmetry is gone. Verify: the *parallel* detector (used by default when it succeeds) still
  has a different, higher cap (`MAX_PATTERN_EVENTS = 15000`, `tracker/pattern_detector.py:17`)
  than the sequential detector/subcommand (`DETECTOR_MAX_EVENTS = 300`) — this remains an
  intentional, documented complexity-driven difference (comments at
  `tracker/pattern_detector.py:9-36`: parallel is O(n) hash-grouping, sequential is
  O(n^2)-ish), not a bug. Both caps are now overridable via `--config` (#219) through
  `get_pattern_detection_caps` (`main.py:58-86`); verify the override keeps the two paths in
  sync.
- Confirm the fallback's `except Exception` (`main.py:1232`) still genuinely catches what
  `ParallelPatternDetector` can realistically raise (pickling/worker errors) rather than only
  trivial exceptions — no change observed here; still worth a real multiprocessing-failure
  spot-check. A parallel crash with no fallback firing is a HIGH floor.

### Dimension 8: Song-Bank Path
The `song` subcommands (`run_song_add` `main.py:862-900`, `run_song_list` `main.py:901-927`,
`run_song_remove` `main.py:928-949`, `run_song_build` `main.py:999-1118`) operate on a JSON
bank via `nes/song_bank.py` (`SongBank.add_song_from_midi`, `export_bank`, `import_bank`).
- **#30/F-13 is CLOSED — the bank is no longer disjoint from the pipeline.** `song build
  <bank.json> <out.nes>` now compiles a bank into a real multi-song "jukebox" ROM, and
  `docs/ROADMAP.md` § "Song banks → ROM" is marked "v1 shipped, follow-ups remain". The old
  prose here told auditors to treat this dimension as a roadmap gap and *not* look for
  functional defects — that instruction is retired: this is now live code carrying a full
  second contract chain (see `_audit-common.md` § Inter-Stage Data Contracts, the `song build`
  sub-list) and is audited like any other path. Verify-the-fix: the v1 scope cuts (MMC3-only,
  DPCM rejected per-song, no `--debug`, no visual menu) are *documented* follow-ups in
  `docs/ROADMAP.md:69-76` — flag those only as doc-rot if the code and the roadmap disagree,
  never as functional defects. Anything **not** on that list is a real finding.
- **Bank ordering and re-parse contract**: `run_song_build` sorts by
  `bank.songs[name]['metadata'].get('order', 0)` (`main.py:1025-1026`) — this is the first and
  only consumer of `order`, which `run_song_add` has always written; `order` collisions after a
  remove+add cycle were fixed by **#488/PIPE-2026-08-22-4** (`SongBank._next_order`,
  `nes/song_bank.py:57-70`, derives the next value from `max(existing) + 1` instead of
  `len(self.songs)`, which used to reuse a removed song's freed slot — verify this still holds).
  `run_song_build` then rebuilds frames from each song's recorded `midi_path`
  (`main.py:1046-1050` via `midi_to_frames_for_song`), **not** from the stored `segments`.
  Verify: `segments` are raw parsed events with no channel mapping, so any future change that
  makes `song build` read them instead is a silent corruption, not a shortcut; and a bank whose
  `midi_path` is missing or has moved must still exit non-zero with a clear message
  (`main.py:1036-1042`) rather than building a partial ROM.
- **Per-song DPCM rejection**: `_song_has_dpcm_events(frames)` (`main.py:982-998`, called at
  `:1052`) hard-fails the whole build with an explanatory error before any export. Verify it
  inspects the *frames* actually being exported (not the bank metadata) so a song that gains
  DPCM via `--arranger` can't slip past, and that a rejection leaves no partial `.nes` on disk
  (the whole build runs inside a `tempfile.TemporaryDirectory`, `main.py:1077`).
- **Capacity pre-flight**: since **#486/PIPE-2026-08-22-2 and #467/TD-32** (both closed),
  `run_song_build` no longer runs its own inline `check_mapper_capacity` call — it now shares
  the same `build_and_validate_rom` helper (`main.py:1355-1400`, capacity check at `:1379`)
  that `run_full_pipeline` uses, called at `main.py:1094-1096`. Verify N songs sharing one
  60-bank MMC3 pool are sized against the same limit the single-song path uses, now
  structurally guaranteed by sharing the one call site — an N-song overrun that only surfaces
  as a CC65 link error is a HIGH contract break.
- `run_song_add` derives `metadata` from CLI args and defaults the bank to `song_bank.json`
  when `--bank` is omitted (`main.py:1675`, `p_song_add.add_argument('--bank', ...)`);
  `run_song_list`/`run_song_remove` require a positional `bank`
  (`main.py:1687`/`:1691`). `run_song_build` takes the bank as a positional too
  (`main.py:1699`), so `add` is the only one with a default. Verify the add-default and the
  list/remove-required asymmetry can't silently write to a different file than the user reads.
- **Parser drift (fixed)**: `add_song_from_midi` (`nes/song_bank.py:81-103`) now calls
  `parse_midi_to_frames` imported from `tracker.parser_fast` (`nes/song_bank.py:11`) instead
  of an independent third parser — fixed by commit `d8f6a0e` (#33/#34). `midi_to_frames_for_song`
  (`main.py:950-981`, used by `run_song_build`'s re-parse) independently does the same
  (`from tracker.parser_fast import parse_midi_to_frames as parse_fast`, `main.py:966`) — a
  third confirmed-consistent call site. Verify the segment shape `_process_segments`
  (`nes/song_bank.py:105`) expects from `parse_midi_to_frames`'s output still matches what
  `run_parse`/`run_map` treat as canonical, since this is now a second, independent consumer of
  that output shape.
- **Verify fix (#427/PIPE-2026-08-21-5, closed)**: `import_bank`'s guard (#220/SAFE-09)
  used to validate only the bank-level shape (`bank_info`, `songs` presence) and store
  `data['songs']` as-is, with no per-entry validation. A song entry missing `'metadata'`
  (or non-dict, or missing `'bank'`/`'size'`) reached the sort key above
  (`bank.songs[name]['metadata'].get('order', 0)`) or `run_song_list`'s print loop as an
  unguarded `KeyError`/`AttributeError`, escaping as a raw traceback -- both call sites'
  `try/except` wraps only the `import_bank()` call itself, not their own subsequent
  indexing. `import_bank` now validates every song entry is a dict with a dict
  `'metadata'` and both `'bank'`/`'size'` keys present (the shape `add_song` always
  writes) before storing `self.songs`, raising the same `ValueError` style as the
  bank-level checks. Verify-the-fix: a bank with one malformed song entry among otherwise
  valid ones still fails the whole import (not a silent partial load) with a clean
  `[ERROR]` and nonzero exit from all three CLI entry points that call `import_bank`
  (`song list`/`song remove`/`song build`).
- **Verify fix (#487/PIPE-2026-08-22-3, closed)**: the pre-subcommand `--arranger` rejection
  message (Dimension 3) used to claim no step-by-step equivalent to `--arranger` existed for
  *any* subcommand, which became false once `song build` gained its own `--arranger`
  (`main.py:1701`, read at `run_song_build` via `getattr(args, 'arranger', False)`,
  `main.py:1028`). The message now special-cases `first_arg == 'song'`
  (`main.py:1762-1765`) with the correct fix ("place `--arranger` after `build`"). Verify a
  bare `--arranger song ...` still gets the song-specific message, not the generic one.

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
