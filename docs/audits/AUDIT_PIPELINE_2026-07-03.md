# Pipeline Integrity Audit — 2026-07-03

Scope: end-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) audited as a contract-bound system per
`.claude/commands/audit-pipeline/SKILL.md`, all dimensions. HEAD = `9cfa0e2`.

This is a re-audit of `docs/audits/AUDIT_PIPELINE_2026-07-01.md` after three commits touched
`main.py` / `nes/song_bank.py` / `nes/project_builder.py` since that report: `e71341b`/`9571074`
(PL-01/PL-02 fixes), `0a6f863` (#120/#123), `d8f6a0e` (#33/#34), and `ce4f829` (#37/#38, outside
`main.py` but relevant to Dimension 4).

**Dedup**: fetched the live issue list (`gh issue list --repo matiaszanolli/midi2nes --state all
--limit 300`, 147 issues) to `/tmp/audit/issues_all.json`, and read every prior
`docs/audits/AUDIT_PIPELINE_*.md` report. Every candidate below was checked against an existing
issue number before being written up.

## Summary

**Zero new findings.** All six findings from the 2026-07-01 report were re-verified against the
current code:

- **PL-01** and **PL-02** (both CRITICAL/MEDIUM) are **fixed and confirmed** — no regression.
- **PL-03, PL-04, PL-05, PL-06** are **still open**, live-reproduced or re-read line-for-line at
  HEAD with no code change since 07-01. They remain filed as #176, #177, #178, #179.
- One incidental discovery: issue **#112** (P-04, dead top-level `tracker.parser` import in
  `main.py`) is **already fixed in code** (removed as a side effect of commit `d8f6a0e`, filed
  under #33/#34) but the GitHub issue is still open — a dedup/issue-hygiene gap, not a code
  defect. Flagged in "Verified-fixed" below with a recommendation to close #112.
- `tests/test_main.py` + `tests/test_main_pipeline.py` pass (108/108) at HEAD.

### Single most dangerous open item
**PL-03** remains the most user-facing issue still open: the sequential-fallback banner tells
users their ROM is "INCOMPLETE" and to re-run with `--no-patterns`, which is factually false
(every byte still comes from `frames`) and actively bad advice (produces a larger ROM for zero
fidelity gain). No CRITICAL/HIGH-severity contract breaks are open in this dimension at HEAD —
the two CRITICAL/HIGH-adjacent items from the 07-01 pass (PL-01, and the underlying `--arranger`
silent-ignore class) are fixed.

### Does the step-by-step path produce the same ROM as the default path?
**Yes, materially — unchanged from 07-01.** Both paths parse with `tracker/parser_fast.py`,
produce the same `frames` shape, export through `CA65Exporter.export_tables_with_patterns` with
`standalone=False`, pack only song-referenced DPCM samples (#140), prepare with `MMC3Mapper`
behind the same `check_mapper_capacity` gate, and compile + validate through the same
`compile_rom`/`validate_rom` pair (#15). No commit since 07-01 touched any of these shared code
paths in a way that changes this answer.

### Findings per dimension
- Dimension 1 (stage JSON contracts): 0 new. E1 (#120, unguarded JSON in
  `run_frames`/`run_export`/`run_detect_patterns`) is now **fixed** (see Verified-fixed) — it was
  still open at the time of the 07-01 report but closed by `0a6f863` before that report's commit
  landed in history order; re-confirmed closed here.
- Dimension 2 (full vs step parity): 0 new. E2 (#112, dead parser import) verified **fixed in
  code**, issue still open (hygiene gap, not a defect).
- Dimension 3 (flag routing): PL-01, PL-02 verified **fixed**. PL-06 (LOW) re-confirmed open,
  live-reproduced.
- Dimension 4 (error propagation / fail-fast): PL-04 (MEDIUM) re-confirmed open. New code path
  checked (commit `ce4f829`'s `ExportError` on missing `audio_engine.asm` in `prepare_project`)
  — correctly propagates through both `run_prepare`'s explicit try/except and
  `run_full_pipeline`'s outer try/except/finally; no gap introduced.
- Dimension 5 (temp/intermediate handling): 0 new; unchanged.
- Dimension 6 (backup/overwrite safety): PL-05 (MEDIUM) re-confirmed open — `run_compile` still
  has no backup contract.
- Dimension 7 (large-file threshold & fallback): PL-03 (MEDIUM) re-confirmed open,
  line-for-line unchanged since 07-01.
- Dimension 8 (song bank): 0 new. E3 (#33, old-parser drift) confirmed **fixed**
  (`nes/song_bank.py:11` now imports `parser_fast`); E4 (#23, DPCM append-mode) re-confirmed open
  at `main.py:339`, still mitigated by the exporter's truncating `'w'`-mode write.

**Severity totals (this report): CRITICAL 0 · HIGH 0 · MEDIUM 3 · LOW 1 · Total 4 (all Existing,
0 NEW)**

(PL-03 MEDIUM, PL-04 MEDIUM, PL-05 MEDIUM, PL-06 LOW — all previously filed as #176/#177/#178/#179.)

## Contract Map

| Stage boundary | Producer (fn → key(s)) | Consumer (fn) | Verified |
|---|---|---|:--:|
| parse → map | `parser_fast.parse_midi_to_frames` → `{"events","metadata"}` | `run_map` reads `midi_data["events"]` via `load_json_stage` guard | ✓ |
| map → frames | `assign_tracks_to_nes_channels(events, dpcm_index)` → `{pulse1,pulse2,triangle,noise,dpcm: [...]}` | `NESEmulatorCore.process_all_tracks` iterates `nes_tracks.items()` | ✓ |
| arrange → frames | `arrange_for_nes(events, arp_speed, verbose)` → `{channel:{frame:{...}}}` | exporter / detector flattening (`int(frame_num)`-tolerant) | ✓ |
| frames → detect | `{channel:{frame:{note,volume,...}}}` | detector event flattening (both entry points identical) | ✓ |
| detect → export | `{patterns, references, stats}` (`variations` dropped by `run_detect_patterns`) | `run_export` reads `patterns`/`references` via guard; exporter ignores `references` (#4, documented) | ✓ |
| stats → banner | `original_size`/`compressed_size`/`compression_ratio`/`unique_patterns` | success banner / subcommand print | ✓ |
| export → prepare | `export_tables_with_patterns(...)` writes music.asm (+DPCM append) | `NESProjectBuilder.prepare_project` (MMC3; capacity gate + `ExportError` on missing engine, #37) | ✓ |
| prepare → compile | project dir | `compile_rom` → bool; CC65 nonzero exit → `CompilationError` → `False` (+timeouts, #122) | ✓ |
| compile → validate | `.nes` | `validate_rom` — boot-fatal on bad vectors / zero APU init (#6), shared by both paths (#15) | ✗ silently passes if diagnostics itself raises (PL-04, open) |
| song add → bank | `SongBank.add_song_from_midi` → `tracker.parser_fast` (fixed, #33) | JSON bank only (disjoint from ROM build, documented) | ✓ |

## Findings

All four are **Existing** — re-verified against the current code, no textual or behavioral
change since the 2026-07-01 report. Full descriptions/evidence/suggested fixes are unchanged and
preserved in `docs/audits/AUDIT_PIPELINE_2026-07-01.md`; this entry records the re-verification
performed today.

### PL-03 (re-confirmed): The fallback's "the ROM is INCOMPLETE" warning is false
- **Severity**: MEDIUM
- **Dimension**: 7 — Large-File Threshold & Fallback
- **Both paths?**: Default path only.
- **Location**: `main.py:571-579` (fallback warning text, unchanged line-for-line since 07-01),
  `main.py:723-724` (success-banner "INCOMPLETE OUTPUT" reprint); ground truth
  `exporter/exporter_ca65.py:873-875` (`patterns` truthiness only selects the serializer; every
  byte comes from `frames`).
- **Status**: Existing: #176
- **Re-verification**: Read `main.py:557-580` at HEAD — text is byte-for-byte identical to the
  07-01 report's citation. Cross-checked the parallel detector's own sampling message
  (`tracker/pattern_detector_parallel.py:44-51`, still an inline "lossy" note with no
  "INCOMPLETE" framing) — the two-sampling-events-different-messaging inconsistency also stands.
- **Impact/Suggested Fix**: unchanged from #176 — reword both messages to state that only
  pattern-*analysis* was sampled and the ROM content is unaffected; drop the `--no-patterns`
  advice.

### PL-04 (re-confirmed): `validate_rom` silently passes when the diagnostics engine itself fails
- **Severity**: MEDIUM
- **Dimension**: 4 — Error Propagation & Fail-Fast
- **Both paths?**: Both (`run_full_pipeline` and `compile` subcommand share `validate_rom`).
- **Location**: `main.py:183-189` (`except Exception as e: ... return True`), unchanged since
  07-01.
- **Status**: Existing: #177
- **Re-verification**: Read `main.py:174-214` at HEAD — the `try/except Exception: return True`
  guard around `ROMDiagnostics(...).diagnose_rom(...)` is present verbatim. Also checked that no
  recent commit (`ce4f829`, `0a6f863`, `d8f6a0e`) touched this function — confirmed none did.
- **Impact/Suggested Fix**: unchanged from #177 — always print the "ROM NOT validated" warning
  (not gated on `--verbose`); consider a nonzero exit unless `--skip-validation` was explicit.

### PL-05 (re-confirmed): A validation-failed ROM can be left at the output path
- **Severity**: MEDIUM
- **Dimension**: 4 — Fail-Fast / 6 — Backup & Overwrite Safety
- **Both paths?**: Both, asymmetrically.
- **Location**: `main.py:217-239` (`run_compile` — still no backup/cleanup logic at all),
  `main.py:743-747` (`finally` restore is a no-op when `backup_path is None`, unchanged).
- **Status**: Existing: #178
- **Re-verification**: Live-reproduced: `python main.py compile <bad-project-dir>
  /tmp/audit/pipeline_test/out.nes` exits 1 on the missing-project-dir precondition; read through
  `run_compile`'s body confirming no `backup_path`/`shutil.copy2`/`unlink` calls exist anywhere in
  the function (grep for `backup` in `main.py:217-239` returns nothing). `_restore_backup`
  (`main.py:166-171`) is unchanged and still a no-op for `backup_path=None`.
- **Impact/Suggested Fix**: unchanged from #178 — give `run_compile` the same
  backup-create/restore/cleanup contract as `run_full_pipeline` (factor into a shared helper).

### PL-06 (re-confirmed): `--version` combined with other arguments is swallowed
- **Severity**: LOW
- **Dimension**: 3 — Flag Routing
- **Both paths?**: Default path only.
- **Location**: `main.py:892-894` (bare `--version` special case), `main.py:939-941` (manual loop
  collects `--version` into `global_args`), `main.py:971-980` (`SimpleArgs` never reads it).
- **Status**: Existing: #179
- **Re-verification**: Live-reproduced at HEAD:
  ```
  $ python main.py --version nonexistent.mid
  [ERROR] Input MIDI file not found: nonexistent.mid
  ```
  No version string is printed; the pipeline path is reached and fails on the (expected) missing
  file, exactly as in the 07-01 report's reproduction.
- **Impact/Suggested Fix**: unchanged from #179 — in the manual loop, treat `--version` like
  argparse's `action='version'`: print and `sys.exit(0)` immediately, before checking for a
  positional input.

## Existing (open) — re-confirmed at HEAD, not re-filed

### E4: `run_export` appends the DPCM block with `open(args.output, 'a')`
- **Severity**: LOW (residual; mitigated) — **Status**: Existing: #23 (F-10)
- **Location**: `main.py:339`. `export_tables_with_patterns` still writes the primary output in
  `'w'` mode first (`exporter/exporter_ca65.py:805,1196`), so a plain re-run of `export` does not
  double the DPCM block. Residual risk limited to appending after a hand-edited `music.asm`
  within one run sequence — unchanged from 07-01.

## Verified-fixed since 2026-07-01

- **PL-01 (#174)** — `--arranger` before a subcommand now hard-errors instead of being silently
  ignored: `main.py:903-914` rejects it with `sys.exit(2)` and a clear message pointing the user
  at `midi2nes --arranger song.mid`. Confirmed by reading the code; matches commit `e71341b`.
- **PL-02 (#175)** — `run_prepare` now passes `debug_mode=getattr(args, 'debug', False)` into
  `NESProjectBuilder` (`main.py:252`), matching the default path's `debug_mode` derivation
  (`main.py:682`). Confirmed by reading the code; matches commit `9571074`.
- **E1 (#120, SAFE-01)** — `run_frames`, `run_export`, and `run_detect_patterns` (not just
  `run_map`) now all route their JSON reads through `load_json_stage` (`main.py:36-65`, applied
  at `main.py:87`, `main.py:276`, `main.py:284`, `main.py:354`). A missing/corrupt/wrong-stage
  file now produces a clean `[ERROR]` and exit 1 instead of a raw traceback on every step-by-step
  subcommand, not just `map`. Matches commit `0a6f863`.
- **E2 (#112, P-04)** — code-level fix confirmed: `grep -n "from tracker.parser import" main.py`
  returns nothing at HEAD; the dead top-level import of the old full parser is gone. `git log -S`
  shows it was removed by `d8f6a0e` (filed under #33/#34, song-bank parser fix) as a side effect,
  not tracked against #112 directly. **Recommend closing #112** — the code defect no longer
  exists, only the issue-tracker bookkeeping is stale.
- **E3 (#33, F-14)** — `nes/song_bank.py:11` now imports `parse_midi_to_frames` from
  `tracker.parser_fast`, not the old full parser. Confirmed by reading the file; matches commit
  `d8f6a0e`.

## New code path checked, no gap found

`ce4f829` ("fail fast on missing audio engine", #37/#38) added a new `ExportError` raise inside
`NESProjectBuilder.prepare_project` (`nes/project_builder.py`) when bytecode mode is selected and
`nes/audio_engine.asm` is missing. Checked both call sites for correct propagation:
- `run_prepare` (`main.py:256-260`) wraps the call in `try/except Exception`, printing
  `[ERROR] Failed to prepare NES project: {e}` and exiting 1 — `ExportError` is an
  `Exception` subclass (`core/exceptions.py:79`, via `MIDI2NESError`), so this is caught cleanly.
- `run_full_pipeline` (`main.py:698-700`) calls `builder.prepare_project(...)` unwrapped at that
  call site, but the entire function body is inside one outer `try` (`main.py:501`) /
  `except Exception` (`main.py:735`) / `finally` (`main.py:743`), so the raised `ExportError`
  is caught, printed as `[ERROR] Pipeline failed: ...`, and the `finally` block still runs
  `_restore_backup`. No new fail-fast gap introduced.

## Suggested next step

The four open findings (PL-03/#176, PL-04/#177, PL-05/#178, PL-06/#179) are already filed and
require no new issues. Recommended housekeeping: close #112 (P-04) as fixed-by-#33/#34's commit.

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-07-03.md
```
