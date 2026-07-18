# Pipeline Integrity Audit — 2026-07-18 (re-audit / verify-the-fix pass)

Scope: end-to-end conversion chain (parse → map/arrange → frames → detect-patterns →
export → prepare → compile → validate) audited as a contract-bound system per
`.claude/commands/audit-pipeline/SKILL.md`, all 8 dimensions. HEAD = `b562e1d`
(branch `fix/audit-167-88-91`; tip after PR #307 "sync audit skills to current code",
`04b3a8c` safety/tech-debt/tempo audits, and the merged fixes for #295/#296 (DPCM length
ceiling + arranger false-chord merge), #259/#260 (tempo-map unification), #297 (compile
mapper recovery from `nes.cfg`), #298 (clamp reporting), and #92/#97/#98 (arpeggio
patterns + tempo-map doc notes)).

**Dedup**: `/tmp/audit/issues.json` (27 OPEN issues, `gh issue list ... --limit 200`,
default state filter = open only) plus every prior `docs/audits/AUDIT_PIPELINE_*.md` —
most recently `AUDIT_PIPELINE_2026-07-06.md`, whose sole open item (PL-08/#269, LOW)
is **re-verified as functionally resolved** below by commit `452d5b2` (#297), landed
after the 07-06 pass. PL-03..PL-07/PL-09 stay fixed; no regressions found.

## Summary

**Zero NEW findings. Zero CRITICAL / HIGH / MEDIUM.** One pre-existing LOW item
(PL-08/#269) remains technically open on the issue tracker but its functional impact
is now closed by #297 (see below) — the workflow it complained about (`prepare --mapper
auto` having no matching `compile` invocation) now works with **no** `--mapper` flag
at all, since `compile` recovers the mapper `prepare` used directly from `nes.cfg`.
All 8 dimensions pass; the two entry points (`run_full_pipeline` vs. the step-by-step
subcommand chain) were live-reproduced to emit a **byte-identical ROM** for the same
input (see below).

Finding counts per dimension:
- Dimension 1 (Stage JSON/artifact contract): 0 new. No regression.
- Dimension 2 (`run_full_pipeline` vs step-by-step parity): 0 new. PL-08/#269 (LOW)
  technically open, functionally superseded by #297.
- Dimension 3 (flag routing): 0 new. Whitelist still in sync with argparse globals.
- Dimension 4 (error propagation / fail-fast): 0 new. Live-reproduced correct
  fail-fast on an oversized direct-export + DPCM + MMC3-forced build (see notes).
- Dimension 5 (temp-file / intermediates): 0 new.
- Dimension 6 (backup & overwrite): 0 new.
- Dimension 7 (large-file threshold / detector fallback): 0 new.
- Dimension 8 (song-bank path): 0 new (known roadmap gap only, F-13/#30;
  `parser_fast` usage confirmed unchanged).

`tests/test_main.py` + `tests/test_main_pipeline.py` + `tests/test_mappers.py`:
**206/206 pass** at HEAD.

### Single most dangerous open item
None at HIGH/CRITICAL. The mildest surviving item is **PL-08/#269 (LOW, Existing)** —
`compile --mapper` still has no `'auto'` in its argparse `choices` — but this is now
cosmetic: `run_compile` (`main.py:460-461`) reads the mapper `prepare` actually used
from a marker `NESProjectBuilder` stamps into `nes.cfg` (`NES_CFG_MAPPER_MARKER`,
`nes/project_builder.py`) and only falls back to `--mapper`'s default for older,
marker-less projects. A `prepare --mapper auto` project now compiles correctly with a
bare `python main.py compile <dir> <out.nes>` — no `--mapper` needed, and passing an
explicit wrong one is still caught by `resolve_mapper`'s bytecode/bank-pack marker
checks. Recommend closing #269 once `'auto'` is (optionally) added to the choices list
for symmetry, but the functional gap it tracked is gone.

### Does the step-by-step path produce the same ROM as the default path?
**Yes — live-reproduced byte-identical.** Ran both paths against `input.mid`
(21,068 events, one DPCM sample) with default settings:

```
$ python main.py input.mid /tmp/.../full.nes
$ python main.py parse ... && map ... && frames ... && detect-patterns ... \
    && export ... && prepare ... --mapper auto && compile ... /tmp/.../step.nes
$ cmp /tmp/.../full.nes /tmp/.../step.nes
IDENTICAL   (both 524,304 bytes)
```

This holds even though the two runs' pattern detectors saw different data (the
default path's parallel detector sampled 21,068→15,000 events and found 206 patterns;
the step-by-step sequential detector sampled to 1,000 events and found far fewer) —
confirming CLAUDE.md's documented contract that `patterns`/`references` are
compression-analysis metrics only and every emitted byte derives from `frames`
(`exporter/exporter_ca65.py:962-971`).

## Contract Map

| Stage boundary | Producer (fn → key(s)) | Consumer (fn) | Verified |
|---|---|---|:--:|
| parse → map | `parser_fast.parse_midi_to_frames` → `{"events","metadata"}` | `run_map` reads `["events"]` via `load_json_stage` guard (`main.py:106`) | ✓ |
| map → frames | `assign_tracks_to_nes_channels(events, dpcm_index)` → per-channel dict | `NESEmulatorCore.process_all_tracks` (`run_frames`, `main.py:114-121`) | ✓ |
| arrange → frames | `arrange_for_nes(events, arp_speed, verbose)` → `{channel:{frame:{...}}}` | exporter/detector flatten via shared `frames_to_events` | ✓ |
| frames → detect | `{channel:{frame:{note,volume,...}}}` | `frames_to_events` (both entry points identical) | ✓ |
| detect → export | `{patterns, references, stats}` (`run_detect_patterns` writes 3 keys; `variations` dropped) | `run_export` reads only `patterns`/`references` (`main.py:547`) — safe, unread elsewhere | ✓ |
| stats → banner | `compression_ratio`/`coverage_ratio`/`total_events`/… (identical both detectors + `--no-patterns` stub) | success banner + subcommand print | ✓ |
| export → prepare (mapper choice, direct) | direct-export `music.asm` bank-packed for a mapper stamps `; Direct export bank-packed for <name>` (`exporter_ca65.py:206-207`) | `resolve_mapper` via `_direct_export_packed_mapper_name` (`main.py:192-215`) raises on mismatch | ✓ |
| export → prepare (bytecode) | MMC3 macro-bytecode `music.asm` marker comment | `resolve_mapper`'s `_requires_mmc3_bytecode_engine` forces/validates MMC3 | ✓ |
| prepare → nes.cfg | `NESProjectBuilder` stamps `NES_CFG_MAPPER_MARKER + mapper.name` as nes.cfg's first line | `_prepared_mapper_name_from_cfg` (`main.py:218-234`) | ✓ **new since 07-06, confirmed working** |
| prepare → compile | project dir (+ recovered mapper) | `resolve_mapper` re-validated against project's own `music.asm`; exact PRG-size check; CC65 nonzero → `CompilationError` → `False` → `sys.exit(1)` | ✓ |
| compile → validate | `.nes` | `validate_rom` — boot-fatal on bad vectors / zero APU init; diagnostics-engine failure → `False` | ✓ |
| `--config` → caps | CLI path → `get_pattern_detection_caps` → `ConfigManager` | sampling caps; missing path errors + exit 1 | ✓ |

## Findings

No NEW findings this pass.

## Verified-fixed / re-confirmed since the previous pass (`8308a63` → `b562e1d`)

- **PL-08/#269 (LOW, was OPEN)** — **functionally resolved** by commit `452d5b2`
  (fix: recover the prepared mapper from nes.cfg in compile, #297). `NESProjectBuilder`
  now writes `# midi2nes-mapper: <name>` as the first line of `nes.cfg`
  (`nes/project_builder.py`, `NES_CFG_MAPPER_MARKER`); `run_compile` reads it back via
  `_prepared_mapper_name_from_cfg` (`main.py:218-234`) and uses it in preference to
  `--mapper`'s CLI default (`main.py:460-461`: `cfg_mapper = _prepared_mapper_name_from_cfg(...); mapper_choice = cfg_mapper if cfg_mapper else get_mapper_choice(args)`).
  This closes the *functional* gap #269 described — a `prepare --mapper auto` project
  (which can resolve to NROM/MMC1/MMC3) now has a working `compile` invocation with no
  flag at all, not just a loud rejection. The narrower literal ask (add `'auto'` to
  `compile --mapper`'s argparse `choices`, `main.py:1198`) is still not done, so #269
  can stay open as a cosmetic follow-up, but it is no longer the "dangerous half" the
  06-29→07-06 audits tracked (that was PL-09/#285, already closed).
  **Live-reproduced fixed** (see "Does the step-by-step path produce the same ROM"
  above): `prepare --mapper auto` → bare `compile` (no `--mapper`) succeeded and
  produced a ROM byte-identical to the default pipeline's.

- **PL-01..PL-07, PL-09 (#174-#179, #267, #283/#285)**: all re-confirmed unchanged —
  no code touching flag routing, backup/restore, temp-file handling, or the
  bank-pack/bytecode markers was touched since 07-06. Spot-read every referenced
  `main.py` line range; all match the 07-06 audit's description verbatim.

- **Tempo-map unification (#259/#260, commit `53a8d19`)**: `tracker/parser_fast.py`'s
  `parse_midi_to_frames` and `parse_midi_to_frames_with_analysis` now share a single
  `_build_tempo_map(mid, config)` helper. Confirmed this did **not** change
  `parse_midi_to_frames`'s return shape — still exactly `{"events": ..., "metadata": {}}`
  (`tracker/parser_fast.py:172-175`) — so the parse→map contract is untouched.
  `parse_midi_to_frames_with_analysis` is not on the `main.py` pipeline path (only
  `nes/song_bank.py` calls the plain `parse_midi_to_frames`), so this fix has no
  pipeline-contract surface even though it changes analysis-path internals.

- **DPCM length-register ceiling + arranger false-chord fix (#295/#296, commit
  `d392ef6`)**: touches `dpcm_sampler/dpcm_packer.py` and
  `arranger/pipeline_integration.py` internals only — no change to the `frames` dict
  shape the arranger hands downstream, or to the DPCM packer's public
  `generate_assembly()`/bank-count contract that `run_full_pipeline`/`run_export`
  consume. Confirmed via `git show --stat`; no `main.py` changes in this commit.

- **Clamped-note reporting (#298, commit `c1b52d9`)**: added a `self.notes_clamped`
  counter and an end-of-export print inside `CA65Exporter.export_tables_with_patterns`.
  Confirmed the method's signature is unchanged
  (`export_tables_with_patterns(self, frames, patterns, references, output_path,
  standalone=True, mapper=None)`) — both `main.py` call sites (`run_export`,
  `run_full_pipeline`) still call it identically; no contract break.

## Dimension notes (verify-the-fix confirmations, no findings)

- **Dim 1**: `run_detect_patterns` (`main.py:670-674`) still saves only
  `{patterns, references, stats}`, dropping `variations`. Confirmed still safe —
  `run_export` reads only `pattern_data['patterns']`/`['references']`
  (`main.py:547`); `variations`/`stats` are never read downstream.
- **Dim 2**: shared constants `PATTERN_MIN_LENGTH=3`/`PATTERN_MAX_LENGTH=12`
  (`main.py:36-37`) still the only values used by both `run_detect_patterns`
  (`main.py:647-648`) and `run_full_pipeline`'s parallel/fallback detectors
  (`main.py:862,870`). `EnhancedPatternDetector`'s constructor defaults
  (`min_pattern_length=3, max_pattern_length=32`, `tracker/pattern_detector.py:383`)
  are never reached — every real call site overrides both explicitly. No drift.
- **Dim 3**: manual dispatch whitelist (`main.py:1296-1339`) still covers exactly
  `--verbose/-v`, `--debug/-d`, `--arranger/-a`, `--version`, `--no-patterns`,
  `--skip-validation`, `--config <path>`, `--mapper <choice>`; unknown flags still
  `sys.exit(2)`. Live-reproduced: `--mapper bogus` → clean exit 2 message;
  `--version input.mid out.nes` → prints version, exits 0, does not run the pipeline;
  a nonexistent input MIDI → `[ERROR] Input MIDI file not found: ...`, exit 1.
- **Dim 4**: fail-fast gate live-reproduced on a real oversized case:
  `python main.py --no-patterns --mapper auto input.mid out.nes` correctly aborts at
  the `prepare` capacity pre-flight (`check_mapper_capacity`, `main.py:346-354`) with
  `[ERROR] Music data does not fit the MMC3 PRG layout: fixed-bank data (173,723 bytes)
  exceeds the MMC3 PRG_FIX budget (~6,138 bytes)` — no ROM is written, and the message
  correctly attributes the cause (`enforce_direct_export_dpcm_mapper` forces MMC3
  because this song's DPCM trigger code is MMC3-register-only, and MMC3's direct-export
  path has no bank-switching, unlike MMC1's) with an accurate workaround ("enable
  pattern compression or shorten the song"). This is the pre-flight gate (#11/#126/#127)
  working as designed, not a new defect — no ROM left at the output path, clear
  message, real workaround exists (drop `--no-patterns`).
- **Dim 5/6**: unchanged; re-read `main.py:1071-1076` (single `finally` restore),
  `main.py:1059-1061` (backup cleanup on success), `run_compile`'s mirrored
  `_backup_existing_rom`/`_restore_backup` — all match 07-06 description exactly.
- **Dim 7**: fallback still uses `sample_events_for_detection` (uniform `np.linspace`),
  live-reproduced in both the default-path run (21,068→15,000, parallel detector
  succeeded, no fallback needed) and the step-by-step run
  (`⚠️ Large file (21068 events): sampled to 1000 (4.7%, lossy) before pattern
  detection`) — both messages correctly frame the loss as analysis-only.
- **Dim 8**: `nes/song_bank.py:11` still imports `parse_midi_to_frames` from
  `tracker.parser_fast` (not the tempo-map-unification-touched
  `parse_midi_to_frames_with_analysis`, which remains unused by the pipeline). No
  doc-rot drift against `docs/ROADMAP.md`'s stated "song build" gap.

## Suggested next step

Nothing to file — zero new findings. Optionally close #269 (functionally resolved by
#297) or leave it open for the small cosmetic follow-up (add `'auto'` to
`compile --mapper`'s choices, routed through the same `nes.cfg` recovery path already
in place).

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-07-18.md
```
