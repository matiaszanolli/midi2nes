# Pipeline Integrity Audit — 2026-07-05 (re-audit)

Scope: end-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) audited as a contract-bound system per
`.claude/commands/audit-pipeline/SKILL.md`, all 8 dimensions. HEAD = `78cf319`
(branch `fix/regression-rom-validation-128-129`, test-only commit on top of
`bcc0395`/master's tip at the time of this pass).

**This supersedes the same-day `docs/audits/AUDIT_PIPELINE_2026-07-05.md` written at
`a7de0d4`.** That pass predates 7 further commits that touched pipeline code, most
importantly `8c2f8aa` (#254/#255, merged via PR #270/#271): it removed the DPCM
oversized-id guard and — the change this re-audit focuses on — implemented real
MMC1 bank-switching for direct (`--no-patterns`) export. That required `main.py` to
resolve the target `--mapper` **before** calling the exporter for the direct-export
branch (`resolve_mapper`/`MapperFactory` + the new `CA65Exporter.estimate_direct_export_size`),
in both `run_export` and `run_full_pipeline`. That reorder is deliberate, already-shipped
architecture — not re-litigated here — but it opens a new cross-stage artifact contract
(bank-packed `RODATA_BANK_NN` segments + baked-in mapper-specific bank-switch asm) that this
pass audits for completeness under Dimensions 1 and 2.

**Dedup**: `/tmp/audit/issues.json` (33 open issues, `gh issue list ... --limit 200`,
default state=open) plus every prior `docs/audits/*.md`, including the mapper-domain
`AUDIT_MAPPERS_2026-07-05.md` (written before `8c2f8aa` landed — it found the CRITICAL
that `8c2f8aa` fixed; re-confirmed fixed below, not re-reported). One genuinely new finding
came out of this pass (PL-09); everything else previously open in this dimension
(PL-07/#267, PL-08/#269) is unchanged, and PL-03..PL-06 remain fixed/closed as previously
verified.

## Summary

**One NEW finding this pass: PL-09, HIGH.** Zero CRITICAL. Two prior findings (PL-07
MEDIUM, PL-08 LOW) remain open, unchanged. PL-03..PL-06 stay fixed.

- **PL-09 (NEW, HIGH)** — the pre-export mapper resolution added for MMC1 bank-switching
  (#255) created a new class of mapper-specific artifact in `music.asm`
  (`RODATA_BANK_NN` segments + inline bank-switch asm), but `check_mapper_capacity`'s
  per-mapper `validate_segment_sizes` guard — the exact gate whose job is "fail before
  linking with a clear message instead of a raw `ld65` error" — silently ignores those
  segments for MMC3 and NROM. Running `export --mapper mmc1 …` (or `--mapper auto` on a
  30–112 KB song) followed by `prepare`/`compile` with any **other** mapper (including the
  default `mmc3`) reports a false "✓ Music data N bytes fits the MMC3 PRG regions" and then
  fails at `ld65` with `Missing memory area assignment for segment 'RODATA_BANK_00'` —
  **live-reproduced below**. Not silent-corruption (no ROM is produced), so it does not meet
  the CRITICAL floor, but it is exactly the class of raw-`ld65`-error the pre-flight gate
  exists to prevent, and no equivalent to `_requires_mmc3_bytecode_engine`'s forcing check
  exists for this direction. Both call sites of the reorder (`run_export`,
  `run_full_pipeline`) were read; **the default full-pipeline path is unaffected** — it
  resolves one mapper object and threads it unchanged through export → prepare → compile, so
  this gap is step-by-step-subcommand-only.
- **PL-07/#267 (MEDIUM, unchanged, still open)** — `--config` with a nonexistent path
  silently falls back to defaults instead of erroring; re-confirmed live
  (`config validate` still reports a missing file "valid").
- **PL-08/#269 (LOW, unchanged, still open)** — `compile --mapper` still has no `auto`
  choice, so a `prepare --mapper auto` project has no matching `compile` invocation.
- **PL-03/#176, PL-04/#177, PL-05/#178, PL-06/#179** — all four re-verified fixed at HEAD,
  no regression (see Verified-fixed).
- The DPCM-guard fix and MMC1 bank-switching work (#254/#255) itself: read and spot-checked
  by building and linking a real ROM; no fresh bug found in the mechanism itself beyond PL-09.
- `#257/#258` (coverage_ratio measured in analyzed-event space; `variations` added to the
  `--no-patterns` stub) — metrics-only fix, re-confirmed both detectors and the stub now
  share one 4-key envelope; no pipeline-contract impact.
- `tests/test_main.py` + `tests/test_main_pipeline.py`: 154/154 pass at HEAD.

### Single most dangerous open item
**PL-09 (HIGH)** is the most dangerous *pipeline-contract* item open right now: it is the
one place a stage-boundary guard (`check_mapper_capacity`) gives false "fits" confidence
for a real, reachable input combination. It stops short of CRITICAL only because the
failure is loud (a raw `ld65` link error, no ROM emitted, no corruption) rather than a
silently-shipped broken ROM — the CRITICAL version of this exact bug class
(`MAP-2026-07-05-1`, MMC1 direct export overflowing its window with **no** link error) was
already found and is already fixed by the same `8c2f8aa` commit this pass re-audits.

### Does the step-by-step path produce the same ROM as the default path?
**Yes, for the shipped/documented workflows.** Both paths parse with `parser_fast`, produce
identical `frames`, export through `export_tables_with_patterns`, pack only
song-referenced DPCM, and compile+validate through the same `compile_rom`/`validate_rom`
pair. The default `run_full_pipeline` path resolves its mapper exactly once (`main.py:806-818`
for direct export, `main.py:908-913` for the bytecode path) and threads that single object
through export, `check_mapper_capacity`, `NESProjectBuilder`, and `compile_rom` — no
divergence found there. The **only** way to get a different result via the step-by-step
subcommands is to deliberately pass a **different** `--mapper` value to `export` than to
`prepare`/`compile` for a bank-packing-capable mapper (currently only MMC1) — this is
PL-09 above, and PL-08 (the `auto` asymmetry) is the milder, already-known sibling of the
same underlying fact: `export --mapper`, `prepare --mapper`, and `compile --mapper` are
three independently-parsed flags with no shared source of truth once you leave the default
pipeline.

## Contract Map

| Stage boundary | Producer (fn → key(s)) | Consumer (fn) | Verified |
|---|---|---|:--:|
| parse → map | `parser_fast.parse_midi_to_frames` → `{"events",...}` (compact JSON) | `run_map` reads `["events"]` via `load_json_stage` guard | ✓ |
| map → frames | `assign_tracks_to_nes_channels(events, dpcm_index)` → `{pulse1,pulse2,triangle,noise,dpcm}` | `NESEmulatorCore.process_all_tracks` (+`dpcm_sample_map` side table) | ✓ |
| arrange → frames | `arrange_for_nes(events, arp_speed, verbose)` → `{channel:{frame:{...}}}` | exporter / detector flatten via shared `frames_to_events` (#261), skips `dpcm_sample_map` | ✓ |
| frames → detect | `{channel:{frame:{note,volume,...}}}` | both entry points flatten identically | ✓ |
| detect → export | `{patterns, references, stats, variations}` (`run_detect_patterns` still saves only 3 keys, drops `variations` — unconsumed, not a bug) | `run_export` reads `patterns`/`references` via guard; exporter ignores `references` (#4, documented) | ✓ |
| stats → banner | `original_size`/`compressed_size`/`compression_ratio`/`unique_patterns`/`total_events`/`patterned_events`/`coverage_ratio` (identical both detectors + `--no-patterns` stub) | success banner + subcommand print | ✓ |
| **export → prepare (mapper choice)** | `export --mapper` resolves a mapper *before* writing `music.asm`; a bank-packing mapper (MMC1) bakes `RODATA_BANK_NN` segments + inline bank-switch asm into the file | `prepare`/`compile --mapper` (independently parsed, default `mmc3`) → `check_mapper_capacity` → `NESProjectBuilder`/`compile_rom` | **✗ PL-09** — capacity gate silently ignores segments it doesn't recognize instead of flagging the mismatch |
| export → prepare (bytecode) | MMC3 macro-bytecode `music.asm` (marker comment) | `resolve_mapper`'s `_requires_mmc3_bytecode_engine` forces MMC3 regardless of `--mapper` | ✓ |
| prepare → compile | project dir + selected mapper | `compile_rom(...,mapper=)` → exact PRG-size check + mapper post-process; CC65 nonzero → `CompilationError` → `False` | ✓ / PL-08 (mapper choice not recoverable from dir) |
| compile → validate | `.nes` | `validate_rom` — boot-fatal on bad vectors / zero APU init; diagnostics-engine failure → `False` (#177) | ✓ |
| `--config` → caps | CLI path → `get_pattern_detection_caps` → `ConfigManager` | sampling caps | ✗ silent default on missing path (PL-07) |

## Findings

### PL-09: `check_mapper_capacity` silently ignores MMC1 bank-packed segments when a different mapper is chosen at `prepare`/`compile` time, turning a preventable pre-flight error into a raw `ld65` link failure
- **Severity**: HIGH
- **Dimension**: 1 (Stage JSON/artifact Contract Integrity) and 2 (`run_full_pipeline` vs Step-by-Step Parity)
- **Both paths?**: Step-by-step only. The default `run_full_pipeline` resolves one mapper
  object once (`main.py:806-818` direct-export branch) and reuses it for `check_mapper_capacity`,
  `NESProjectBuilder`, and `compile_rom` (`main.py:908-932`) — no divergence possible there.
  This is exclusively a gap between the independently-parsed `export --mapper`
  (`main.py:1053`) and `prepare --mapper` / `compile --mapper` (`main.py:1063`, `main.py:1073`).
- **Location**: `main.py:444-472` (`run_export`'s pre-export mapper resolution, new in
  #255/MAP-2026-07-05-1); `exporter/exporter_ca65.py:249-268` (`export_direct_frames`
  bin-packs into `RODATA_BANK_NN` segments whenever `mapper.direct_export_bank_size()` is
  not `None` — currently true only for `MMC1Mapper`, `mappers/mmc1.py:163-166`);
  `mappers/mmc3.py:169-243` (`validate_segment_sizes` only reads `RODATA`/`CODE`/`CODE_8000`
  and segments prefixed `BANK_`/`DPCM_` — anything else, including `RODATA_BANK_NN`, is
  silently skipped, `mmc3.py:210-212`); `mappers/nrom.py` (inherits `BaseMapper`'s flat
  `validate_segment_sizes`, `mappers/base.py:183-200`, which sums *all* segment sizes into
  one total against `get_data_capacity()` — it doesn't reject `RODATA_BANK_NN` by name, but
  NROM's `nes.cfg` never declares that segment either, so the same link failure occurs even
  though the size check would have technically "passed").
- **Status**: NEW
- **Description**: `CA65Exporter.export_direct_frames` now asks the mapper
  `bank_size = mapper.direct_export_bank_size()` and, when not `None`, bin-packs every
  direct-export frame table into per-bank segments named `RODATA_BANK_00`, `RODATA_BANK_01`,
  … and prefixes each table read with `mapper.generate_bank_switch_code(bank)` — mapper-
  specific inline assembly (MMC1's real 5-write serial `$E000` bank-select protocol).
  `MMC1Mapper.generate_linker_config()` (and its `validate_segment_sizes` override) knows
  about `RODATA_BANK_NN`; **no other mapper does**. `run_export`/`run_full_pipeline` resolve
  this mapper choice from the `export`-time `--mapper` flag alone and never record it
  anywhere the project directory or `music.asm` can be checked against later. `prepare`
  and `compile` each parse their *own*, independent `--mapper` flag (default `mmc3`) and
  hand it to `check_mapper_capacity`, whose entire purpose (per its own docstring) is to
  "abort before linking... instead of a raw `ld65` region overflow." For MMC3/NROM that
  function's `validate_segment_sizes` has no branch for `RODATA_BANK_NN`, so those bytes
  are counted nowhere, the check reports success, and the failure is deferred to `ld65`
  itself with a much less actionable message.
- **Evidence**: Live-reproduced end-to-end with the real CC65 toolchain (`ca65`/`ld65`
  V2.18):
  ```
  $ python main.py export small_frames.json small_music.asm --mapper mmc1
    ...
    Data size: 1,600 bytes (1.6 KB)
  $ grep '\.segment' small_music.asm | sort -u
  .segment "RODATA_BANK_00"
  .segment "CODE"
  .segment "RODATA"
  .segment "BSS"

  $ python main.py prepare small_music.asm nes_project     # default --mapper mmc3
    ✓ Music data 1,604 bytes fits the MMC3 PRG regions      <- FALSE: RODATA_BANK_00 unrecognized
    Using MMC3 with 512KB PRG-ROM
   Prepared NES project -> nes_project

  $ python main.py compile nes_project out.nes --verbose
    Compiling music.asm...
    Assembled: music.asm -> music.o
    Linking ROM...
  [ERROR] Failed to link ROM: ld65: Error: Missing memory area assignment for segment 'RODATA_BANK_00'
  [ERROR] ROM compilation failed
  ```
  No `out.nes` is produced (confirmed via `ls`) — the failure is loud and no ROM ships, so
  this does not meet the CRITICAL "silently ships a broken ROM" floor, but the pre-flight
  gate's own stated purpose (avoid exactly this raw `ld65` message) is defeated for this
  input combination.
- **Impact**: Reachable any time a user picks `--mapper mmc1` (or `--mapper auto`, which
  routes 30–112 KB direct-export songs to MMC1 per `MapperFactory.auto_select`) on `export`
  and does not pass the *identical* `--mapper` to the subsequent `prepare`/`compile` step —
  including simply omitting `--mapper` on `prepare`/`compile` and getting their `mmc3`
  default. The documented step-by-step example in `CLAUDE.md` doesn't pass `--mapper` to
  `export` at all (defaults to `mmc3`, which never bank-packs, so the documented workflow is
  unaffected) — this is an edge combination within the subcommands, not the default path,
  but it is one the `--mapper` flag itself (#217/MAP-6) was built to make reachable, and
  the failure UX (a raw linker error) is strictly worse than what the pre-flight gate was
  designed to give every other capacity mismatch.
- **Related**: `MAP-2026-07-05-1` (the CRITICAL this same commit fixed — MMC1 direct export
  silently overflowing its window with no link error at all; this finding is the "loud
  failure" cost of that fix landing without a matching cross-stage mapper-identity guard).
  PL-08/#269 (the milder, already-filed sibling: `prepare --mapper auto` has no `compile`
  equivalent) — both stem from the same root fact that `export`/`prepare`/`compile` mapper
  choices have no shared source of truth outside the default pipeline. #217/MAP-6 (added
  the `--mapper` flag family this depends on).
- **Suggested Fix**: Either (a) record which mapper `export`/`run_full_pipeline` used to
  bank-pack `music.asm` — e.g. a marker comment analogous to `_requires_mmc3_bytecode_engine`'s
  "MMC3 Macro Bytecode" string, such as `; Direct export packed for <mapper.name> bank-switching`
  — and teach `resolve_mapper` to read it back and force/validate that mapper the same way it
  already forces MMC3 for the bytecode marker; or (b) make `validate_segment_sizes` on every
  mapper explicitly reject (not silently ignore) any segment name it doesn't recognize as its
  own, turning today's false "✓ fits" into a clear "this music.asm was built for a different
  mapper" pre-flight error instead of deferring to `ld65`.

---

## Re-confirmed still open (unchanged since 07-03/07-05 at `a7de0d4`)

### PL-07/#267: `--config` silently reverts to built-in defaults when the given path does not exist
- **Severity**: MEDIUM · **Status**: Existing: #267 (OPEN, unchanged)
- Re-confirmed live: `python main.py config validate /tmp/does_not_exist_xyz.yaml` still
  prints `[OK] Configuration file is valid: ...`. `config/config_manager.py`'s
  `_load_config` still treats "path given but missing" the same as "no path given". No
  change since the 07-05 (`a7de0d4`) report; not re-detailed here.

### PL-08/#269: `compile --mapper` has no `auto`, so a `prepare --mapper auto` project has no matching compile invocation
- **Severity**: LOW · **Status**: Existing: #269 (OPEN, unchanged)
- Re-confirmed: `main.py:1073` (`p_compile.add_argument('--mapper', choices=['nrom','mmc1','mmc3'], default='mmc3', ...)`)
  still has no `auto` choice. No change since the 07-05 (`a7de0d4`) report.

## Verified-fixed since the previous pass (`a7de0d4` → `78cf319`)

- **PL-03 (#176)**: fallback/success-banner warning still reads "for compression analysis
  only — ... ROM content is unaffected" (`main.py:757-763`), no `--no-patterns` misdirection.
  Confirmed unchanged/fixed.
- **PL-04 (#177)**: `validate_rom` (`main.py:294-299`) still `return False`s (not `True`) on
  a diagnostics-engine exception, always prints the warning. Confirmed unchanged/fixed.
- **PL-05 (#178)**: `run_compile` (`main.py:327-376`) still creates/restores a backup via
  `_backup_existing_rom`/`_restore_backup`, moving a first-build failure's unbootable ROM to
  `<name>.nes.failed`. Confirmed unchanged/fixed.
- **PL-06 (#179)**: the manual dispatch loop (`main.py:1186-1192`) still handles `--version`
  with an immediate `print` + `sys.exit(0)`. Confirmed unchanged/fixed.
- **`MAP-2026-07-05-1`** (from `AUDIT_MAPPERS_2026-07-05.md`, written before `8c2f8aa`
  landed): MMC1 direct export silently overflowing its 16 KB window with no link error is
  now **fixed** by `8c2f8aa` (#254/#255) — `MMC1Mapper` now declares 7 separate `$8000`-based
  `PRG_BANK_NN` regions (`mappers/mmc1.py:61-105`), `direct_export_bank_size()` returns the
  16 KB window (`mmc1.py:163-166`), `CA65Exporter` bin-packs tables and bank-switches
  (`exporter_ca65.py:107-268`), and `MMC1Mapper.validate_segment_sizes` now understands its
  own `RODATA_BANK_NN` segments (`mmc1.py:168-210`). Verified by building and linking a real
  multi-bank MMC1 ROM (208.8 KB of direct-export data spanning `RODATA_BANK_00..12`) through
  the actual pipeline — this also incidentally surfaced that `run_export` itself does not
  pre-check the bank count against `MMC1Mapper.SWAP_BANK_COUNT` (only `prepare`'s
  `check_mapper_capacity` does, correctly raising when the *matching* mapper is used), which
  is expected/by-design, not a gap: `export` only ever writes `music.asm`, and the
  authoritative capacity gate is deliberately deferred to `prepare`/`full-pipeline` per
  `check_mapper_capacity`'s own docstring.
- **#257/#258**: `coverage_ratio` now measured in post-sampling analyzed-event space on both
  detectors (`tracker/pattern_detector.py`), and the `--no-patterns` stub's 4-key envelope now
  includes `variations: {}` matching both detectors. Metrics-only; no contract-break impact.
  Confirmed via `git show e2cccc0`.
- Tech-debt import cleanup (`2823594`, #264/#227/#228) and dead-code pruning (`1bf4a95`,
  #165/#166) touch `main.py`/`exporter_ca65.py` but not the mapper-resolution or stage-JSON
  contract logic audited here; `python -m pytest tests/test_main.py tests/test_main_pipeline.py`
  passes 154/154 at HEAD.

## Suggested next step

One new finding to file (PL-09, HIGH). PL-07 (MEDIUM) and PL-08 (LOW) remain open and
already filed as #267/#269 — no re-filing needed.

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-07-05.md
```
