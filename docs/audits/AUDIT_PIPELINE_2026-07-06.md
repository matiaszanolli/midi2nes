# Pipeline Integrity Audit — 2026-07-06 (re-audit / verify-the-fix pass)

Scope: end-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) audited as a contract-bound system per
`.claude/commands/audit-pipeline/SKILL.md`, all 8 dimensions. HEAD = `8308a63`
(master; tip after PR #294 "sync audit skills to current code" and PR #293
"config-missing-path guard + arranger pulse-volume floor").

**Dedup**: `/tmp/audit/issues.json` (29 issues, `gh issue list ... --limit 200`) plus
every prior `docs/audits/AUDIT_PIPELINE_*.md` — most recently
`AUDIT_PIPELINE_2026-07-05.md`, whose one NEW finding (PL-09, HIGH) and one open
MEDIUM (PL-07/#267) are both **re-verified fixed** below. This pass focuses on
confirming the two fixes that landed since the 07-05 pass (`resolve_mapper`'s
direct-export packed-mapper guard for PL-09/#285/#283, and `get_pattern_detection_caps`'s
missing-config-path guard for PL-07/#267) and re-checking every previously-verified fix
for regression.

## Summary

**Zero NEW findings. Zero CRITICAL / HIGH / MEDIUM.** One pre-existing open item
(PL-08/#269, LOW) remains, unchanged. Two items that were live in the 07-05 pass —
PL-09 (HIGH) and PL-07 (MEDIUM) — are both **verified fixed** at HEAD and live-reproduced
as no longer defective. PL-03..PL-06 stay fixed. All 8 dimensions pass.

Finding counts per dimension:
- Dimension 1 (Stage JSON/artifact contract): 0 new. PL-09 (was ✗) now ✓.
- Dimension 2 (`run_full_pipeline` vs step-by-step parity): 0 new. PL-08/#269 (LOW) open.
- Dimension 3 (flag routing): 0 new. `--config`/`--mapper` whitelist in sync with argparse.
- Dimension 4 (error propagation / fail-fast): 0 new.
- Dimension 5 (temp-file / intermediates): 0 new.
- Dimension 6 (backup & overwrite): 0 new.
- Dimension 7 (large-file threshold / detector fallback): 0 new.
- Dimension 8 (song-bank path): 0 new (known roadmap gap only, F-13/#30).

`tests/test_main.py` + `tests/test_main_pipeline.py`: **167/167 pass** at HEAD.

### Single most dangerous open item
**PL-08/#269 (LOW, Existing, unchanged)** — `compile --mapper` still has no `auto`
choice, so a `prepare --mapper auto` project (which can resolve to MMC1 and bank-pack)
has no matching `compile` invocation; the user must know to pass `--mapper mmc1`
explicitly. This is the mildest surviving symptom of the "`export`/`prepare`/`compile`
`--mapper` are three independently-parsed flags with no shared source of truth outside
the default pipeline" fact — but the dangerous half of that fact (PL-09, a false "✓ fits"
that deferred to a raw `ld65` error) is now closed (see below). No CRITICAL, HIGH, or
MEDIUM pipeline-contract item is open.

### Does the step-by-step path produce the same ROM as the default path?
**Yes, for every documented/shipped workflow.** Both paths parse with `parser_fast`,
produce identical `frames`, export through `export_tables_with_patterns`, pack only
song-referenced DPCM, and compile+validate through the same `compile_rom`/`validate_rom`
pair. The only way to get a *different* result via the subcommands — passing a
`--mapper` to `export`/`prepare`/`compile` that mismatches the mapper `music.asm` was
bank-packed for — is now caught with a clean pre-flight `ValueError` in `resolve_mapper`
(PL-09 fix, live-reproduced) instead of a raw linker error. The residual `auto`-choice
asymmetry (PL-08/#269) is loud (argparse rejects `--mapper auto` on `compile` up front),
not silent.

## Contract Map

| Stage boundary | Producer (fn → key(s)) | Consumer (fn) | Verified |
|---|---|---|:--:|
| parse → map | `parser_fast.parse_midi_to_frames` → `{"events",...}` | `run_map` reads `["events"]` via `load_json_stage` guard (`main.py:105`) | ✓ |
| map → frames | `assign_tracks_to_nes_channels(events, dpcm_index)` → per-channel dict | `NESEmulatorCore.process_all_tracks` | ✓ |
| arrange → frames | `arrange_for_nes(events, arp_speed, verbose)` → `{channel:{frame:{...}}}` | exporter / detector flatten via shared `frames_to_events` | ✓ |
| frames → detect | `{channel:{frame:{note,volume,...}}}` | `frames_to_events` (both entry points identical) | ✓ |
| detect → export | `{patterns, references, stats}` (`run_detect_patterns` writes 3 keys; `variations` dropped) | `run_export` reads only `patterns`/`references` (`main.py:522-523`) — `variations`/`stats` never read; drop is safe | ✓ |
| stats → banner | `compression_ratio`/`coverage_ratio`/`total_events`/… (identical both detectors + `--no-patterns` stub, `main.py:868-876`) | success banner + subcommand print | ✓ |
| **export → prepare (mapper choice)** | direct-export `music.asm` bank-packed for a mapper stamps `; Direct export bank-packed for <name>` (`exporter_ca65.py:206-207`) | `resolve_mapper` reads the marker via `_direct_export_packed_mapper_name` (`main.py:192-260`) and raises `ValueError` on a mismatched later `--mapper` | ✓ **PL-09 fixed** |
| export → prepare (bytecode) | MMC3 macro-bytecode `music.asm` marker comment | `resolve_mapper`'s `_requires_mmc3_bytecode_engine` forces/validates MMC3 (`main.py:231,246-251`) | ✓ |
| prepare → compile | project dir + selected mapper | `compile_rom(...,mapper=)` exact PRG-size check; CC65 nonzero → `CompilationError` → `False` → `sys.exit(1)` | ✓ / PL-08 (mapper not recoverable from dir) |
| compile → validate | `.nes` | `validate_rom` — boot-fatal on bad vectors / zero APU init; diagnostics-engine failure → `False` (`main.py:383-385`) | ✓ |
| `--config` → caps | CLI path → `get_pattern_detection_caps` → `ConfigManager` | sampling caps; **missing path now errors + exit 1** (`main.py:51-58`) | ✓ **PL-07 fixed** |

## Findings

No NEW findings this pass.

### PL-08: `compile --mapper` has no `auto`, so a `prepare --mapper auto` project has no matching compile invocation
- **Severity**: LOW
- **Dimension**: 2 (`run_full_pipeline` vs Step-by-Step Parity)
- **Both paths?**: Step-by-step only (the default `run_full_pipeline` resolves one mapper
  object once and threads it through prepare + compile).
- **Location**: `main.py:1165` (`p_compile.add_argument('--mapper', choices=['nrom','mmc1','mmc3'], default='mmc3', ...)` — no `'auto'`).
- **Status**: Existing: #269 (OPEN, unchanged since 07-05).
- **Description**: `prepare --mapper` accepts `auto` (`main.py:1155`) and can resolve to
  MMC1 (bank-packed) or another mapper by size, but `compile --mapper` offers only
  `nrom`/`mmc1`/`mmc3`. A user who prepares with `auto` has no `auto` to pass to `compile`
  and must know the concrete mapper `auto` actually chose. Loud (argparse rejects
  `--mapper auto` on `compile`), never silent.
- **Evidence**: Re-confirmed at HEAD — `choices=['nrom', 'mmc1', 'mmc3']` on the `compile`
  subparser, vs `choices=['auto', 'nrom', 'mmc1', 'mmc3']` on `prepare`/`export`.
- **Impact**: Minor UX friction on the `prepare --mapper auto` → `compile` step-by-step
  path only. No ROM correctness impact.
- **Related**: PL-09/#285 (now fixed — the dangerous sibling of the same root fact);
  #217/MAP-6 (added the `--mapper` flag family).
- **Suggested Fix**: Add `'auto'` to `compile --mapper` choices and route it through
  `resolve_mapper` (which already reads the project's `music.asm` markers and can recover
  the packed/bytecode mapper), so `auto` on `compile` re-derives the same choice `prepare`
  made.

## Verified-fixed since the previous pass (`78cf319` → `8308a63`)

- **PL-09 (#285 / #283, was HIGH-NEW at 07-05)** — **fixed.** The direct-export path now
  stamps `music.asm` with `; Direct export bank-packed for <mapper.name>`
  (`exporter/exporter_ca65.py:206-207`, emitted whenever `mapper.direct_export_bank_size()`
  is not `None`). `resolve_mapper` (`main.py:218-260`) reads it back via
  `_direct_export_packed_mapper_name` (`main.py:192-215`) — the direct-export mirror of
  `_requires_mmc3_bytecode_engine` — and, for `auto`, honors the packed mapper; for an
  explicit mismatched `--mapper`, raises a clear `ValueError` before `check_mapper_capacity`
  or `ld65` are ever reached. Both `run_prepare` (`main.py:471`) and `run_compile`
  (`main.py:438`) call `resolve_mapper` with the project's `music.asm`, so the guard fires
  on both step-by-step entry points.
  **Live-reproduced fixed**:
  ```
  $ python main.py export sf.json m.asm --mapper mmc1        # exit 0
  $ grep -n "Direct export bank-packed" m.asm
  3:; Direct export bank-packed for MMC1
  $ python main.py prepare m.asm proj                        # default --mapper mmc3
  [ERROR] this music.asm's frame tables were bank-packed for MMC1 at export time
  (RODATA_BANK_NN segments only MMC1's linker config defines), but --mapper mmc3 was
  selected here -- re-export with --mapper mmc3 or run prepare/compile with --mapper mmc1.
  $ python main.py prepare m.asm proj2 --mapper mmc1          # clean success
  ```
  The old false "✓ Music data N bytes fits the MMC3 PRG regions" followed by a raw
  `ld65: Missing memory area assignment for segment 'RODATA_BANK_00'` is gone.

- **PL-07 (#267, was MEDIUM-OPEN)** — **fixed** by commit `f4a1f54`.
  `get_pattern_detection_caps` (`main.py:50-58`) now wraps `ConfigManager(config_path)` in
  a `try/except ConfigurationError` that prints `[ERROR]` and `sys.exit(1)` instead of
  silently reverting to defaults. **Live-reproduced fixed**:
  `python main.py config validate /tmp/does_not_exist_xyz.yaml` now prints
  `[ERROR] Configuration validation failed: Configuration file not found: ...` and exits 1
  (previously printed `[OK] ... is valid`).

- **PL-03 (#176)**: fallback/success-banner warning still reads "for compression analysis
  only — ROM content is unaffected" (`main.py:846-851`, `main.py:1046-1049`). No regression.
- **PL-04 (#177)**: `validate_rom` (`main.py:380-385`) still `return False`s (not `True`)
  on a diagnostics-engine exception, and always prints the warning. No regression.
- **PL-05 (#178)**: `run_compile` (`main.py:443-462`) still backs up / restores via
  `_backup_existing_rom`/`_restore_backup`, moving a first-build failure's unbootable ROM
  to `<name>.nes.failed`. No regression.
- **PL-06 (#179)**: the manual dispatch loop (`main.py:1278-1284`) still handles `--version`
  with an immediate `print` + `sys.exit(0)`. No regression.

## Dimension notes (verify-the-fix confirmations, no findings)

- **Dim 1**: `run_detect_patterns` (`main.py:645-649`) still saves only
  `{patterns, references, stats}` and drops `variations`. Confirmed **safe** — the only
  consumer of that JSON, `run_export`, reads exclusively `pattern_data['patterns']` and
  `['references']` (`main.py:522-523`); `variations`/`stats` are never read downstream.
  `run_frames`/`run_export`/`run_detect_patterns` pass `required_keys=[]` to
  `load_json_stage` and then iterate the all-optional channel dict via `frames_to_events` —
  genuinely safe, not a guard gap.
- **Dim 2**: shared constants `PATTERN_MIN_LENGTH=3`/`PATTERN_MAX_LENGTH=12`
  (`main.py:36-37`) used by both `run_detect_patterns` (`main.py:622-624`) and
  `run_full_pipeline`'s parallel + fallback detectors (`main.py:829,837`). No other call
  site hardcodes divergent bounds. `--no-patterns` stub stats schema (`main.py:868-876`)
  matches both detectors' key set. No parity drift.
- **Dim 3**: argparse-declared globals (`--version`/`--verbose`/`--debug`/`--arranger`,
  `main.py:1083-1086`) are a subset of the manual default-path whitelist (`main.py:1269-1308`),
  which additionally handles `--no-patterns`/`--skip-validation`/`--config`/`--mapper` —
  the default-path-only flags. Both new global flags (`--config`, `--mapper`) are in the
  whitelist and consumed by `SimpleArgs` (`main.py:1337-1340`) → `run_full_pipeline`. No
  legitimate global flag falls through to the unknown-option hard-error.
- **Dim 4**: CC65 failure surfaces as `False` → `sys.exit(1)` on both paths
  (`main.py:1024-1026`, `main.py:447-449`). `validate_rom` gates boot-fatal defects
  (bad vectors / zero APU init) before consulting `overall_health` (`main.py:387-396`).
  DPCM-pack failure is non-fatal-by-design and surfaced in the banner (`main.py:1053-1054`).
- **Dim 5**: default path writes intermediates into `TemporaryDirectory(prefix="midi2nes_")`
  (`main.py:770`); final ROM written to the user's `output_rom` outside the temp dir
  (`main.py:1024`), surviving cleanup. Exporter still truncates (`'w'`) before any DPCM
  append, so re-runs can't accumulate duplicate `dpcm_*` symbols.
- **Dim 6**: single `finally` restore (`main.py:1071-1075`) covers every exit inside the
  `try`; success branch unlinks the backup (`main.py:1059-1061`). `run_compile` mirrors this
  (`main.py:458-462`).
- **Dim 7**: fallback uses `sample_events_for_detection` (uniform `np.linspace`), not a head
  cut; warning describes analysis-only loss. Parallel `except Exception` (`main.py:832`)
  catches worker/pickle errors with the documented sequential fallback.
- **Dim 8**: song-bank path still disjoint from the ROM pipeline — a known roadmap gap
  (`docs/ROADMAP.md`, F-13/#30), not a functional defect; `add_song_from_midi` still uses
  `tracker.parser_fast`. No doc-rot drift observed.

## Suggested next step

Nothing to file — zero new findings. PL-08/#269 (LOW) remains open and already tracked;
PL-07/#267 and PL-09/#285 are verified fixed and can be closed if not already.

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-07-06.md
```
