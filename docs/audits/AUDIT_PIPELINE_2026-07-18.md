# Pipeline Integrity Audit — 2026-07-18 (verify-the-fix pass)

Scope: end-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) audited as a contract-bound system per
`.claude/commands/audit-pipeline/SKILL.md`, all 8 dimensions.

- **HEAD**: `308d712` (master; tip after merges #327/#326 landing the #312–#315 and
  #318–#321 fixes). `main.py` is 1,535 lines — the SKILL's cited line numbers predate
  these commits, so every claim below was re-resolved against the current file.
- **Dedup**: `/tmp/audit/issues.json` — 24 OPEN issues (`gh issue list … --limit 200`,
  default = open only) — plus every prior `docs/audits/AUDIT_PIPELINE_*.md` (most recent
  the earlier `AUDIT_PIPELINE_2026-07-18.md` at `b562e1d`). No open issue tracks a live
  pipeline-contract break; PL-01..PL-09 all remain closed/fixed.
- **Commits touching `main.py` since the previous pass**: `08e7fb2` (#312–#315 — adds
  `coverage_lossy_note`/`coverage_note` labeling on the coverage print sites) and
  `8a2457a` (#318–#321 — `load_config` now raises `ConfigurationError` on a given-but-
  missing `--config` path). Both re-read in full; neither changes an inter-stage contract,
  a stage's JSON shape, a flag route, or the backup/restore/fail-fast structure.

## Summary

**Zero NEW findings. Zero CRITICAL / HIGH / MEDIUM / LOW.** All 8 dimensions pass. Every
"verify-the-fix" checkpoint the skill enumerates was confirmed still in place at `308d712`,
and the two intervening `main.py` commits introduced no regressions.

Finding counts per dimension:
- Dimension 1 (Stage JSON/artifact contract): 0. No drift.
- Dimension 2 (`run_full_pipeline` vs step-by-step parity): 0. Shared constants, single parser.
- Dimension 3 (flag routing): 0. Manual whitelist still in sync with argparse globals.
- Dimension 4 (error propagation / fail-fast): 0. Single try/except/finally intact.
- Dimension 5 (temp-file / intermediates): 0. Exporter still truncates before DPCM append.
- Dimension 6 (backup & overwrite): 0. Shared `_backup_existing_rom`/`_restore_backup`.
- Dimension 7 (large-file threshold / detector fallback): 0. Uniform sampling both paths.
- Dimension 8 (song-bank path): 0. `parser_fast` used; known roadmap gap only (F-13/#30).

### Single most dangerous contract break
**None.** No HIGH/CRITICAL. No item at any severity. The only surviving open pipeline-tagged
issue is **PL-08/#269 (LOW)** — `compile --mapper` has no `'auto'` in its argparse `choices`
— which is cosmetic and functionally superseded by #297 (`run_compile` recovers the prepared
mapper from `nes.cfg` via `_prepared_mapper_name_from_cfg`, `main.py:218-236`, before falling
back to `--mapper`; `main.py:460-461`).

### Does the step-by-step path produce the same ROM as the default path?
**Yes** (by contract, re-confirmed statically). Both entry points import the same
`parser_fast.parse_midi_to_frames` (`main.py:97`, `main.py:810`), share
`PATTERN_MIN_LENGTH=3`/`PATTERN_MAX_LENGTH=12` (`main.py:36-37`) at every detector call site,
and every emitted byte derives from the full `frames` dict — `export_tables_with_patterns`
treats `patterns` truthiness as a serializer switch only and never reads `references`
(`exporter/exporter_ca65.py:965`). The two paths' pattern detectors legitimately see different
sampled event counts (parallel cap `MAX_PATTERN_EVENTS=15000`, sequential/subcommand cap
`DETECTOR_MAX_EVENTS=1000`, `tracker/pattern_detector.py:16,23`) without changing ROM content,
because that data feeds compression *analysis* only.

## Contract Map

| Stage boundary | Producer (fn → key(s)) | Consumer (fn) | Verified |
|---|---|---|:--:|
| parse → map | `parser_fast.parse_midi_to_frames` → `{"events","metadata"}` | `run_map` reads `["events"]` via `load_json_stage` guard (`main.py:106`) | ✓ |
| map → frames | `assign_tracks_to_nes_channels(events, dpcm_index)` → per-channel dict | `NESEmulatorCore.process_all_tracks` (`run_frames`, `main.py:114-121`) | ✓ |
| arrange → frames | `arrange_for_nes(events, arp_speed, verbose)` → `{channel:{frame:{…}}}` | `frames_to_events` / exporter, identical to `process_all_tracks` output | ✓ |
| frames → detect | `{channel:{frame:{note,volume,…}}}` | `frames_to_events` (both entry points, `main.py:653`/`858`) | ✓ |
| detect → export | `run_detect_patterns` writes `{patterns,references,stats}` (`main.py:670-675`); `variations` dropped | `run_export` reads only `patterns`/`references` (`main.py:547-548`) | ✓ |
| stats → banner | `compression_ratio`/`coverage_ratio`/`total_events`/… — identical keys in both detectors' `calculate_compression_stats` + the `--no-patterns` stub (`main.py:922-930`) | success banner (`main.py:1100-1104`), subcommand print (`main.py:680-690`) | ✓ |
| export → prepare (direct) | direct-export `music.asm` stamps `; Direct export bank-packed for <name>` | `resolve_mapper` via `_direct_export_packed_mapper_name` (`main.py:192-215`) raises on mismatch | ✓ |
| export → prepare (bytecode) | MMC3 macro-bytecode `music.asm` marker | `resolve_mapper` / `_requires_mmc3_bytecode_engine` forces/validates MMC3 (`main.py:175-189`) | ✓ |
| prepare → nes.cfg | `NESProjectBuilder` stamps `NES_CFG_MAPPER_MARKER + name` | `_prepared_mapper_name_from_cfg` (`main.py:218-236`) | ✓ |
| prepare → compile | project dir (+ recovered mapper) | `resolve_mapper` re-validated vs project `music.asm`; capacity pre-flight; CC65 nonzero → `False` → `sys.exit(1)` | ✓ |
| compile → validate | `.nes` | `validate_rom` — boot-fatal on bad vectors / zero APU init; diagnostics failure → `False` (`main.py:388-431`) | ✓ |
| `--config` → caps | CLI path → `get_pattern_detection_caps` → `ConfigManager` (`main.py:39-62`) | sampling caps; missing/invalid config → `[ERROR]` + exit 1 | ✓ |

## Findings

No NEW findings this pass.

## Dimension notes (verify-the-fix confirmations, no findings)

- **Dim 1** — `run_detect_patterns` (`main.py:670-675`) still saves only
  `{patterns, references, stats}`, omitting `variations`; the only downstream consumer
  `run_export` reads `pattern_data['patterns']`/`['references']` (`main.py:547-548`) — safe.
  `run_frames`/`run_export`/`run_detect_patterns` pass `required_keys=[]` to `load_json_stage`
  because the channel dict is all-optional keys — genuinely safe (they iterate, never index a
  fixed key). The `--no-patterns` stub carries `'variations': {}` (`main.py:934`), closing the
  one-path KeyError gap (#258/PAT-09). References passed to the exporter are inert both ways
  (`{}` from the pipeline `main.py:974`, detector-native from `run_export`) — noted latent
  inconsistency only if `references` is ever wired to affect output (forward-looking, not a
  finding).
- **Dim 2** — single parser both paths (`parser_fast`, `main.py:97`/`810`); no third parser
  reintroduced (`tracker/parser.py` referenced only by tests — tracked as #112, out of scope).
  `PATTERN_MIN/MAX_LENGTH` constants used at all three detector construction sites
  (`main.py:647-648`, `872`, `880`). `--no-patterns` stub stats schema matches the detectors'
  key set exactly. `compile` subcommand gives `prepare`→`compile` parity, sharing
  `_backup_existing_rom`/`_restore_backup` (#178/PL-05, #15).
- **Dim 3** — manual dispatch whitelist (`main.py:1324-1363`) covers exactly the argparse
  globals (`--version`, `--verbose/-v`, `--debug/-d`, `--arranger/-a`, `main.py:1138-1141`)
  plus `--no-patterns`/`--skip-validation`/`--config`/`--mapper`; unknown flags `sys.exit(2)`
  (`main.py:1358-1363`). `--version` prints + exits 0 both for bare argv (`main.py:1286-1288`)
  and combined-with-args (`main.py:1333-1339`). `--arranger` before a subcommand rejected
  (`main.py:1303-1308`). `--debug` reaches `run_prepare`'s `NESProjectBuilder`
  (`main.py:504`). No subcommand declares a flag its handler ignores (verified each
  `add_argument` against its `func=` body: `map` dropped `--config`, `detect-patterns`
  `--config` is consumed via `get_pattern_detection_caps`, `song add` dropped `--config`).
- **Dim 4** — `run_full_pipeline` is one try (`main.py:807`) / except (`main.py:1118`) /
  finally (`main.py:1126-1130`). DPCM pack is non-fatal-by-design and surfaced in the banner
  (`main.py:1108-1109`, #123). `validate_rom` returns `False` (fail-closed) on any
  diagnostics exception and prints unconditionally (`main.py:404-406`, #177/PL-04); boot-fatal
  vectors/APU checked before health (`main.py:408-417`, #6). CC65 nonzero → `compile_rom`
  `False` → `sys.exit(1)` in both paths (`main.py:1078-1080`, `main.py:472-474`). `run_prepare`
  covers raise and falsy-return (`main.py:508-515`, #15).
- **Dim 5** — final ROM written to the user path outside the `TemporaryDirectory`
  (`main.py:1078`). Both exporter write paths open `'w'` (truncate) before the step-by-step
  DPCM append (`exporter/exporter_ca65.py:897`, `:1306`), so the F-10/#23 double-write hazard
  stays closed.
- **Dim 6** — `Path('x.nes').with_suffix('.nes.backup')` behaves (last-dot replace); single
  `finally` restore covers all exit points (`main.py:1126-1130`, #26); backup unlinked on
  success (`main.py:1114-1116`, #29); `run_compile` mirrors it (`main.py:468`, `483-487`,
  #178/PL-05).
- **Dim 7** — `LARGE_FILE_THRESHOLD=10000` still print-only (`main.py:861-864`). Fallback uses
  `sample_events_for_detection` (uniform `np.linspace`) not a head-cut (`main.py:887`, #10);
  warning frames the loss as analysis-only, ROM unaffected (`main.py:889-894`, #176/PL-03).
  `run_detect_patterns` samples symmetrically (`main.py:661-664`, #21). Parallel/sequential
  caps intentionally differ (15000 vs 1000), both `--config`-overridable via one helper
  (#219). `was_sampled` now exposed on **both** detectors (#312), so the
  `if detector.was_sampled` check (`main.py:898`) is attribute-safe whether the parallel path
  or the sequential fallback ran.
- **Dim 8** — `nes/song_bank.py:11` imports `parse_midi_to_frames` from `tracker.parser_fast`
  (fixed #33/#34); no independent third parser. Song-bank→ROM remains a documented roadmap
  gap (F-13/#30), not a defect. `song add` defaults bank to `song_bank.json`;
  `list`/`remove` require a positional bank — asymmetric but each print/write targets the same
  resolved path, no silent cross-file write.

## Forward-looking notes (not findings)

- `validate_rom` gates boot-fatal only on `reset_vectors_valid` and `apu_pattern_count`
  (`main.py:409-412`); a different boot-fatal condition (e.g. an undetected PRG-bank overflow
  or mapper/`nes.cfg` mismatch) would have to surface through `overall_health`, which only
  rejects on `"ERROR"` (`main.py:424-426`) and otherwise warns. The capacity pre-flight
  (`check_mapper_capacity`, `main.py:336-354`) and `resolve_mapper`'s marker checks cover the
  known overflow/mismatch cases before link, so this is defense-in-depth latent risk, not a
  live gap — worth re-probing if a new boot-fatal class is introduced.
- `references` is passed with two different shapes at the two `export_tables_with_patterns`
  call sites (`{}` from the pipeline, detector-native from `run_export`). Both are inert today;
  a latent inconsistency only if `references` is ever made to affect output.

## Test health

`tests/test_main.py` (114), `tests/test_main_pipeline.py` + `tests/test_e2e_pipeline.py` (66):
**180/180 pass** at `308d712`.

## Suggested next step

Nothing to file — zero new findings. Optionally close #269 (functionally superseded by #297)
or leave it open for the cosmetic `'auto'`-in-`choices` follow-up.

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-07-18.md
```
