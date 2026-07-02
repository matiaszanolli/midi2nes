# Pipeline Integrity Audit — 2026-07-01

Scope: end-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) audited as a contract-bound system per
`.claude/commands/audit-pipeline/SKILL.md`, all dimensions. HEAD = `2bcb780`.

**Dedup**: performed against the cached matiaszanolli/midi2nes issue list at
`/tmp/audit/issues.json` (125 issues, open+closed) and all prior reports in `docs/audits/`.
No open or closed issue matches any of the six new findings (PL-01–PL-06); the four
re-confirmed Existing findings map to open issues #120, #112, #33, and #23. Every fix
credited in the "Verified-fixed" section corresponds to a CLOSED issue in the list.

## Summary

The pipeline has absorbed the 2026-06-29 fix wave cleanly: the fast parser is used on both
paths, pattern bounds are shared (`PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`), sampling is
uniform and reported with the true retained count (#100), the no-patterns stats stub uses
the detector schema (#104), backup restore is unified in a `finally` (#26), unknown flags
are rejected (#8), `run_map` guards its `events` key (#110), the ignored `--config` flags
were dropped (#109/#13), and the `compile` subcommand gives the step-by-step path the same
compile + boot-fatal validation gate (#15). `tests/test_main_pipeline.py` +
`tests/test_main.py` pass (96/96) at HEAD.

The remaining live defects are concentrated in **flag routing for global options placed
before a subcommand** and in **messaging/fail-safe residue** around the validation gate.

### Single most dangerous contract break
**PL-01**: `--arranger` is a global argparse option, so `python main.py --arranger map
parsed.json mapped.json` parses cleanly — and is then **silently ignored** by `run_map`,
which always runs the legacy mapper. The user gets a legacy-arranged song (polyphony
dropped) while believing arranger mode was engaged. Live-reproduced at HEAD. This is the
same defect class the #8 fix closed for typo flags on the default path, resurfacing through
the *declared* global flags on the subcommand path (CRITICAL per the ignored-flag /
silent-song-change floor in `.claude/commands/_audit-severity.md`).

### Does the step-by-step path produce the same ROM as the default path?
**Yes, materially.** For the same input, both paths parse with
`tracker/parser_fast.py`, produce the same `frames`, export through
`CA65Exporter.export_tables_with_patterns` with `standalone=False`, pack only
song-referenced DPCM samples (#140), prepare with `MMC3Mapper` behind the same
`check_mapper_capacity` gate, and compile + validate through the same
`compile_rom`/`validate_rom` pair (#15). All emitted bytes derive from `frames`
(`exporter/exporter_ca65.py:862-874`), and the exporter tolerates both int (in-memory) and
str (JSON round-trip) frame keys (`exporter/exporter_ca65.py:965`), so the JSON round-trip
does not reorder frames. Residual, non-ROM-affecting divergence (by design): the pattern
JSON artifacts differ (default path: `ParallelPatternDetector`, exact repeats, sampled to
15000; subcommand: `EnhancedPatternDetector`, variations, sampled to 1000), and the
`references` shape differs (`{}` vs detector-native) — but `references` is never consumed
by the exporter (#4), and `patterns` affects the ROM only via truthiness (serializer
selection). A byte divergence is possible only in the edge case where one detector finds
patterns and the other finds none.

### Findings per dimension
- Dimension 1 (stage JSON contracts): 0 new; 1 Existing re-confirmed (E1: unguarded JSON
  reads in `run_frames`/`run_export`/`run_detect_patterns` — #120 (SAFE-01); the `run_map`
  case is fixed, #110 closed).
- Dimension 2 (full vs step parity): 0 new; 1 Existing re-confirmed (E2: dead top-level
  import of the old full parser, #112 (P-04)).
- Dimension 3 (flag routing): PL-01 (CRITICAL), PL-02 (MEDIUM), PL-06 (LOW).
- Dimension 4 (error propagation / fail-fast): PL-04 (MEDIUM), PL-05 (MEDIUM, shared with Dim 6).
- Dimension 5 (temp/intermediate handling): 0 new; 1 Existing re-confirmed (E4: `run_export`
  DPCM append, #23 — now mitigated by the exporter's truncating write).
- Dimension 6 (backup/overwrite safety): covered by PL-05 (the `compile` subcommand has no
  backup contract at all).
- Dimension 7 (large-file threshold & fallback): PL-03 (MEDIUM).
- Dimension 8 (song bank): 0 new; 1 Existing re-confirmed (E3: old-parser drift, #33).

**Severity totals (new findings this report): CRITICAL 1 · HIGH 0 · MEDIUM 4 · LOW 1 · Total 6**

## Contract Map

| Stage boundary | Producer (fn → key(s)) | Consumer (fn) | Verified |
|---|---|---|:--:|
| parse → map | `parser_fast.parse_midi_to_frames` → `{"events","metadata"}` | `run_map` reads `midi_data["events"]` (guarded, #110) | ✓ |
| map → frames | `assign_tracks_to_nes_channels(events, dpcm_index)` → `{pulse1,pulse2,triangle,noise,dpcm: [...]}` | `NESEmulatorCore.process_all_tracks` | ✓ |
| arrange → frames | `arrange_for_nes(events, arp_speed, verbose)` → `{channel:{frame:{...}}}` | exporter / detector flattening (`int(frame_num)`-tolerant) | ✓ |
| frames → detect | `{channel:{frame:{note,volume,...}}}` | detector event flattening (both entry points identical) | ✓ |
| detect → export | `{patterns, references, stats}` (`variations` dropped by `run_detect_patterns` — consumer never reads it) | `run_export` reads `patterns`/`references`; exporter ignores `references` (#4, documented) | ✓ |
| stats → banner | `original_size`/`compressed_size`/`compression_ratio`/`unique_patterns` (unified, #104; % units, #17) | success banner / subcommand print | ✓ |
| export → prepare | `export_tables_with_patterns(...)` writes music.asm (+DPCM append; builder stubs `dpcm_*_table` if absent) | `NESProjectBuilder.prepare_project` (MMC3; capacity gate on both paths) | ✓ |
| prepare → compile | project dir | `compile_rom` → bool; CC65 nonzero exit → `CompilationError` → `False` (+timeouts, #122) | ✓ |
| compile → validate | `.nes` | `validate_rom` — boot-fatal on bad vectors / zero APU init (#6), shared by both paths (#15) | ✗ silently passes if diagnostics itself raises (PL-04) |
| song add → bank | `SongBank.add_song_from_midi` → `tracker.parser` (old parser) | JSON bank only (disjoint from ROM build, documented) | ✗ third-parser drift (#33, Existing) |

## Findings

### PL-01: Global `--arranger` before a subcommand parses cleanly and is silently ignored — step-by-step users get the legacy arrangement
- **Severity**: CRITICAL
- **Dimension**: 3 — Flag Routing
- **Both paths?**: Step-by-step subcommands only (the default path honors the flag).
- **Location**: `main.py:694` (global declaration), `main.py:839-843` (subcommand dispatch parses the full argv), `main.py:44-58` (`run_map` never reads `args.arranger`)
- **Status**: NEW (sibling of closed #8 / F-03, which fixed *unknown* flags on the default path; this is the *declared* global flags on the subcommand path)
- **Description**: `--arranger`/`-a` is declared on the top-level parser, so argparse accepts
  it in front of any subcommand. No subcommand consumes it: `run_map` unconditionally runs
  `assign_tracks_to_nes_channels` (legacy mode), and there is no `arrange` subcommand at all —
  the arranger front-end is reachable *only* through `run_full_pipeline`. The flag is
  swallowed without any warning or error.
- **Evidence**: Live at HEAD: `python main.py --arranger map missing.json out.json` proceeds
  into `run_map` (fails on the missing input file, not on the flag) — argparse accepted and
  discarded `--arranger`. Contrast: `python main.py --no-pattern x.mid` correctly errors
  `Unknown option` (the #8 fix), and `main.py map --arranger ...` (flag after subcommand)
  correctly errors via argparse.
- **Impact**: A user running the documented step-by-step chain with `--arranger` gets
  legacy single-voice mapping: polyphonic content is pitch-split/dropped instead of
  arpeggiated, so the final ROM plays a different song than requested, with zero
  diagnostics. Per `_audit-severity.md` and the SKILL Dimension 3 floor, an ignored flag
  that silently changes the song is CRITICAL (same rationale that classified F-03/#8).
  Trigger requires putting the global flag on a subcommand invocation; impact when it
  fires is a silently different song.
- **Related**: Closed #8 (F-03); PL-02 (same mechanism, `--debug`); the absence of an
  `arrange` subcommand is the underlying parity gap.
- **Suggested Fix**: Either reject song-affecting global flags when a subcommand is chosen
  (error: "--arranger only applies to the default pipeline; there is no step-by-step
  equivalent"), or honor them (add an `arrange` subcommand / an `--arranger` switch on
  `map`). At minimum, scope the help text.

### PL-02: Global `--debug` is silently inert on `prepare` — step-by-step cannot produce a debug ROM
- **Severity**: MEDIUM
- **Dimension**: 3 — Flag Routing / 2 — Parity
- **Both paths?**: Step-by-step only (default path routes `debug_mode` into the builder).
- **Location**: `main.py:693` (global declaration), `main.py:216-242` (`run_prepare`
  constructs `NESProjectBuilder(args.output, mapper=mapper)` with no `debug_mode`),
  vs `main.py:620,634` (default path passes `debug_mode=debug_mode`)
- **Status**: NEW (explicitly anticipated by SKILL Dimension 3; not reported in the
  2026-06-28/29 audits)
- **Description**: `--debug`/`-d` ("Enable debug overlay in ROM") is a global option, so
  `python main.py --debug prepare music.asm proj/` parses cleanly — and `run_prepare`
  never reads `args.debug`, so the prepared project has no debug overlay. The same class
  of declared-but-ignored flag was cleaned up for `--config` on `map`/`detect-patterns`/
  `song add` (#13/#109) but the `--debug`→`prepare` route was missed. (Global `--verbose`
  is similarly inert on most subcommands, but is cosmetic-only.)
- **Evidence**: Live at HEAD: `python main.py --debug prepare missing.asm proj` reaches
  `run_prepare` (clean `[ERROR] Failed to prepare NES project`) — the flag was accepted;
  `grep args.debug main.py` shows the only consumer is `run_full_pipeline` (line 620).
- **Impact**: Misleading interface: a developer debugging playback via the step-by-step
  chain silently gets a normal ROM without the APU/frame overlay they asked for. No song
  change (the overlay is diagnostic), hence MEDIUM, not CRITICAL.
- **Related**: PL-01 (same mechanism); closed #13/#109 (same defect class).
- **Suggested Fix**: Pass `debug_mode=getattr(args, 'debug', False)` in `run_prepare`'s
  builder construction (one line), or reject `--debug` on subcommands like PL-01.

### PL-03: The fallback's "the ROM is INCOMPLETE" warning is false — event sampling cannot make the ROM incomplete, and the advice it gives makes ROMs bigger
- **Severity**: MEDIUM
- **Dimension**: 7 — Large-File Threshold & Fallback / 2 — messaging parity
- **Both paths?**: Default path only (the `detect-patterns` subcommand's "lossy" wording is
  accurate for its artifact, the pattern JSON).
- **Location**: `main.py:522-530` (`pattern_loss_warning` text), `main.py:661-662`
  ("INCOMPLETE OUTPUT" success-banner line); ground truth `exporter/exporter_ca65.py:862-874`
- **Status**: NEW (the numeric inaccuracy of this warning was PATTERNS P-01 → fixed by
  #100; the *factual* claim of ROM incompleteness was not previously reported)
- **Description**: When the sequential fallback samples events down to
  `DETECTOR_MAX_EVENTS` (1000), the pipeline prints and re-prints at success:
  "the ROM is INCOMPLETE. Re-run with --no-patterns for full fidelity." But sampled
  `events` feed *only* pattern detection, whose output affects the ROM solely via
  `patterns` truthiness (serializer selection) — every emitted byte derives from the full
  `frames` dict (`export_tables_with_patterns` docstring, #4; confirmed in the macro path
  which iterates `range(max_frame + 1)` over `frames`). The ROM contains the whole song
  either way. The message is also inconsistent with the parallel path, which samples to
  15000 (`tracker/pattern_detector_parallel.py:47-51`) printing only an inline "lossy"
  note and *no* INCOMPLETE banner — two sampling events of the same kind get opposite
  messaging.
- **Evidence**: `main.py:525-528` (warning text) vs `exporter/exporter_ca65.py:873-874`
  (`if not patterns: return self.export_direct_frames(...)` — the only read of pattern
  data) and `:964-965` (frame loop over `frames`, not `events`).
- **Impact**: Users with large files hitting the fallback are told their ROM is broken when
  it is not, and are directed to `--no-patterns` — which switches to the direct-frame
  serializer, typically producing a much larger ROM (and closer to the MMC3 capacity gate)
  for zero fidelity gain. Misleading-messaging class (`_audit-severity.md`: inaccurate
  reported stats → MEDIUM). Only the compression *metrics* are affected by sampling.
- **Related**: Closed #10 (introduced the warning), #100 (fixed its numbers), #4
  (references are analysis-only — the fact that makes the claim false); PATTERNS P-01.
- **Suggested Fix**: Reword both messages to what is true: "pattern *analysis* was sampled
  (N→M events); compression stats are approximate; ROM content is unaffected." Drop the
  `--no-patterns` advice, and align the parallel path's sampling message with the
  fallback's.

### PL-04: `validate_rom` silently passes when the diagnostics engine itself fails — and says nothing without `--verbose`
- **Severity**: MEDIUM
- **Dimension**: 4 — Error Propagation & Fail-Fast
- **Both paths?**: Both (shared gate: `run_full_pipeline` step 8 and the `compile` subcommand).
- **Location**: `main.py:157-163`
- **Status**: NEW
- **Description**: The post-build gate wraps `from debug.rom_diagnostics import
  ROMDiagnostics` + `diagnose_rom(...)` in `except Exception:` and returns **True**
  (ROM accepted), printing a warning only `if verbose`. `diagnose_rom` handles unreadable
  ROMs internally (`_create_error_result` → `"ERROR"` → fatal), so this outer except fires
  on genuine infrastructure failures (import error in the `debug` package, an unexpected
  bug in diagnostics) — exactly the cases where the boot-fatal vector/APU gate (#6)
  silently stops existing. In a default (non-verbose) run there is zero indication that
  validation was skipped.
- **Evidence**: `main.py:157-163` — `except Exception as e: if verbose: print(...);
  return True`. The docstring itself flags it: "treated as non-blocking, matching prior
  behavior."
- **Impact**: Defense-in-depth gap on the one gate that keeps unbootable ROMs (bad
  $FFFA-$FFFF vectors, missing APU init — the CRITICAL class of `_audit-severity.md`) from
  shipping as `✅ SUCCESS`. Requires a second failure (broken diagnostics) to bite, hence
  MEDIUM rather than HIGH, but the swallow is fully silent by default.
- **Related**: Closed #6 (the gate this bypasses), #15 (gate shared with `compile`);
  open #130 (TD-02, duplicate validators).
- **Suggested Fix**: Always print the "ROM validation could not run: {e} — ROM NOT
  validated" warning (not just under verbose); consider exiting nonzero unless
  `--skip-validation` was passed, since the user explicitly has that escape hatch.

### PL-05: A validation-failed (unbootable) ROM is left at the output path — always for the `compile` subcommand, and on the default path whenever no backup existed
- **Severity**: MEDIUM
- **Dimension**: 4 — Fail-Fast / 6 — Backup & Overwrite Safety
- **Both paths?**: Both, asymmetrically (default path is protected only when the output
  pre-existed; `compile` is never protected).
- **Location**: `main.py:191-213` (`run_compile`: no backup, no cleanup on validation
  failure), `main.py:679-683` (`finally` restore is a no-op when `backup_path is None`),
  `compiler/compiler.py:144` (ROM copied to the output path before validation runs)
- **Status**: NEW (closed #26 unified restore for *existing* backups; the no-backup residue
  and the `compile` subcommand's missing backup contract were not previously reported)
- **Description**: `compile_rom` copies the linked ROM to the user's output path, then
  `validate_rom` runs. If validation reports a boot-fatal defect, both callers
  `sys.exit(1)` — but the freshly-written unbootable `.nes` stays at the output path.
  On the default path the `finally` restore repairs this only if the output existed before
  the run (backup taken at `main.py:432-437`); a first-time build leaves the bad ROM behind.
  `run_compile` never creates a backup at all, so it both (a) overwrites a pre-existing good
  ROM with no restore path (a parity break with the default path's backup contract, SKILL
  Dimension 6) and (b) always leaves the failed ROM on disk.
- **Evidence**: `run_compile` body (`main.py:197-213`) contains no `backup`/`unlink`
  logic; `_restore_backup` (`main.py:140-145`) is a no-op for `backup_path=None`.
- **Impact**: The cardinal fail-fast rule ("no broken `.nes` left where the user expects a
  good one") is violated in the artifact sense: the failure *is* loudly reported with a
  nonzero exit, but a known-unbootable ROM persists at the destination — a later `ls`-and-
  flash, or any workflow ignoring exit codes, ships it. Workaround exists (heed the error)
  → MEDIUM.
- **Related**: Closed #26 (restore unification), #15 (`compile` subcommand); PL-04.
- **Suggested Fix**: On validation failure with no backup, rename the bad ROM to
  `<name>.nes.failed` (or delete it) before exiting; give `run_compile` the same
  backup-create/restore/cleanup contract as the default path (factor the default path's
  backup block into a helper both use).

### PL-06: `--version` combined with other arguments is swallowed and a full build runs instead
- **Severity**: LOW
- **Dimension**: 3 — Flag Routing
- **Both paths?**: Default path only.
- **Location**: `main.py:828-830` (bare `--version` special case), `main.py:864-866`
  (manual loop collects `--version` into `global_args`), `main.py:896-905` (`SimpleArgs`
  never reads it)
- **Status**: NEW
- **Description**: `python main.py --version` alone prints the version (special-cased at
  argv length 2). But `python main.py --version song.mid` takes the manual default-path
  loop, which files `--version` into `global_args` where nothing consumes it — the full
  pipeline runs (parse → … → compile), overwriting/creating `song.nes`, and the version is
  never printed. An argparse-handled flag would have printed-and-exited regardless of
  other args.
- **Evidence**: Live at HEAD: `python main.py --version missing.mid` prints
  `[ERROR] Input MIDI file not found` — the pipeline path was reached; no version output.
- **Impact**: Surprising side effect (an unrequested build, possibly minutes of CC65 work
  and an output-file overwrite — mitigated by the backup contract) for a
  query-only flag. Low realism, no data corruption → LOW.
- **Related**: PL-01/PL-02 (manual-dispatch flag handling).
- **Suggested Fix**: In the manual loop, treat `--version` like argparse does: print
  `MIDI2NES {__version__}` and `sys.exit(0)` immediately.

## Existing (open) — re-confirmed at HEAD, not re-filed

### E1: Unguarded JSON loads / key access in `run_frames`, `run_export`, `run_detect_patterns`
- **Severity**: MEDIUM — **Status**: Existing: #120 (OPEN — SAFE-01); the `run_map` member
  of the set was fixed by #110 (closed).
- **Location**: `main.py:61` (`run_frames`), `main.py:246,251` + `main.py:262-263`
  (`run_export`, incl. bare `pattern_data['patterns']`/`['references']`), `main.py:305`
  (`run_detect_patterns`).
- **Note**: Live-reproduced this audit — a missing input file raises a raw
  `FileNotFoundError` traceback from `run_map`'s siblings (see PL-01 evidence run).

### E2: Dead top-level import of the old full parser
- **Severity**: LOW — **Status**: Existing: #112 (OPEN — P-04).
- **Location**: `main.py:16` — still present at HEAD despite the `2bcb780` dead-code
  sweep; all live paths import `parser_fast` locally (`main.py:39`, `main.py:455`).

### E3: `SongBank.add_song_from_midi` parses with the old full parser (third-parser drift)
- **Severity**: LOW — **Status**: Existing: #33 (OPEN — F-14).
- **Location**: `nes/song_bank.py:7` (`from tracker.parser import parse_midi_to_frames`).
  Song-bank remains ROM-disjoint (help text now documents this), so impact stays latent.

### E4: `run_export` appends the DPCM block with `open(args.output, 'a')`
- **Severity**: MEDIUM→LOW residual — **Status**: Existing: #23 (OPEN — F-10).
- **Location**: `main.py:297`. Mitigation confirmed at HEAD: `export_tables_with_patterns`
  writes the output with mode `'w'` (`exporter/exporter_ca65.py:801,1183`), so a re-run
  truncates before appending — no doubling on plain re-runs; the residual risk is limited
  to appending after a hand-edited file within one run sequence.

## Verified-fixed since 2026-06-29 (spot-checked, no regression)
- #110 — `run_map` guards missing `events` key (`main.py:50-52`).
- #109/#13 — silently-ignored `--config` flags removed from `map`/`detect-patterns`/`song add`
  (declaration sites now carry explanatory comments).
- #100/#21 — uniform sampling to `DETECTOR_MAX_EVENTS` with accurate retained-count warnings
  at both entry points (`main.py:330-334`, `main.py:522-530`).
- #104/#17 — `--no-patterns` stub stats use the detector schema; ratio printed as `%
  reduction` on both paths (`main.py:541-550`, `main.py:659`, `main.py:347`).
- #26/#25 — single `finally` restore point; backup deleted on success (`main.py:667-683`).
- #15 — `compile` subcommand shares `compile_rom` + `validate_rom` with the default path.
- #6 — boot-fatal validation gate (invalid vectors / zero APU init → fail + restore).
- #122 — CC65 subprocess timeouts; nonzero exit → `CompilationError` → `False` → nonzero exit.
- #46/#103 — parallel detector deterministic tie-break and shared `score_pattern`.
- #140 — both DPCM pack call sites filter to song-referenced samples; empty set packs nothing.

## Suggested next step

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-07-01.md
```
