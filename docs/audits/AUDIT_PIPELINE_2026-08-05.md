# Pipeline Integrity Audit — 2026-08-05

**Scope**: End-to-end `parse → map/arrange → frames → detect-patterns → export → prepare →
compile → validate` chain, per `.claude/commands/audit-pipeline/SKILL.md` Dimensions 1-8.
**Repo state audited**: commit `3b16c5a` (branch `master`).

## Summary

This is a re-audit following `docs/audits/AUDIT_PIPELINE_2026-07-19.md`. `main.py` — the file
this skill's contracts hinge on — has **not changed since commit `36348ce`** (2026-07-19,
20:55), which is the same state the 2026-07-19 report already audited. The only pipeline-
adjacent change since then is `398891f` (fix #365, sequential pattern-selection gate in
`tracker/pattern_detector.py`), which its own commit message and code comments confirm is
round-trip- and export-neutral ("round-trip is unaffected... the exporter derives every byte
from frames, not references, #4") — verified directly against `exporter/exporter_ca65.py`
and found to have no impact on any inter-stage contract.

Every "verify-the-fix" item across all 8 dimensions was re-checked directly against current
line numbers and **holds** — no regressions found. The three findings from the 2026-07-19
report are still present in the code exactly as before and remain open on GitHub (`#377`,
`#378`, `#379`); no new findings were identified this pass.

**Total findings this pass: 0 NEW / 3 Existing (all LOW, all still OPEN — re-confirmed present, not re-filed).**

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 3 (all `Existing: #377`, `#378`, `#379`) |

**Single most dangerous contract break**: none found. The most notable *residual* risk is
still `#379` (two `export_tables_with_patterns` call sites pass divergent `references`
shapes), but it is explicitly inert today — `references` is documented as unconsumed by the
exporter (F-01/#4) — so it is a forward-looking risk, not a live break.

**Does the step-by-step path produce the same ROM as the default path?** **Yes**, for the
byte content of the ROM. Every frame byte in both paths derives from the same `frames` dict
via `export_tables_with_patterns`/`export_direct_frames`; `patterns` truthiness only selects
which serializer runs, and `references` is provably unconsumed. The two paths can diverge in
**diagnostics text only** (`#378`'s missing "(lossy)" coverage suffix on the default path's
sequential-fallback branch is default-path-only) and in mapper resolution robustness for
older/marker-less projects (already handled via `nes.cfg`'s stamped mapper marker, confirmed
working in `run_compile`). No byte-level divergence was found.

## Contract Map

| Producer → Key(s) → Consumer | Verified matching |
|---|---|
| `run_parse` (`tracker/parser_fast.parse_midi_to_frames`) → `{"events":[...], "metadata":...}` → `run_map` (`load_json_stage(..., ['events'], 'parse')`, `main.py:117`) | ✓ |
| `run_map` (`assign_tracks_to_nes_channels`) → per-channel mapped events → `run_frames` (`load_json_stage(..., [], 'map')`, `main.py:137`) → `NESEmulatorCore.process_all_tracks` | ✓ (shape unchanged; guard has the known narrow gap, see `#377`) |
| `run_frames` → `{channel: {frame: {...}}}` → `run_export`/`run_detect_patterns` (`load_json_stage(..., [], 'frames')`, `main.py:522`, `main.py:630`) | ✓ (same narrow guard gap, `#377`) |
| `run_detect_patterns`/parallel/sequential detectors → `{'patterns','references','stats'}` (+ `'variations'` from detectors, omitted by the `detect-patterns` subcommand's saved JSON, `main.py:668-672`) → `run_export`'s `--patterns` load (`load_json_stage(..., ['patterns','references'], 'detect-patterns')`, `main.py:530`) | ✓ (no consumer reads `variations`; open question, not a bug — unchanged from 07-19) |
| `run_export`/`run_full_pipeline` → `CA65Exporter.export_tables_with_patterns(frames, patterns, references, output_path)` | ✓ bytes; `references` shape diverges between call sites (`#379`) but is provably unconsumed |
| `NESProjectBuilder.prepare_project` → `main.asm`/`music.asm`/`nes.cfg` + build scripts, mapper stamped into `nes.cfg` marker | ✓ |
| `compiler.compile_rom(project_dir, output_rom)` → validated `.nes`; `run_compile`/`run_full_pipeline` share `_backup_existing_rom`/`_restore_backup` (`main.py:351-379`) | ✓ |

## Findings

### PIPE-2026-08-05 re-audit: no new findings

All three previously-reported issues were re-verified directly against the current source and
are still present, unchanged in substance (only their line numbers shifted slightly from the
07-19 report's citations, corrected below):

#### Existing: #377 — Wrong-stage JSON passes the `[]` required-keys guard and yields silent empty output
- **Severity**: LOW (per prior audit; re-confirmed, not re-scored)
- **Dimension**: 1 (Stage JSON Contract Integrity)
- **Both paths?**: Step-by-step subcommands only (`run_frames`, `run_export`, `run_detect_patterns`)
- **Location**: `main.py:137` (`run_frames`), `main.py:522` (`run_export`), `main.py:630`
  (`run_detect_patterns`); `nes/emulator_core.py` `process_all_tracks` (only-if/elif channel
  dispatch, no `else`).
- **Status**: Existing: #377 (OPEN)
- **Re-verification**: `load_json_stage(args.input, [], 'map'/'frames')` is called with an
  empty `required_keys` list at all three sites (confirmed at the line numbers above, which
  differ slightly from the 07-19 report's `main.py:565`/`main.py:673` — those had drifted;
  current numbers are accurate as of this commit). The gap is unchanged: a structurally-valid
  but wrong-stage JSON file (e.g. `parse` output handed to `frames`) is accepted and silently
  produces an empty/near-empty result with no diagnostic.

#### Existing: #378 — Sequential-fallback sampling omits the "(lossy)" coverage suffix
- **Severity**: LOW
- **Dimension**: 7 (Large-File Threshold & Pattern-Detector Fallback Hand-off)
- **Both paths?**: Default `run_full_pipeline` only (fallback branch)
- **Location**: `main.py:886-908` (outer `sample_events_for_detection` call at `main.py:887`,
  detector-internal check at `main.py:898`); `tracker/pattern_detector.py:222`
  (`self.was_sampled` set inside `detect_patterns`), `tracker/pattern_detector.py:35-36`
  (`sample_events_for_detection` returns `was_sampled=False` when `len(events) <= max_events`).
- **Status**: Existing: #378 (OPEN)
- **Re-verification**: Confirmed the mechanism still holds — `main.py:887` pre-samples
  `events` down to `max_events` *before* calling `detector.detect_patterns(events)`; inside
  `detect_patterns`, the internal `sample_events_for_detection` call (`pattern_detector.py:222`)
  sees `len(events) == max_events` and takes the `<=` branch, returning `was_sampled=False`.
  The success banner's coverage line (`main.py:1108-1110`) therefore keys off
  `detector.was_sampled` (`main.py:898`), which stays `False`, so `coverage_lossy_note` is
  never set even though the printed `coverage_ratio` genuinely was computed over a sampled
  subset. The separate `pattern_loss_warning` (driven by the outer, correct `was_sampled` flag)
  still prints and correctly states "ROM content is unaffected" — no misleading claim about ROM
  integrity, only the coverage line's parenthetical qualifier is missing.

#### Existing: #379 — Two export call sites pass divergent `references` shapes (latent, currently inert)
- **Severity**: LOW (forward-looking risk)
- **Dimension**: 1 (Stage JSON Contract Integrity)
- **Both paths?**: Divergence between the two paths (the finding itself)
- **Location**: `main.py:980` (`run_full_pipeline` passes literal `{}`) vs. `main.py:542`
  (`run_export` passes `pattern_data['references']`, the detector-native
  `{'pattern_id': [positions]}` shape); consumer `exporter/exporter_ca65.py:996` documents the
  parameter as unconsumed.
- **Status**: Existing: #379 (OPEN)
- **Re-verification**: Confirmed both call sites still diverge exactly as previously reported.
  `main.py:972-976`'s comment explicitly justifies the `{}` choice ("the detector's pattern
  `references` are analysis/metrics only and are never read by `export_tables_with_patterns`
  (#4)... pass an empty references dict rather than building a table nothing consumes"). Still
  fully inert today; flagged only because the skill explicitly asks to keep tracking it as a
  forward-looking risk should `references` ever become load-bearing.

## Verify-the-Fix Confirmations (re-checked this pass, no findings)

- **D1 — `load_json_stage` guard (SAFE-01/#120)**: still fails clean with `[ERROR]` + exit 1 on
  missing/corrupt/wrong-shape JSON (`main.py:75-104`); the narrower `[]`-required-keys gap is
  `#377` above, not a new issue.
- **D1 — `variations` omission in `detect-patterns` output**: `main.py:668-672` still saves
  only `patterns`/`references`/`stats`; confirmed no consumer (`run_export`,
  `CA65Exporter.export_tables_with_patterns`) reads `pattern_result['variations']`. Still an
  open question per the skill, not a bug.
- **D2 — Parser parity**: only `tracker.parser_fast.parse_midi_to_frames` is imported anywhere
  in `main.py` (`main.py:108`, `main.py:...` inside `run_full_pipeline`) and in
  `nes/song_bank.py:11` (song-bank ingestion). No `tracker.parser` (full parser) import found
  on any pipeline path.
- **D2 — Pattern-detector bound constants**: `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` are
  passed explicitly and identically to every detector construction site
  (`main.py:872`, `main.py:880`, and `run_detect_patterns`'s construction); the #365 fix to
  `tracker/pattern_detector.py`'s internal `MIN_PATTERN_OCCURRENCES` gate is a
  pattern-*selection* change, not a length-bound change, and does not touch these constants.
- **D2 — `stats` schema**: the `--no-patterns` stub (`main.py:924-941`) still emits exactly the
  shared key set (`original_size`/`compressed_size`/`compression_ratio`/`unique_patterns`/
  `total_events`/`patterned_events`/`coverage_ratio`) plus `'variations': {}`, matching both
  detectors' real output shape.
- **D3 — Unknown-flag rejection**: the manual `global_args` loop still `sys.exit(2)`s on any
  unrecognized `-`-prefixed token (`main.py:1364-1369`); whitelist covers `--verbose/-v`,
  `--debug/-d`, `--arranger/-a`, `--version`, `--no-patterns`, `--skip-validation`, `--config`,
  `--mapper` — a superset of the argparse-declared top-level globals
  (`--version`/`--verbose`/`--debug`/`--arranger`, `main.py:1144-1147`). No drift.
- **D3 — `--version` combined with other args**: still short-circuits with `sys.exit(0)`
  immediately inside the manual loop (`main.py:1339-1345`), matching argparse's
  `action='version'` semantics; the `len(sys.argv)==2` fast path (`main.py:1292-1294`) is
  unchanged.
- **D3 — `--arranger` before a subcommand**: still rejected with `sys.exit(2)` and a clear
  message (`main.py:1303-1314`).
- **D3 — `--debug` → `run_prepare` parity**: `debug_mode=getattr(args, 'debug', False)` still
  threaded into `NESProjectBuilder` in `run_prepare`, matching the default path.
- **D4 — Fail-fast / restore**: `run_full_pipeline`'s single `try`/`except`/`finally`
  (`main.py:1124-1136`) still routes every failure through `_restore_backup` exactly once;
  `validate_rom` still fails closed (`False`) on a diagnostics-engine exception and treats bad
  vectors / zero APU-init patterns as fatal defects ahead of `overall_health`
  (`main.py:402-409`).
- **D5 — Temp-dir / DPCM append**: `export_tables_with_patterns` still opens `output_path` in
  `'w'` mode (`exporter/exporter_ca65.py:928`, `:1357`) before any `'a'`-mode DPCM append, so
  no cross-run duplicate-symbol accumulation is possible.
- **D6 — Backup/restore/cleanup**: `_backup_existing_rom`/`_restore_backup`
  (`main.py:351-379`) are shared verbatim by `run_full_pipeline` and `run_compile`
  (`main.py:462-481`); success path unlinks the backup, failure path restores or moves the
  unbootable ROM to `<name>.nes.failed`. No divergence between the two entry points.
- **D7 — Sampling/truncation**: no `events[:N]` head-cut anywhere; both fallback paths use
  `sample_events_for_detection`'s uniform `np.linspace` sampling. The two caps
  (`MAX_PATTERN_EVENTS=15000` parallel, `DETECTOR_MAX_EVENTS=1000` sequential/fallback) remain
  distinct by design and both are overridable in lockstep via `--config`
  (`get_pattern_detection_caps`, `main.py:39-73`).
- **D8 — Song-bank parser**: `nes/song_bank.py` still imports and uses
  `tracker.parser_fast.parse_midi_to_frames` exclusively (line 11, line 75). `docs/ROADMAP.md`
  still lists "Song banks → ROM" as an open roadmap item, consistent with `SongBank` having no
  build/compile method — no doc-rot detected.

## Notes on Recent Non-`main.py` Changes

- `398891f` (fix #365, `tracker/pattern_detector.py`): tightens the sequential detector's
  pattern-selection gate to require ≥3 *exact* occurrences (not just exact+variation combined),
  preventing a degenerate 0%-compression pattern from blocking a genuinely-repeating shorter
  one. This only affects `pattern_result['patterns']`/`stats`/`compression_ratio` values, not
  any inter-stage JSON shape or the exporter's byte output (which never reads `references`).
  No pipeline-contract impact.
- `36348ce` (fix #361/#362/#363, mapper-capacity refactor): already reflected in the code
  audited both here and in the 2026-07-19 report (that report was authored after this commit
  landed). `resolve_mapper`, `enforce_direct_export_dpcm_mapper`, and the `nes.cfg`
  mapper-marker recovery in `run_compile` were spot-checked this pass and remain internally
  consistent — no new pipeline-dimension finding (deeper mapper-capacity correctness is
  `audit-mappers` territory, not re-litigated here).

## Next Step

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-08-05.md
```
