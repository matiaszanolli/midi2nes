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
  `parse_midi_to_frames`). `run_map` reads `midi_data["events"]` — confirm the key, and that
  a parse output with no `events` key fails loudly, not with a bare `KeyError`.
- `run_map` → `assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)` whose
  signature is `assign_tracks_to_nes_channels(midi_events, dpcm_index_path)` in
  `tracker/track_mapper.py`. `run_frames` feeds that JSON straight into
  `NESEmulatorCore.process_all_tracks` (`nes/emulator_core.py`). Verify the mapped shape the
  emulator expects equals what the mapper emits.
- `run_detect_patterns` saves only `{'patterns','references','stats'}` — note it **omits
  `variations`**, which the detectors (`tracker/pattern_detector.py`,
  `tracker/pattern_detector_parallel.py`) do return. `run_export` reads
  `pattern_data['patterns']` and `pattern_data['references']`. Verify the consumer never
  needs `variations` (or flag the silent drop).
- **The references-format gap**: `run_detect_patterns` writes `references` in the detector's
  native `{'pattern_id': [positions]}` shape, but `run_export` passes that dict **straight**
  into `CA65Exporter.export_tables_with_patterns(frames, patterns, references, output_path)`
  (`exporter/exporter_ca65.py:646`) **without** the position→frame conversion that
  `run_full_pipeline` performs (`main.py` ~line 352, building `ca65_references` as
  `{frame_str: (pattern_id, offset)}`). Check whether the exporter accepts both shapes or
  whether `export prep.json out.s --patterns detected.json` produces wrong/garbage refs. A
  consumer that parses the producer's bytes as a different meaning is a contract corruption —
  severity floor HIGH (`_audit-severity.md`: "Pipeline stage JSON contract break"), CRITICAL
  if it silently changes which frames map to which pattern (the song plays differently).
- `grep` each contract key (`events`, `patterns`, `references`, `stats`, `compression_ratio`)
  across producer and consumer; a key renamed on one side only is the finding.

### Dimension 2: `run_full_pipeline` vs Step-by-Step Parity
The default path inlines the stages instead of calling the `run_*` functions, so the two can
drift. Diff them:
- `run_full_pipeline` parses with `tracker/parser_fast.py`'s `parse_midi_to_frames` (imported
  locally as `parse_fast`) — same as `run_parse`. Confirm both use the fast parser, not the
  top-level `from tracker.parser import parse_midi_to_frames` imported at `main.py:16` (which
  is the *older full parser*, per `_audit-common.md`). Flag if any path silently uses the
  wrong parser.
- Pattern detection differs by design: `run_full_pipeline` prefers
  `ParallelPatternDetector` with a fallback (Dimension 7), while `run_detect_patterns` uses
  `EnhancedPatternDetector` directly with `min_pattern_length=3` and **no**
  `max_pattern_length`, whereas the inline path passes `max_pattern_length=12`. Verify this
  parameter divergence does not change the compressed output between the two entry points for
  the same input (if it does, the step-by-step ROM ≠ the default ROM — MEDIUM, HIGH if it
  changes playback).
- The inline export builds `ca65_references` via position→frame mapping; `run_export` does
  not (Dimension 1). The `stats` dict the inline `--no-patterns` stub builds uses keys
  `original_events`/`compressed_size`/`patterns_found`, while the detectors emit
  `original_size`/`compressed_size`/`unique_patterns`. Confirm every later reader of `stats`
  (e.g. the success banner at end of `run_full_pipeline` reads
  `stats['compression_ratio']`) tolerates both key sets.
- Verify the default path covers prepare + compile + validate, which the step-by-step path
  only reaches via separate `prepare` + manual `build.sh`. Flag any stage present in one path
  but missing from the other.

### Dimension 3: Flag Routing (`--arranger` / `--no-patterns` / `--debug` / `--skip-validation`)
Flags are parsed twice: argparse declares `--verbose`/`--debug`/`--arranger` as global
options, but the hand-rolled dispatch in `main()` (the `SimpleArgs` builder, ~line 684)
re-derives them from a manually whitelisted `global_args` list. Audit both:
- The manual loop (`main.py` ~lines 643-669) only recognizes `--verbose/-v`, `--debug/-d`,
  `--arranger/-a`, `--version`, `--no-patterns`, `--skip-validation`; everything else
  starting with `-` is **silently skipped** (`# Skip unknown options`). Confirm a typo like
  `--no-pattern` or `--arrange` is silently ignored rather than erroring — that yields a ROM
  the user did not ask for (e.g. patterns applied when they meant `--no-patterns`). Silent
  song change → CRITICAL floor.
- `--no-patterns` and `--skip-validation` are **only** handled in the manual default path —
  they are never declared as argparse arguments. Confirm they do nothing (or error) if a user
  puts them on a subcommand like `parse`/`export`.
- `--arranger` routes to `arrange_for_nes(midi_data["events"], arp_speed=3, verbose=...)`
  (`arranger/__init__.py` re-exports it); the legacy branch routes to
  `assign_tracks_to_nes_channels` + `NESEmulatorCore`. Confirm both branches produce a
  `frames` structure the downstream pattern/export code accepts identically (the arranger
  output must be `{channel: {frame: {...}}}` like `process_all_tracks`).
- `--debug` flows into `NESProjectBuilder(..., debug_mode=debug_mode, ...)`. Confirm the flag
  reaches the builder in the default path and that there is no step-by-step equivalent
  (`run_prepare` constructs `NESProjectBuilder(args.output, mapper=MMC3Mapper())` with **no**
  `debug_mode`) — flag the inconsistency.
- `run_map` declares `--config` and `--dpcm-index` but `run_map`'s body **ignores both** and
  hardcodes `dpcm_index_path = 'dpcm_index.json'`. A declared flag that silently does nothing
  is a finding (MEDIUM — misleading interface).

### Dimension 4: Error Propagation & Fail-Fast (no broken ROM on stage failure)
The cardinal rule: a stage failure must abort before a stale/garbage `.nes` is left where the
user expects a good one. Audit `run_full_pipeline`'s guards:
- The whole body is wrapped in one `try/except Exception` (~line 488) that prints and
  `sys.exit(1)`. Confirm no inner `except` swallows a fatal error and lets the run continue to
  emit a ROM. Specifically: the DPCM-pack block (~line 410) and the ROM-validation block
  (~line 473) both catch broadly and **continue** — verify those are genuinely non-fatal
  (a failed DPCM pack still produces a playable ROM? a validation exception is only a warning?).
- `compile_rom(project_dir, output_rom)` (`compiler/compiler.py:149`) returns a bool;
  `run_full_pipeline` checks `if not compile_rom(...)` and exits. Confirm a CC65 nonzero exit
  surfaces as `False` (cross-check `compiler/cc65_wrapper.py` and `CompilationError` /
  `ToolchainError` in `core/exceptions.py`) — a compile failure reported as success is a HIGH
  floor (`_audit-severity.md`: "CC65 nonzero exit / stderr ignored").
- `prepare_project` (`nes/project_builder.py:74`) returns bool; the inline path exits on
  `False` but `run_prepare` only prints success **inside** the `if builder.prepare_project(...)`
  with no `else` — a failed prepare in the step-by-step path exits 0 silently. Flag.
- ROM validation: `ROMDiagnostics.diagnose_rom` (`debug/rom_diagnostics.py:84`) returns an
  `overall_health` of HEALTHY/GOOD/FAIR/POOR/ERROR. The pipeline only exits on `"ERROR"`;
  POOR/FAIR pass through with a warning. Verify a POOR ROM that crashes on hardware is not
  shipped as success (cross-check against the CRITICAL bad-vector rule).

### Dimension 5: Temp-File / Intermediate Handling
The default path writes intermediates into a `tempfile.TemporaryDirectory(prefix="midi2nes_")`
(`main.py:258`); the step-by-step path writes user-named JSON/asm files.
- Confirm the temp dir is the parent of `music.asm` and `nes_project/`, and that
  `compile_rom(project_path, output_rom)` reads from the temp project and writes the final ROM
  **outside** the temp dir (so it survives `TemporaryDirectory` cleanup). A ROM written inside
  the temp dir would be deleted on context exit — verify `output_rom` is the user path.
- Confirm nothing in the temp path is referenced after the `with` block closes (the success
  banner reads `output_rom.stat()` — that is outside temp, good; verify no other late read).
- Step-by-step intermediates (`parsed.json`, `mapped.json`, etc.) are user-managed and not
  cleaned — confirm no stage overwrites an input it still needs, and that `args.output` of one
  stage is safe to use as `args.input` of the next.
- DPCM packing appends to `music.asm` with `open(music_asm, 'a')` in the default path and
  `open(args.output, 'a')` in `run_export`. Verify append-mode does not double-append on a
  re-run of the step-by-step `export` (the file already containing a DPCM block).

### Dimension 6: Backup & Overwrite Safety
Only `run_full_pipeline` implements backup/restore; the subcommands overwrite freely.
- The backup uses `output_rom.with_suffix('.nes.backup')` (`main.py:245`). Note
  `Path('x.nes').with_suffix('.nes.backup')` yields `x.nes.backup` only if the stem has no
  dot — verify the suffix math on names like `my.song.nes` (does it clobber unexpectedly?).
- Restore-on-failure runs after compile failure (~line 436) and after validation ERROR
  (~line 463) via `shutil.copy2(backup_path, output_rom)`. Confirm restore fires on **every**
  early `sys.exit(1)` after the backup was made — the prepare-failure exit (~line 427) and the
  top-level `except` (~line 488) exit do **not** restore the backup. Flag any failure exit
  that leaves the user's good ROM overwritten/half-written with no restore.
- The backup is never deleted on success → confirm whether `.nes.backup` is intentionally
  left on disk (clutter) or should be cleaned (LOW unless it masks a stale ROM).
- Step-by-step `export`/`prepare`/`frames`/etc. silently overwrite their `output` with no
  backup. Confirm this is acceptable for intermediate files; if `export` can clobber a
  hand-edited `music.asm`, note it.

### Dimension 7: Large-File Threshold & Pattern-Detector Fallback Hand-off
`run_full_pipeline` has a `LARGE_FILE_THRESHOLD = 10000` (`main.py:307`) and a
parallel→sequential fallback (~lines 314-327).
- The threshold only **prints a suggestion** to use `--no-patterns`; it does not change
  behavior. Confirm that is intended (no silent path switch) and that the message is accurate.
- The fallback wraps `ParallelPatternDetector(...).detect_patterns(events)` in `try/except
  Exception` and on failure constructs `EnhancedPatternDetector` and **truncates events to
  2000** (`events = events[:2000]`). This truncation drops note data → the compressed ROM
  represents only the first 2000 events. Per `_audit-severity.md`, data loss that changes the
  song is CRITICAL; verify whether truncation is reachable on common large files and whether
  the user is warned that output is incomplete. The truncation also mutates `events`, which is
  later reused to build `ca65_references` (~line 353) — confirm the reference frame-mapping is
  still correct against the truncated list (positions beyond 2000 hit the `position < len(events)`
  fallback branch ~line 356 and emit `str(position)` as a frame — verify that is valid).
- Confirm the documented fallback (`_audit-common.md`: "graceful fallback to
  `EnhancedPatternDetector`") actually fires — i.e. the `except` catches what
  `ParallelPatternDetector` realistically raises (pickling / worker errors), not only trivial
  exceptions. A parallel crash with no fallback is a HIGH floor.
- `run_detect_patterns` (step-by-step) has **no** fallback and **no** threshold — it always
  uses `EnhancedPatternDetector` on the full event set. Flag the asymmetry (a large file that
  the default path survives via truncation may hang/OOM under the bare subcommand).

### Dimension 8: Song-Bank Path
The `song` subcommands (`run_song_add`/`run_song_list`/`run_song_remove`) operate on a JSON
bank via `nes/song_bank.py` (`SongBank.add_song_from_midi`, `export_bank`, `import_bank`).
- This path is **disjoint** from the main pipeline — confirm a bank is never an input to
  `run_full_pipeline`/`export`/`prepare`, and there is no `song → ROM` route (no
  build/compile method on `SongBank` per the grep). If multi-song ROMs are a roadmap promise
  (`docs/ROADMAP.md`), flag the missing hand-off as a contract gap (doc-rot if docs claim it
  works — LOW/MEDIUM).
- `run_song_add` derives `metadata` from CLI args (`composer`, `loop_point`, `tags`, `tempo`)
  and defaults the bank to `song_bank.json` when `--bank` is omitted; `run_song_list` /
  `run_song_remove` require a positional `bank`. Verify the add-default and the
  list/remove-required asymmetry can't silently write to a different file than the user reads.
- `add_song_from_midi(args.input, ...)` parses MIDI independently of `parser_fast` — confirm
  it does not use a third parser that drifts from the pipeline's note handling.

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
