# Pipeline Integrity Audit — 2026-08-06

**Scope**: End-to-end `parse → map/arrange → frames → detect-patterns → export → prepare →
compile → validate` chain, per `.claude/commands/audit-pipeline/SKILL.md` Dimensions 1-8.
**Repo state audited**: commit `20f627e` (branch `fix/issues-136-137-167-202`).

## Summary

This is a re-audit following `docs/audits/AUDIT_PIPELINE_2026-08-05.md` (which audited
`3b16c5a` and found 0 new / 3 existing LOW findings). Four commits have landed since then,
three touching `main.py` (`5c61c30` #393, `89bdeb7` #371, `fe8c5b3` #380) and one touching it
plus `exporter_ca65.py`/`arranger/`/`dpcm_sampler/`/`tracker/pattern_detector.py`
(`24e51d2` #348/#355/#366/#367/#394, and today's `20f627e` #136/#137/#202).

Every `main.py` change since `3b16c5a` was diffed directly:
- `fe8c5b3`/#380 extracted the previously copy-pasted DPCM-packing block (in both `run_export`
  and `run_full_pipeline`) into one shared `pack_dpcm_into_asm`/`DpcmPackResult` helper
  (`main.py:104-216`). Both call sites (`main.py:706`, `main.py:1102`) now share identical
  warning text, "NO DRUMS" vs "PARTIAL DPCM MISS" labeling (#367/DP-DPCM-05), and
  `--verbose`-gated traceback printing. No behavior drift found between the two call sites.
- `89bdeb7`/#371 added `del midi_data` / `del mapped` in `run_full_pipeline` (`main.py:922`,
  `:930`, `:939`) purely for peak-memory reduction; confirmed by grep that neither name is
  referenced again after its `del` on either the arranger or legacy-mapper branch — no
  use-after-free/`NameError` risk introduced.
- `5c61c30`/#393 added an `__all__` list (`main.py:265-270`) to keep pyflakes happy about
  three re-exported `mappers.capacity` names; purely cosmetic, no runtime effect.
- `24e51d2`'s `main.py` slice is the same DPCM-labeling work folded into the `fe8c5b3` extraction
  (no separate `main.py` hunk beyond what's already described above).

The much larger `exporter/exporter_ca65.py` refactor (today's `20f627e`, #136: extracting 8
per-channel/per-table emitter methods out of the former ~750-line `export_direct_frames`) was
checked at the contract boundary only, per this skill's scope (internal exporter correctness is
`audit-exporters` territory): `export_tables_with_patterns(frames, patterns, references,
output_path, standalone=True, mapper=None)` (`exporter/exporter_ca65.py:1064`) and
`export_direct_frames(frames, output_path, standalone=True, mapper=None)`
(`exporter/exporter_ca65.py:603`) keep identical signatures, the `not patterns` dispatch
(`:1075-1076`) and the "references not consumed" contract (`:1071-1073`) are unchanged, and
both `main.py` call sites (`main.py:697`, `:1084`) pass the same argument shapes as before. No
contract break found from this refactor.

The `arranger/pipeline_integration.py` change (#329, Type-0/multi-channel track splitting by
MIDI channel before role analysis) and the `dpcm_sampler/enhanced_drum_mapper.py` /
`tracker/pattern_detector.py` changes (#202, #341, #366) are internal to arranger role-analysis
and drum-pattern-matching logic respectively; `arrange_for_nes`'s return shape (the
`{channel: {frame: {...}}}` structure `run_full_pipeline` hands to pattern detection/export)
and `assign_tracks_to_nes_channels`'s output shape are both unchanged, so neither affects any
Dimension-1 contract.

**Total findings this pass: 0 NEW / 3 Existing (all LOW, all still OPEN — re-confirmed present,
not re-filed).**

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 3 (`Existing: #377`, `#378`, `#379`) |

**Single most dangerous contract break**: none found.

**Does the step-by-step path produce the same ROM as the default path?** **Yes**, for ROM byte
content. Every frame byte in both paths derives from the same `frames` dict via
`export_tables_with_patterns`/`export_direct_frames`; `patterns` truthiness only selects which
serializer runs, and `references` is provably unconsumed (confirmed again against the refactored
exporter). The two paths can still diverge only in diagnostics text (`#378`) and in the inert
`references` shape passed to the exporter (`#379`), neither of which changes emitted bytes.

## Findings-per-Dimension

| Dimension | New findings | Existing (re-confirmed) |
|---|---|---|
| 1 — Stage JSON Contract Integrity | 0 | #377, #379 |
| 2 — `run_full_pipeline` vs step-by-step parity | 0 | — |
| 3 — Flag routing | 0 | — |
| 4 — Error propagation / fail-fast | 0 | — |
| 5 — Temp-file / intermediate handling | 0 | — |
| 6 — Backup & overwrite safety | 0 | — |
| 7 — Large-file threshold / fallback hand-off | 0 | #378 |
| 8 — Song-bank path | 0 | — |

## Contract Map

| Producer → Key(s) → Consumer | Verified matching |
|---|---|
| `run_parse` (`tracker/parser_fast.parse_midi_to_frames`) → `{"events":[...], "metadata":...}` → `run_map` (`load_json_stage(..., ['events'], 'parse')`, `main.py:228`) | ✓ |
| `run_map` (`assign_tracks_to_nes_channels`) → per-channel mapped events → `run_frames` (`load_json_stage(..., [], 'map')`, `main.py:248`) → `NESEmulatorCore.process_all_tracks` | ✓ (shape unchanged; known narrow guard gap, `#377`) |
| `run_frames` → `{channel: {frame: {...}}}` → `run_export`/`run_detect_patterns` (`load_json_stage(..., [], 'frames')`, `main.py:646`, `main.py:725`) | ✓ (same narrow guard gap, `#377`) |
| `run_detect_patterns`/parallel/sequential detectors → `{'patterns','references','stats'}` (+`'variations'` from detectors, still omitted by `detect-patterns`'s saved JSON, `main.py:759-763`) → `run_export`'s `--patterns` load (`main.py:660-667`) | ✓ (no consumer reads `variations`; open question, not a bug — unchanged) |
| `run_export`/`run_full_pipeline` → `CA65Exporter.export_tables_with_patterns(frames, patterns, references, output_path)` (`main.py:697`, `main.py:1084`; `exporter/exporter_ca65.py:1064`) | ✓ bytes; `references` shape diverges between call sites (`#379`) but is provably unconsumed (`exporter/exporter_ca65.py:1071-1073`) |
| `NESProjectBuilder.prepare_project` → `main.asm`/`music.asm`/`nes.cfg` + build scripts, mapper stamped into `nes.cfg` marker | ✓ |
| `compiler.compile_rom(project_dir, output_rom)` → validated `.nes`; `run_compile`/`run_full_pipeline` share `_backup_existing_rom`/`_restore_backup` (`main.py:475-504`) | ✓ |
| `pack_dpcm_into_asm(frames, asm_path)` (`main.py:126`) shared by `run_export` (`main.py:706`) and `run_full_pipeline` (`main.py:1102`) → appended DPCM asm block | ✓ (identical behavior at both call sites, confirmed post-#380 extraction) |

## Findings

### Existing: #377 — Wrong-stage JSON passes the `[]` required-keys guard and yields silent empty output
- **Severity**: LOW (re-confirmed, not re-scored)
- **Dimension**: 1 (Stage JSON Contract Integrity)
- **Both paths?**: Step-by-step subcommands only (`run_frames`, `run_export`, `run_detect_patterns`)
- **Location**: `main.py:248` (`run_map`'s `load_json_stage(..., [], 'map')` — actually
  `run_frames` reads `map`'s output), `main.py:646` (`run_export`), `main.py:725`
  (`run_detect_patterns`); `nes/emulator_core.py` `process_all_tracks` (only-if/elif channel
  dispatch, no `else`).
- **Status**: Existing: #377 (OPEN)
- **Description**: `load_json_stage(args.input, [], <stage>)` is called with an empty
  `required_keys` list at all three sites because each downstream stage's body only iterates
  the (all-optional) channel dict rather than indexing a fixed required key. A structurally
  valid but wrong-stage JSON file (e.g. handing `parse`'s output to `frames`) is therefore
  accepted and silently produces an empty/near-empty result with no diagnostic.
- **Evidence**: `grep -n "load_json_stage(args.input, \[\]" main.py` → lines 248, 646, 725,
  all passing `[]`.
- **Impact**: A user error in the step-by-step CLI (feeding the wrong intermediate JSON to a
  later subcommand) fails silently downstream instead of erroring immediately — confusing but
  not data-corrupting, since the eventual output is empty/near-empty rather than wrong.
- **Related**: `#120`/SAFE-01 (the `load_json_stage` guard itself, closed for the
  missing/corrupt/wrong-shape cases this narrower gap doesn't cover).
- **Suggested Fix**: Unchanged from prior audits — have each of these three call sites assert
  the loaded JSON contains at least one recognized channel key (or a stage-specific marker) so
  a wrong-stage file is rejected rather than silently accepted.

### Existing: #378 — Sequential-fallback sampling omits the "(lossy)" coverage suffix
- **Severity**: LOW
- **Dimension**: 7 (Large-File Threshold & Pattern-Detector Fallback Hand-off)
- **Both paths?**: Default `run_full_pipeline` only (sequential-fallback branch)
- **Location**: `main.py:994-1013` (outer `sample_events_for_detection` call at `:994`,
  `detector.was_sampled` check at `:1005`); `tracker/pattern_detector.py` (`was_sampled` set
  inside `detect_patterns`; `sample_events_for_detection` returns `was_sampled=False` when
  `len(events) <= max_events`).
- **Status**: Existing: #378 (OPEN)
- **Description**: `run_full_pipeline`'s fallback pre-samples `events` down to `max_events`
  (`main.py:994`) *before* calling `detector.detect_patterns(events)`. Inside
  `detect_patterns`, the detector's own internal `sample_events_for_detection` call sees
  `len(events) == max_events` and takes the `<=` branch, returning `was_sampled=False`. The
  success banner's coverage line (`main.py:1176`) keys off `detector.was_sampled`
  (`main.py:1005`), which therefore stays `False` even though the printed `coverage_ratio` was
  genuinely computed over a pre-sampled subset — only the separate `pattern_loss_warning`
  (driven by the correct outer `was_sampled` flag, `main.py:995-1002`) reflects the sampling.
- **Evidence**: `main.py:994` → `main.py:1005` — two different `was_sampled` flags from two
  different sampling calls, only one of which feeds the coverage-line qualifier.
- **Impact**: Cosmetic — the coverage-percentage line can omit its "(lossy)" qualifier on a
  large default-path song even though the number was computed over a subset. The correctly-
  flagged `pattern_loss_warning` still prints and still states "ROM content is unaffected", so
  no claim about ROM integrity is wrong — only the coverage line's own qualifier is missing.
- **Related**: `#176`/PL-03 (the warning message wording this coexists with, closed).
- **Suggested Fix**: Unchanged — thread the outer `was_sampled` flag (or an explicit
  "pre-sampled" marker) into the coverage-line's qualifier instead of relying solely on
  `detector.was_sampled`, which cannot observe sampling that already happened before the
  detector ran.

### Existing: #379 — Two export call sites pass divergent `references` shapes (latent, currently inert)
- **Severity**: LOW (forward-looking risk)
- **Dimension**: 1 (Stage JSON Contract Integrity)
- **Both paths?**: Divergence between the two paths (the finding itself)
- **Location**: `main.py:1084-1091` (`run_full_pipeline` passes literal `{}`) vs.
  `main.py:660-667`/`main.py:697` (`run_export` passes `pattern_data['references']`, the
  detector-native `{'pattern_id': [positions]}` shape); consumer
  `exporter/exporter_ca65.py:1071-1073` documents the parameter as unconsumed.
- **Status**: Existing: #379 (OPEN)
- **Description**: `run_full_pipeline` explicitly passes an empty dict for `references` with a
  comment justifying it ("the detector's pattern `references` are analysis/metrics only and
  are never read by `export_tables_with_patterns` (#4)... pass an empty references dict rather
  than building a table nothing consumes" — `main.py:1078-1082`), while `run_export` passes the
  detector's native shape straight through unmodified. Both are fully inert today.
- **Evidence**: `main.py:1084` (`{}`) vs. `main.py:666` (`references = pattern_data['references']`)
  then `main.py:697` passing that variable into `export_tables_with_patterns`.
- **Impact**: None today — `exporter_ca65.py` explicitly does not read `references`. Flagged
  purely as a forward-looking risk: if `references` is ever wired up to affect output, these
  two call sites would immediately diverge in behavior since they don't agree on shape.
- **Related**: `#4`/F-01 (the "references not consumed" documentation this depends on).
- **Suggested Fix**: Unchanged — no action needed while `references` stays unconsumed; if it's
  ever made load-bearing, normalize both call sites to the same shape first.

## Verify-the-Fix Confirmations (re-checked this pass, no findings)

- **D1 — `load_json_stage` guard (SAFE-01/#120)**: still fails clean with `[ERROR]` + exit 1 on
  missing/corrupt/wrong-shape JSON (`main.py:76-102`); the narrower `[]`-required-keys gap is
  `#377` above, not new.
- **D1 — `variations` omission in `detect-patterns` output**: `main.py:759-763` still saves only
  `patterns`/`references`/`stats`; no consumer reads `pattern_result['variations']`.
- **D2 — Parser parity**: only `tracker.parser_fast.parse_midi_to_frames` is imported anywhere
  in `main.py` (`run_parse` at `:218`, `run_full_pipeline` at `:903`) and in
  `nes/song_bank.py:11`/`:75`. No `tracker.parser` (full parser) import on any pipeline path.
- **D2 — Pattern-detector bound constants**: `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` still
  passed identically at every detector construction site (`run_detect_patterns`,
  `run_full_pipeline`'s parallel/fallback construction). The #366/#341 changes to
  `tracker/pattern_detector.py`/`dpcm_sampler/enhanced_drum_mapper.py` are pattern-*matching*
  and DPCM-sizing changes, not length-bound changes, and don't touch these constants.
- **D2 — `stats` schema**: the `--no-patterns` stub (`main.py:1020-1048`) still emits exactly
  the shared key set (`original_size`/`compressed_size`/`compression_ratio`/`unique_patterns`
  + `'variations': {}`), matching both detectors' real output shape.
- **D3 — Flag routing**: no changes to the `global_args` whitelist, `--version` short-circuit,
  `--arranger`-before-subcommand rejection, or `--debug`→`run_prepare` threading since
  `3b16c5a`; all previously re-verified as closed.
- **D4 — Fail-fast / restore**: `run_full_pipeline`'s single `try`/`except`/`finally` still
  routes every failure through `_restore_backup` exactly once; `validate_rom` (`main.py:506-547`)
  still fails closed (`False`) on a diagnostics-engine exception and treats bad vectors / zero
  APU-init patterns as fatal defects ahead of `overall_health`.
- **D4 — DPCM pack non-fatal warning (SAFE-04/#123, #367/DP-DPCM-05)**: now lives in one shared
  `pack_dpcm_into_asm` (`main.py:126-216`) called from both `run_export` (`:706`) and
  `run_full_pipeline` (`:1102`); "NO DRUMS" vs "PARTIAL DPCM MISS" labeling confirmed identical
  at both call sites (`main.py:717-718`, `main.py:1180-1182`).
- **D5 — Temp-dir / DPCM append**: `export_tables_with_patterns`/`export_direct_frames` still
  open `output_path` in `'w'` mode before any `'a'`-mode DPCM append (confirmed in the
  refactored `exporter_ca65.py`), so no cross-run duplicate-symbol accumulation is possible.
- **D5 — Memory hygiene (#371, new this pass)**: `del midi_data`/`del mapped` in
  `run_full_pipeline` (`main.py:922`, `:930`, `:939`) confirmed dead after deletion on both
  branches — no `NameError` risk, pure peak-memory improvement.
- **D6 — Backup/restore/cleanup**: `_backup_existing_rom`/`_restore_backup` (`main.py:475-504`)
  still shared verbatim by `run_full_pipeline` and `run_compile`; success path unlinks the
  backup, failure path restores or moves the unbootable ROM to `<name>.nes.failed`.
- **D7 — Sampling/truncation**: no `events[:N]` head-cut anywhere; both fallback paths use
  `sample_events_for_detection`'s uniform `np.linspace` sampling; caps remain distinct by
  design and both overridable via `--config` (`get_pattern_detection_caps`, `main.py:46-74`).
- **D8 — Song-bank parser**: `nes/song_bank.py` still imports and uses
  `tracker.parser_fast.parse_midi_to_frames` exclusively. `docs/ROADMAP.md` still lists
  "Song banks → ROM" as an open roadmap item, consistent with `SongBank` having no
  build/compile method — no doc-rot detected.

## Notes on Recent Non-`main.py` Changes (checked for contract impact only)

- `20f627e` (#136/#137/#202, today): `exporter/exporter_ca65.py`'s `export_direct_frames` was
  split into 8 per-channel/table emitter methods (`_emit_pulse_or_triangle_table`,
  `_emit_noise_table`, `_emit_dpcm_table`, `_emit_pulse1_proc`, `_emit_pulse2_proc`,
  `_emit_triangle_proc`, `_emit_noise_proc`, `_emit_dpcm_proc`). Both public entry-point
  signatures (`export_direct_frames`, `export_tables_with_patterns`) and the "references not
  consumed"/`not patterns` dispatch contracts are unchanged. `enhanced_drum_mapper.py`'s
  `use_advanced` threading fix (#202) and real-sample-size backfill (#341) affect DPCM
  event/sample-allocation *content* within the `frames['dpcm']` channel, not the channel's
  shape — no Dimension-1 impact; deeper correctness of these fixes is `audit-dpcm` territory.
- `24e51d2` (#348/#355/#366/#367/#394): `tracker/pattern_detector.py`'s drum-pattern matching
  loop fix (#366, non-overlapping window scan) changes which windows get classified as
  matches/variations within `DrumPatternDetector`, not any inter-stage JSON shape. No
  pipeline-contract impact.
- `90b4582`/#329 (already in `3b16c5a`, re-confirmed unaffected by later commits):
  `arranger/pipeline_integration.py`'s `_split_events_by_channel` splits Type-0/multi-channel
  MIDI tracks by channel before role analysis. `arrange_for_nes`'s return type/shape
  (`{channel: {frame: {...}}}`) is unchanged — confirmed by re-reading its final `return output`
  statement and the function signature.

## Next Step

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-08-06.md
```
