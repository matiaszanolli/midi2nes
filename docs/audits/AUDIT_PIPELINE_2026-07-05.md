# Pipeline Integrity Audit — 2026-07-05

Scope: end-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) audited as a contract-bound system per
`.claude/commands/audit-pipeline/SKILL.md`, all dimensions. HEAD = `a7de0d4`.

This is a re-audit of `docs/audits/AUDIT_PIPELINE_2026-07-03.md` after a large fix sprint touched
`main.py`, `compiler/compiler.py`, `nes/song_bank.py`, and the exporter/mapper wiring. Commits
since 07-03 that touch pipeline code: `c3cc399` (#176/#177/#178 — the four open findings from the
07-03 report), `69a75b9` (#179/#170/#171), `d8fc083` (#215/#216/#217 — `--mapper` flag),
`5ff6c4a` (#214 — mapper post-process in compiler), `a420395` (#23/#28/#32), `91bcead`/`e8b39b2`
(#116-119, #218/#219 — compact JSON + config-driven sampling caps), `69f907f` (#220/#221),
`b7c99c8` (#80/#83), `84955f3` (#168/#169 — pattern positions / coverage metric).

**Dedup**: used the pre-fetched open-issue list at `/tmp/audit/issues.json` (36 open issues) and
read every prior `docs/audits/AUDIT_PIPELINE_*.md`. Every candidate below was checked against the
issue list and prior reports before being written up. The four findings open at 07-03
(#176/#177/#178/#179) are **no longer in the open list** and are confirmed fixed in code (see
Verified-fixed).

## Summary

**Two NEW findings (1 MEDIUM, 1 LOW). Zero CRITICAL/HIGH.** The entire fix sprint's pipeline
work re-verified clean:

- **PL-03/#176, PL-04/#177, PL-05/#178, PL-06/#179** — all four fixed and confirmed at HEAD,
  no regression.
- **E4/#23** (DPCM append double-write) — closed; the exporter's `'w'`-mode primary write still
  truncates before the append, so a plain `export` re-run does not double the DPCM block.
- The new `--mapper`/`--config` global-flag routing, the `resolve_mapper`/`check_mapper_capacity`
  capacity gate, the shared `_backup_existing_rom`/`_restore_backup` contract, and the
  `compile`-subcommand backup parity were all read line-for-line and reproduced.
- **NEW PL-07 (MEDIUM)**: the newly-wired `--config` flag silently reverts to built-in defaults
  when its path does not exist — `ConfigManager._load_config` treats a missing given path exactly
  like "no config given". `python main.py config validate <nonexistent>` even reports a
  nonexistent file as valid (live-reproduced).
- **NEW PL-08 (LOW)**: `compile --mapper` offers no `auto`, so a project prepared with
  `prepare --mapper auto` cannot be re-driven through the step-by-step `compile` subcommand with a
  matching value — a prepare→compile parity gap. It fails loudly (mapper size-check mismatch), so
  impact is usability, not a silent bad ROM.
- `tests/test_main.py` + `tests/test_main_pipeline.py` pass (151/151) at HEAD.

### Single most dangerous open item
**PL-07 (MEDIUM)** — a mistyped or missing `--config` path is silently ignored rather than
erroring. Blast radius is bounded: the only thing `--config` currently overrides is the
pattern-detection event-sampling caps (`max_events`/`max_pattern_events`), which per CLAUDE.md's
Assembly Export section affect only compression *analysis* — every emitted ROM byte still derives
from the full `frames` dict — so a silently-ignored config never changes the song. No
CRITICAL/HIGH contract break is open in this dimension at HEAD.

### Does the step-by-step path produce the same ROM as the default path?
**Yes, materially.** Both paths parse with `tracker/parser_fast.py`, produce the same `frames`
shape, export through `CA65Exporter.export_tables_with_patterns(standalone=False)`, pack only
song-referenced DPCM (#140), resolve the mapper through the same `resolve_mapper` +
`check_mapper_capacity` gate, and compile + validate through the same `compile_rom`/`validate_rom`
pair (#15). The one detector asymmetry — the default path runs `ParallelPatternDetector` while
`detect-patterns` runs the sequential `EnhancedPatternDetector`, which can yield different
`patterns` dicts — does **not** change the ROM: the exporter uses `patterns` only for its
truthiness (bytecode serializer vs. direct frames), never its contents (#4, documented). The one
caveat is PL-08: a `prepare --mapper auto` selection has no exact `compile --mapper` equivalent
(fails loud, not silent).

### Findings per dimension
- **Dimension 1 (stage JSON contracts)**: 0 new. Both detectors emit an identical `stats` schema
  via the shared `calculate_compression_stats` (`original_size`/`compressed_size`/
  `compression_ratio`/`unique_patterns`/`total_events`/`patterned_events`/`coverage_ratio`), so
  the success banner's new `coverage_ratio`/`total_events` reads (`main.py:929-932`, inside the
  `try` before `build_succeeded=True`) cannot `KeyError` and discard a freshly-built valid ROM.
  Verified. `dpcm_sample_map` side-table (#200) is skipped by every consumer (both event-flatten
  loops, `export_direct_frames`, and the bytecode channel loop). Verified.
- **Dimension 2 (full vs step parity)**: 0 new. Shared `PATTERN_MIN/MAX_LENGTH`, shared
  `get_pattern_detection_caps`, shared `validate_rom`, shared backup helpers. PL-08 (LOW) is the
  one residual `prepare`→`compile` asymmetry.
- **Dimension 3 (flag routing)**: PL-06/#179 (`--version`) fixed; **PL-07 (NEW, MEDIUM)** —
  `--config` missing-file silent default.
- **Dimension 4 (fail-fast)**: PL-04/#177 fixed — `validate_rom` now `return False`s (not `True`)
  when the diagnostics engine itself raises, and always prints the warning. 0 new.
- **Dimension 5 (temp/intermediate handling)**: 0 new; unchanged.
- **Dimension 6 (backup/overwrite safety)**: PL-05/#178 fixed — `run_compile` now has the same
  `_backup_existing_rom`/`_restore_backup` contract as the default path; a first-build validation
  failure moves the unbootable ROM to `<name>.nes.failed` instead of leaving it at the output. 0
  new.
- **Dimension 7 (large-file threshold & fallback)**: PL-03/#176 fixed — the fallback message now
  states sampling is "for compression analysis only — ... ROM content is unaffected" and drops the
  false `--no-patterns` advice. 0 new.
- **Dimension 8 (song bank)**: 0 new. Parser drift stays fixed (`nes/song_bank.py` uses
  `parser_fast`); `song add` JSON-import is now guarded (#220).

**Severity totals (this report): CRITICAL 0 · HIGH 0 · MEDIUM 1 · LOW 1 · Total 2 (both NEW).**

## Contract Map

| Stage boundary | Producer (fn → key(s)) | Consumer (fn) | Verified |
|---|---|---|:--:|
| parse → map | `parser_fast.parse_midi_to_frames` → `{"events",...}` (compact JSON, #116) | `run_map` reads `["events"]` via `load_json_stage` guard | ✓ |
| map → frames | `assign_tracks_to_nes_channels(events, dpcm_index)` → `{pulse1,pulse2,triangle,noise,dpcm}` | `NESEmulatorCore.process_all_tracks` (+`dpcm_sample_map` side table, #200) | ✓ |
| arrange → frames | `arrange_for_nes(events, arp_speed, verbose)` → `{channel:{frame:{...}}}` | exporter / detector flatten (`int(frame_num)`-tolerant, skips `dpcm_sample_map`) | ✓ |
| frames → detect | `{channel:{frame:{note,volume,...}}}` | both entry points flatten identically; `dpcm_sample_map` skipped in both | ✓ |
| detect → export | `{patterns, references, stats}` (`variations` dropped by `run_detect_patterns`) | `run_export` reads `patterns`/`references` via guard; exporter ignores `references` (#4) | ✓ |
| stats → banner | `compression_ratio`/`unique_patterns`/`total_events`/`coverage_ratio` (identical both detectors) | success banner + subcommand print | ✓ |
| export → prepare | `export_tables_with_patterns(...)` writes music.asm (+DPCM append) | `resolve_mapper` + `check_mapper_capacity` gate → `NESProjectBuilder.prepare_project` | ✓ |
| prepare → compile | project dir + selected mapper | `compile_rom(...,mapper=)` → exact PRG-size check (#28) + mapper post-process (#214); CC65 nonzero → `CompilationError` → `False` | ✓ / PL-08 (mapper choice not recoverable from dir) |
| compile → validate | `.nes` | `validate_rom` — boot-fatal on bad vectors / zero APU init (#6); diagnostics-engine failure now → `False` (#177) | ✓ |
| `--config` → caps | CLI path → `get_pattern_detection_caps` → `ConfigManager` | sampling caps | ✗ silent default on missing path (PL-07) |

## Findings

### PL-07: `--config` silently reverts to built-in defaults when the given path does not exist
- **Severity**: MEDIUM
- **Dimension**: 3 — Flag Routing
- **Both paths?**: Both — the default `run_full_pipeline` (`--config` global flag) and the
  `detect-patterns --config` subcommand both route to `get_pattern_detection_caps`; the `config
  validate` subcommand is the most user-visible manifestation.
- **Location**: `config/config_manager.py:110-115` (`_load_config`); wired into the pipeline at
  `main.py:38-54` (`get_pattern_detection_caps`), `main.py:1170-1175` (default-path `--config`
  routing), `main.py:502`/`main.py:738` (consumers), and `main.py:1236-1252` (`run_config_validate`).
- **Status**: NEW
- **Description**: `ConfigManager._load_config` does `if self.config_path and self.config_path.exists():
  _load_from_file(...) else: _load_defaults()`. A path that is passed **but does not exist** falls
  into the `else` and silently loads the built-in defaults — indistinguishable from passing no
  config at all. `--config` was only recently wired to actually be consumed (#219, previously it
  was dropped), so this silent no-op is newly reachable from the pipeline. There is no warning on
  any path.
- **Evidence**: Live-reproduced:
  ```
  $ python main.py config validate /tmp/does_not_exist_xyz.yaml
  [OK] Configuration file is valid: /tmp/does_not_exist_xyz.yaml
  ```
  A nonexistent file is reported valid because `validate()` runs against the silently-loaded
  defaults. The identical mechanism means `midi2nes --config typo.yaml song.mid` and
  `detect-patterns --config typo.yaml ...` run with default sampling caps, not the user's.
- **Impact**: Bounded. `--config` currently overrides only `processing.pattern_detection.max_events`
  / `max_pattern_events` (the pattern-detection event-sampling caps). Per CLAUDE.md's Assembly
  Export section, sampling affects only compression *analysis*; every emitted ROM byte still comes
  from the full `frames` dict, so a silently-ignored `--config` never changes the song — only the
  compression stats/telemetry. The `config validate` false-positive is the sharper edge: it green-
  lights a path that isn't there. Recoverable (the user can notice the caps didn't change), so
  MEDIUM per the "missing error handling on a recoverable path (bad config file)" row of
  `_audit-severity.md`, not the CRITICAL "ignored flag → silent song change" floor.
- **Related**: #222 (SAFE-11, ConfigManager save/validate typed-exception gap) is adjacent but
  distinct; #13/#109 (scoped `--config` wiring philosophy).
- **Suggested Fix**: In `_load_config`, distinguish "no path given" from "path given but missing":
  if `self.config_path` is set and does not exist, raise `ConfigurationError` (already imported and
  used two lines down) instead of falling through to `_load_defaults()`. That makes `config
  validate` reject a missing file and makes a mistyped pipeline `--config` fail fast rather than
  silently no-op.

### PL-08: `compile --mapper` has no `auto`, so a `prepare --mapper auto` project has no matching compile invocation
- **Severity**: LOW
- **Dimension**: 2 — `run_full_pipeline` vs Step-by-Step Parity
- **Both paths?**: Step-by-step only (`prepare` → `compile`).
- **Location**: `main.py:1034-1036` (`prepare --mapper` choices include `auto`) vs
  `main.py:1044-1046` (`compile --mapper` choices are `nrom`/`mmc1`/`mmc3` only); mismatch surfaces
  in `resolve_mapper`/`compile_rom`'s exact-size check (`compiler/compiler.py:192-201`).
- **Status**: NEW
- **Description**: `prepare` accepts `--mapper auto`, which resolves at prepare-time to whichever
  mapper `MapperFactory.auto_select()` picks by data size and bakes that mapper's `nes.cfg`/header
  into the project directory. The `compile` subcommand cannot recover that choice from the project
  directory (its docstring at `main.py:344-350` acknowledges this) and offers no `auto` value, so
  the user must know the resolved mapper and pass it explicitly. If they accept `compile`'s default
  (`mmc3`) against a project auto-resolved to `nrom`/`mmc1`, `compile_rom`'s exact PRG-size check
  raises a `CompilationError` (the three mappers have distinct PRG sizes — 32K/128K/512K — so there
  is no false pass), the build fails, and the backup/`.failed` restore contract (#178) kicks in.
- **Evidence**: `compile`'s parser: `p_compile.add_argument('--mapper', choices=['nrom','mmc1','mmc3'],
  default='mmc3', ...)` — no `auto`. `resolve_mapper` for a non-bytecode `music.asm` returns the
  literal mapper, and `compile_rom(...,mapper=mmc3)` then compares `game.nes` (linked with the
  project's real `nes.cfg`) against `mmc3.prg_rom_size+16`, mismatching and raising.
- **Impact**: Usability/parity only — a fully-recoverable loud failure with a clear size-mismatch
  message and no bad ROM left behind (the size distinctness rules out a silent header/`nes.cfg`
  mismatch, so this is not the HIGH "mapper header vs nes.cfg mismatch" floor). The default
  `run_full_pipeline` path is unaffected (it threads one mapper object end-to-end).
- **Related**: #217/MAP-6 (the `--mapper` flag), #15 (`prepare`→`compile` parity).
- **Suggested Fix**: Either add `auto` to `compile --mapper` (re-running `auto_select` against the
  project's own `music.asm`, exactly as `resolve_mapper` already does), or have `prepare` record
  the resolved mapper into the project dir (e.g. a `mapper.txt` or a comment in `nes.cfg`) so
  `compile` can default to it instead of a fixed `mmc3`.

## Verified-fixed since 2026-07-03

- **PL-03 (#176)** — fallback + success-banner warnings reworded: `main.py:760-766` now says the
  sample feeds "compression analysis only — ... ROM content is unaffected" and drops the
  `--no-patterns` advice. Confirmed by reading the code (commit `c3cc399`).
- **PL-04 (#177)** — `validate_rom` (`main.py:294-299`) now `return False` on a diagnostics-engine
  exception (was `return True`) and always prints "ROM validation could not run: ... — ROM NOT
  validated" (no longer gated on `--verbose`). Confirmed (commit `c3cc399`).
- **PL-05 (#178)** — `run_compile` (`main.py:327-376`) now creates a backup via
  `_backup_existing_rom`, restores it (or moves the unbootable ROM to `<name>.nes.failed`) in a
  `finally`, and unlinks it on success — parity with the default path's contract. Confirmed
  (commit `c3cc399`).
- **PL-06 (#179)** — the manual dispatch loop (`main.py:1157-1163`) now handles `--version` by
  printing and `sys.exit(0)` immediately, matching argparse's `action='version'`, so
  `midi2nes --version song.mid` prints the version instead of silently running the pipeline.
  Confirmed (commit `69a75b9`).
- **E4 (#23)** — `run_export`'s DPCM append (`main.py:484`) is still `open(args.output, 'a')`, but
  `export_tables_with_patterns` writes the primary output in `'w'` mode first, so a plain `export`
  re-run truncates before appending — no duplicate `dpcm_*` symbols. Issue is closed; residual risk
  is limited to appending after a hand-edited `music.asm` within one run.
- **#28/#32/#214** — `compile_rom` now takes a `mapper` and does an exact PRG-size check
  (`compiler/compiler.py:192-201`) instead of the flat 32768 floor, runs the mapper's post-link
  fixup (`compiler/compiler.py:183-189`), and surfaces a traceback under `--verbose` on an
  unexpected exception (`compiler/compiler.py:250-251`). Read and confirmed.

## Suggested next step

Two new findings to file (PL-07 MEDIUM, PL-08 LOW). No CRITICAL/HIGH open in this dimension.

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-07-05.md
```
