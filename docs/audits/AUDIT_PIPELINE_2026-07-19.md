# Pipeline Integrity Audit — 2026-07-19

**Scope:** End-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) audited as a contract-bound system: inter-stage data
contracts, `run_full_pipeline` vs step-by-step parity, flag routing, fail-fast/no-broken-ROM,
temp-file handling, backup/overwrite safety, large-file fallback hand-off, and the song-bank path.

This was a **verify-the-fix** pass: the large historical batch (F-01..F-13, SAFE-01/04,
PL-01..PL-09) is fixed. Every fix in scope was re-confirmed against the live code. No
regressions found. Three new LOW-severity/forward-looking items are reported.

## 1. Summary

| Dimension | Findings |
|-----------|----------|
| 1. Stage JSON contract integrity | 1 (LOW) |
| 2. Full-pipeline vs step-by-step parity | 0 |
| 3. Flag routing | 0 |
| 4. Error propagation / fail-fast | 0 |
| 5. Temp-file / intermediate handling | 0 |
| 6. Backup & overwrite safety | 0 |
| 7. Large-file threshold & detector fallback | 1 (LOW) |
| 8. Song-bank path | 0 |
| Cross-cutting (latent/forward-looking) | 1 (LOW) |
| **Total** | **3 (0 CRITICAL / 0 HIGH / 0 MEDIUM / 3 LOW)** |

**Most dangerous contract break:** None found. The most notable residual is a defense-in-depth
gap (PIPE-2026-07-19-1): the `frames`/`export`/`detect-patterns` subcommands pass an empty
`required_keys` list to `load_json_stage`, so a *wrong-stage* JSON (e.g. a `parse`-stage file
handed to `frames`) passes the guard and `process_all_tracks` silently returns an empty frames
dict — no crash, no diagnostic. This is only reachable by user misuse on the debug path; the
correct producer (`map`) always emits recognized channel keys, so the happy path is intact.

**Does the step-by-step path produce the same ROM as the default path? YES.** Both entry points
now import `parse_midi_to_frames` from `tracker/parser_fast.py` (`main.py:108`, `main.py:851`);
both use the shared `PATTERN_MIN_LENGTH=3`/`PATTERN_MAX_LENGTH=12` constants (`constants.py:9-10`)
at every call site; both drive the same `CA65Exporter.export_tables_with_patterns`; both resolve
the mapper through `resolve_mapper`; and both run the shared `validate_rom` gate. The only
default-only capability is `--arranger`, which is intentionally rejected before a subcommand
(`main.py:1352-1357`, #174) rather than silently discarded.

## 2. Contract Map

| Stage boundary | Producer → key(s) → consumer | Verified |
|----------------|------------------------------|:--------:|
| parse → map | `run_parse` writes `{events, metadata}` → `run_map` reads `load_json_stage(input,['events'],'parse')` (`main.py:117`) then indexes `["events"]` (`main.py:130`) | ✓ |
| map → frames | `assign_tracks_to_nes_channels` → channel dict → `NESEmulatorCore.process_all_tracks` (`main.py:137-139`) | ✓ |
| frames → detect-patterns | `process_all_tracks` frames dict → `frames_to_events` → `EnhancedPatternDetector` (`main.py:673-708`) | ✓ |
| frames → export | frames dict → `CA65Exporter.export_tables_with_patterns(frames, patterns, references, out)` (`main.py:616-623`) | ✓ |
| detect-patterns → export | `run_detect_patterns` writes `{patterns, references, stats}` (`main.py:711-716`) → `run_export` reads `['patterns','references']` (`main.py:573`), uses `pattern_data['patterns']`/`['references']` only | ✓ (`variations`/`stats` never read by export) |
| export → prepare | `music.asm` → `NESProjectBuilder.prepare_project` (`main.py:541-546`) | ✓ |
| prepare → compile | `nes.cfg` mapper marker → `_prepared_mapper_name_from_cfg` → `resolve_mapper` (`main.py:497-500`) | ✓ |
| compile → validate | `compile_rom` → `validate_rom` boot-fatal gate (`main.py:513-516`) | ✓ |

## 3. Findings

### PIPE-2026-07-19-1: Wrong-stage JSON passes the `[]` required-keys guard and yields silent empty output
- **Severity**: LOW
- **Dimension**: 1 (Stage JSON Contract Integrity)
- **Both paths?**: Step-by-step only (the default path never writes/reads these intermediates).
- **Location**: `main.py:137` (`run_frames`), `main.py:565` (`run_export`), `main.py:673`
  (`run_detect_patterns`); `nes/emulator_core.py:124-243` (`process_all_tracks`).
- **Status**: NEW
- **Description**: `run_frames`, `run_export`, and `run_detect_patterns` call
  `load_json_stage(args.input, [], 'map'/'frames')` with an empty `required_keys` list because
  the mapped/frames channel dict has no fixed key. The guard therefore only catches
  missing/corrupt/non-object files, not a structurally-valid file from the *wrong* stage. If a
  user hands `parse`-stage JSON (`{"events":[...], "metadata":...}`) to `frames`,
  `process_all_tracks` iterates its keys, matches none of `pulse1/pulse2/triangle/noise/dpcm`
  (there is no `else` branch — `nes/emulator_core.py:128,135,181`), and returns an empty
  `processed` dict. The pipeline then writes an empty frames file and continues with no warning.
- **Evidence**: `process_all_tracks` has only `if/elif` arms for the five known channels and
  `return processed` (`nes/emulator_core.py:243`); an unrecognized key is silently skipped. The
  skill's Dimension 1 explicitly leaves this as an open question ("confirm that's genuinely safe
  rather than a gap in the guard") — it is a real, if narrow, gap.
- **Impact**: Debug-path ergonomics only. A mistyped stage produces an empty/near-empty ROM with
  zero diagnostics instead of a clear "wrong stage" error. The correct producer always emits
  channel keys, so no happy-path breakage; not reachable from the default pipeline.
- **Related**: SAFE-01/#120 (the guard this extends); Dimension 1 open question in the skill.
- **Suggested Fix**: In `run_frames`/`run_export`/`run_detect_patterns`, after load, assert the
  dict contains at least one recognized channel key (intersect keys with the known channel set)
  and exit 1 with a "does not look like <stage> output" message when it does not.

### PIPE-2026-07-19-2: Sequential-fallback sampling omits the "(lossy)" coverage suffix
- **Severity**: LOW
- **Dimension**: 7 (Large-File Threshold & Pattern-Detector Fallback Hand-off)
- **Both paths?**: Default `run_full_pipeline` only (fallback branch).
- **Location**: `main.py:929-950` (fallback sampling + `if detector.was_sampled:` at `main.py:941`).
- **Status**: NEW
- **Description**: When parallel detection raises and the sequential fallback fires, the events
  are pre-sampled to `max_events` at `main.py:930` before being passed to
  `EnhancedPatternDetector.detect_patterns`, which re-runs `sample_events_for_detection`
  internally (`tracker/pattern_detector.py:211`). Because the list is already at the cap, the
  detector's own `self.was_sampled` stays `False`. The subsequent `if detector.was_sampled:`
  check (`main.py:941`) therefore leaves `coverage_lossy_note` empty, so the success banner's
  "Pattern coverage" line is printed *without* the "(lossy — measured over the sampled subset)"
  qualifier even though the coverage number genuinely was computed over a sampled subset.
- **Evidence**: Outer sampling sets a local `was_sampled` (`main.py:930`) that drives
  `pattern_loss_warning`, but the coverage suffix keys off `detector.was_sampled`, a different
  flag that reflects only the detector's *internal* (now no-op) sampling.
- **Impact**: Cosmetic. The prominent `pattern_loss_warning` ("compression stats are
  approximate; ROM content is unaffected") still prints, so the user is not misled about ROM
  integrity — only the coverage line's parenthetical is missing. No effect on ROM bytes.
- **Related**: #312/PAT-11 (coverage labeling), #176/PL-03.
- **Suggested Fix**: Drive `coverage_lossy_note` off the local `was_sampled` (OR it with
  `detector.was_sampled`) in the fallback branch, mirroring how `pattern_loss_warning` is set.

### PIPE-2026-07-19-3: Two export call sites pass divergent `references` shapes (latent, currently inert)
- **Severity**: LOW (forward-looking risk)
- **Dimension**: 1 (Stage JSON Contract Integrity)
- **Both paths?**: Divergence between the two paths (the finding itself).
- **Location**: `main.py:1023` (`run_full_pipeline` passes `{}`) vs `main.py:619` (`run_export`
  passes detector-native `references`); consumer `exporter/exporter_ca65.py:965-973`.
- **Status**: NEW
- **Description**: `run_full_pipeline` passes a bare empty dict `{}` for the `references`
  argument regardless of what pattern detection produced, while the step-by-step `run_export`
  passes the detector's native `{'pattern_id': [positions]}` shape through unmodified. Today this
  is completely inert: `export_tables_with_patterns` documents that `references` is **not
  consumed** (`exporter/exporter_ca65.py:972-973`, F-01/#4, confirmed intentional per CLAUDE.md).
  So there is no live mismatch. The risk is purely forward-looking.
- **Evidence**: `main.py:1020-1027` passes literal `{}`; `main.py:616-623` passes
  `pattern_data['references']`.
- **Impact**: None currently. If `references` is ever wired up to affect output bytes, the two
  entry points would diverge (default path would have no references data; step-by-step would),
  breaking the "same ROM from both paths" guarantee. Flagged per the skill's explicit request.
- **Related**: F-01/#4 (references intentionally unused).
- **Suggested Fix**: If/when `references` becomes load-bearing, unify both call sites on one
  shape (or have both derive it from `pattern_result`). No action needed while it stays inert;
  a comment at `main.py:1023` already notes the empty-dict choice.

## Verify-the-Fix Confirmations (no findings)

- **Parser parity (D2):** No `tracker.parser` import in `main.py`; both entries use
  `parser_fast`. Song-bank ingestion also uses `parser_fast` (`nes/song_bank.py`).
- **Pattern-bound drift (D2):** `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` sourced from
  `constants.py`; every `main.py` call site passes them explicitly. The constructor defaults
  (`min=3,max=32` etc.) in `tracker/pattern_detector*.py` are never reached from the pipeline.
- **Truncation-to-2000 (D7, F-04):** No `events[:2000]`/`events[:1000]` head-cut anywhere;
  fallback uses `sample_events_for_detection` (uniform `np.linspace`). Both detectors expose
  `was_sampled`, so `main.py:941` cannot `AttributeError`.
- **Flag routing (D3):** Manual `global_args` loop rejects unknown flags with `exit(2)`
  (`main.py:1407-1412`); `--version` prints and exits inside the loop (`main.py:1382-1388`) and
  via argparse in both short-circuit forms; `--config`/`--mapper` are validated and threaded
  into `SimpleArgs`. Whitelist is a superset of the argparse-declared globals.
- **Fail-fast / restore (D4/D6):** `run_full_pipeline` has a single `try/except/finally`;
  `_restore_backup` runs in `finally` on every `sys.exit(1)` and on the top-level exception;
  backup is unlinked only on success (`main.py:1163-1165`). `run_compile` shares the same
  helpers with a `finally` restore. `validate_rom` fails **closed** (returns `False`) on a
  diagnostics-engine exception (`main.py:441-443`) and treats bad vectors / no-APU-init as
  fatal defects before consulting health (`main.py:445-454`).
- **Exporter truncate (D5, F-10):** `export_tables_with_patterns` opens the output with `'w'`
  (`exporter/exporter_ca65.py:897,1326`), so the post-export `'a'` DPCM append cannot accumulate
  duplicate symbols across re-runs.
- **`references` unused (D1, F-01):** Confirmed not consumed by the exporter.

## Next Step

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-07-19.md
```
