# Safety & Robustness Audit — 2026-08-06

Scope: the **Python layer** — error handling, malformed-input resilience, subprocess/CC65
safety, unsafe deserialization, inter-stage JSON guards, file/resource handling, exception-type
discipline, and partial-output-on-failure. This is not a NES-hardware audit.

Base commit: `20f627e`. Dedup source: `/tmp/audit/issues.json` (`gh issue list --repo
matiaszanolli/midi2nes --limit 200`, 19 open issues) + scan of `docs/audits/`.

## Summary

The safety/robustness surface remains in **excellent** shape. All eight dimensions were
re-verified line-by-line against the current `main.py` (1610 lines) and its collaborators
following the `#136/#137/#202` commit (`20f627e`). One item is reported **NEW**; three
previously-filed LOW findings are re-confirmed present (no regression, not re-filed); every
other dimension is confirmed clean with zero findings.

- **D1 Swallowed-Error Handling**: `run_full_pipeline`'s single `try` (`main.py:900`) /
  broad `except Exception as e` (`main.py:1193`) is unchanged — still LOW/testability-only
  (Existing: `#384`). The parallel→sequential pattern-detector fallback (`main.py:977-1003`)
  and its lossy-resample warning are intact and still the documented fallback; the
  `ParallelPatternDetector`'s own per-chunk retry-then-record-failure path
  (`tracker/pattern_detector_parallel.py:215-260`) durably surfaces any truly-lost chunks
  after the loop rather than silently dropping them — confirmed, not a finding.
  **`#380`/TD-28 is CLOSED and its dedup is real**: both `run_export` (`main.py:709-720`)
  and `run_full_pipeline` (`main.py:1093-1109`) now call one shared
  `pack_dpcm_into_asm(frames, asm_path, *, verbose=False) -> DpcmPackResult` helper
  (`main.py:126-214`), and the "NO DRUMS" vs. "PARTIAL DPCM MISS" labeling (`#367`/DP-DPCM-05)
  is correctly derived from `pack_result.loaded_samples`/`.warning` at both call sites. But
  the **specific messaging asymmetry** the 2026-08-05 audit flagged under `#380` survives the
  fix unchanged, because `#380`'s own scope explicitly kept "presentation... at the call
  sites": `run_full_pipeline` still special-cases `pack_result.index_found is False` with an
  info line (`main.py:1100-1101`), while `run_export` has no equivalent branch at all
  (`main.py:709-720`) — see **SAFE-2026-08-06-1** below, now reported as **NEW** since the
  tracking issue that covered it (`#380`) is closed for an unrelated reason (the duplication,
  not this gap).
- **D2 Malformed-Input Resilience**: both `mido.MidiFile` call sites remain guarded —
  `tracker/parser_fast.py:15-20` (`_open_midi_file`) and `tracker/parser.py:10-15` — both
  convert `(EOFError, OSError, ValueError)` to `InvalidMIDIError` and re-raise
  `FileNotFoundError` as-is. Repo-wide grep confirms no other `mido.MidiFile` call site
  (`nes/song_bank.py` goes through `tracker.parser_fast.parse_midi_to_frames`, inheriting the
  guard). The per-event drop counter (`tracker/parser_fast.py:115-140`,
  `dropped_note_events`/`last_drop_reason`) is intact and unfired in this review.
- **D3 Subprocess/CC65 Safety**: all `ca65`/`ld65` invocations remain argv lists
  (`compiler/cc65_wrapper.py:141`, `:199`); the sole `shell=True`
  (`compiler/compiler.py:120`, `# nosec B602`) is fed only by
  `BaseMapper.generate_post_process_commands` (`mappers/base.py:143-160`), which returns a
  static `""` — grep confirms `nrom.py`/`mmc1.py`/`mmc3.py` define no override. `
  check_toolchain()` (`compiler/cc65_wrapper.py:34-81`) gates both `ROMCompiler.compile()`
  (`compiler/compiler.py:182`) and `CC65Wrapper.build()` (`:260`); grepping every
  `.assemble(`/`.link(` call site in the repo confirms these are the *only* two entry points,
  so `assemble()`/`link()` are never reachable without `check_toolchain()` having run first.
  Returncode+stderr are checked at every `subprocess.run` call
  (`cc65_wrapper.py:162-168`, `:225-231`; `compiler.py:126-132`) and `10s`/`120s`/`60s`
  timeouts are present and wrapped in `except subprocess.TimeoutExpired` throughout. The
  known, previously-adjudicated non-issue (`AUDIT_MAPPERS_2026-06-28.md`'s M-4: `assemble()`/
  `link()` build their argv with the bare `"ca65"`/`"ld65"` strings rather than the
  `self._ca65_path`/`self._ld65_path` resolved by `check_toolchain()`) is unchanged and was
  already explicitly ruled "no change needed" — re-confirmed, not re-raised here.
- **D4 Unsafe Deserialization**: repo-wide grep (excluding `venv/`) for
  `eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system`/`shell=True` finds only the one
  documented, guarded `shell=True` above (plus two comment/docstring mentions of it in
  `compiler/compiler.py` and `tests/test_mappers.py`). `config/config_manager.py:127` still
  uses `yaml.safe_load`.
- **D5 JSON-Intermediate Guards**: `load_json_stage` (`main.py:76-105`) still guards all
  four inter-stage subcommand reads: `run_map` (`:228`, `['events']`), `run_frames`
  (`:248`, `[]`), `run_export` (`:646`/`:654`, `[]`/`['patterns','references']`),
  `run_detect_patterns` (`:725`, `[]`) — confirmed by re-reading each call site's downstream
  key access. `nes/song_bank.py:import_bank` (`#220`/SAFE-09) and `run_song_add/list/remove`
  independently guard the song-bank JSON family the same way. No bare
  `json.loads(...).read_text()` remains on a user-supplied path anywhere in `main.py`.
- **D6 File/Resource Handling**: grep for bare `open(` (no `with`) across `main.py`,
  `tracker/`, `nes/`, `exporter/`, `compiler/`, `config/`, `dpcm_sampler/` returns zero
  matches. `tempfile.TemporaryDirectory` (`main.py:897`) auto-cleans. Backup create
  (`_backup_existing_rom`, `main.py:475-488`) / delete-on-success (`main.py:1190-1191`,
  `:604-605`) / restore-on-failure (`_restore_backup`, `main.py:491-503`, invoked from the
  single centralized `finally:` blocks at `main.py:1201-1205` and `:601-605`) contract is
  correct and unchanged.
- **D7 Exception-Type Discipline**: `config/config_manager.py`'s `_load_from_file`
  (`:123-134`) narrows to `(OSError, yaml.YAMLError)` → `ConfigurationError`. Re-reading
  `save()` (`:242-256`) and `validate()` (`:258-301`) shows **both now raise typed
  exceptions** — `ConfigurationError("No path specified for saving configuration")` at
  `:251` and `ValidationError("Configuration validation failed", ...)` at `:299` — neither is
  a bare `ValueError` any more. This is *better* than the audit-safety skill's own hotspot
  text currently assumes (it still describes both as bare `ValueError`); the skill's D7
  section has drifted from the code and is a candidate for `/audit-sync`, not a code finding.
  No bare `except:` found anywhere in the repo outside test docstrings that reference
  historically-fixed bugs (`tests/test_parser_fast.py:582`, `tests/test_rom_tester.py:40`).
- **D8 Partial-Output-on-Failure**: `run_full_pipeline` still builds inside the
  auto-cleaned temp dir and only reaches the final path via `ROMCompiler.compile()`'s
  `shutil.copy`. `run_export`'s direct `.asm` write (`exporter/exporter_ca65.py:996`,
  `:1430`) remains non-atomic (Existing: `#385`). The DPCM messaging asymmetry above is also
  a D8-adjacent partial-output-visibility gap (SAFE-2026-08-06-1). The backup/restore
  `finally` block is single and centralized per entry point (D6, above).

### Counts

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 1 new (+ 3 Existing, not re-filed) |
| **Total new findings** | **1** |

By dimension: D1/D8 (1 new: `SAFE-2026-08-06-1`; Existing ×1: `#384`), D8 (Existing ×1:
`#385`), D1 (Existing ×1: `#381`, re-confirmed present in the legacy-mode
`assign_tracks_to_nes_channels` hard dependency on `dpcm_index.json`, `main.py:926-927`
→ `dpcm_sampler/enhanced_drum_mapper.py:268-276`). D2, D3, D4, D5, D6, D7 confirmed clean
with no findings, new or existing.

### Three highest-leverage robustness items

1. **`SAFE-2026-08-06-1`** (NEW) — give `run_export`'s DPCM block the same `index_found is
   False` branch `run_full_pipeline` already has, so a missing `dpcm_index.json` is never
   silently indistinguishable from "this song has no drums."
2. **`#381`** (Existing, OPEN) — guard the full pipeline's legacy-mode `dpcm_index.json`
   dependency so a missing index degrades/reports cleanly instead of aborting the whole run
   at step 2.
3. **`#385`** (Existing, OPEN) — make `run_export`'s direct `.asm` write atomic
   (write-to-temp + rename) so a failure mid-write can't leave a half-written `music.asm` at
   the user's requested path.

---

## Findings

### SAFE-2026-08-06-1: `run_export`'s DPCM-pack block still gives zero feedback when `dpcm_index.json` is missing (asymmetric with `run_full_pipeline`, survives the `#380` dedup)
- **Severity**: LOW
- **Dimension**: D1 (Swallowed-Error Handling) / D8 (Partial-Output-on-Failure)
- **Location**: `main.py:709-720` (`run_export`'s call to `pack_dpcm_into_asm`) vs.
  `main.py:1097-1109` (`run_full_pipeline`'s call, specifically the `if not
  pack_result.index_found:` branch at `:1100-1101`)
- **Status**: NEW (previously discussed under `#380`, which is now CLOSED for the
  duplication root cause it actually targeted; this specific messaging gap was
  deliberately out of that fix's scope per its own commit message — "Presentation... stays
  at the call sites" — and has no other open tracking issue)
- **Description**: `pack_dpcm_into_asm` returns `DpcmPackResult(index_found=False)` with
  `warning=None` when `dpcm_index.json` does not exist (`main.py:146-148`). Both call sites
  receive this result, but only `run_full_pipeline` branches on `index_found` to print an
  info line; `run_export` only ever checks `if dpcm_pack_warning:` (`main.py:714`), which is
  `None` in this case, so nothing prints at all — the subcommand's success line
  (`" Exported CA65 ASM -> {args.output}"`) is the only output, identical to what a
  drum-free song would also produce. This is the same divergence the 2026-08-05 audit
  identified (tracked at the time as `Existing: #380`), but `#380`'s actual fix (extracting
  `pack_dpcm_into_asm`) explicitly preserved this exact behavior rather than closing it —
  the helper returns `index_found=False` precisely so each call site can decide what (if
  anything) to print, and `run_export` still decides "nothing."
- **Evidence**:
  ```python
  # main.py:709-720 (run_export) — no branch on index_found
  pack_result = pack_dpcm_into_asm(
      frames, args.output, verbose=getattr(args, 'verbose', False))
  dpcm_pack_warning = pack_result.warning
  print(f" Exported CA65 ASM -> {args.output}")
  if dpcm_pack_warning:          # None when index_found is False -- never fires
      ...

  # main.py:1097-1109 (run_full_pipeline) — explicit index_found branch
  pack_result = pack_dpcm_into_asm(frames, music_asm, verbose=args.verbose)
  dpcm_pack_warning = pack_result.warning
  if not pack_result.index_found:
      print("  ℹ️ No dpcm_index.json found, skipping DPCM packing.")
  elif pack_result.warning:
      print(f"  ⚠️ Warning: {pack_result.warning}")
  ```
- **Impact**: Confined to the step-by-step `export` subcommand's `.asm` output. The
  shipped `dpcm_index.json` normally lives at the repo root, so a user running `export` from
  there is unaffected; the gap bites when `export` runs from a different working directory,
  a fresh checkout missing the index, or a CI job with a different cwd — a song with
  percussion silently loses its drums in the exported ASM with no warning of any kind, not
  even the info-level line the pipeline path gives for the identical condition. The ROM/ASM
  byte content itself is unaffected either way (no DPCM data is emitted regardless, whether
  or not the message prints), so this stays a messaging-only LOW, not a data-corruption bug —
  but it is the one place in the DPCM-packing code path where the two call sites can still
  visibly disagree despite sharing the same helper.
- **Related**: `#380` (TD-28, closed — extracted the shared helper this finding's evidence
  now lives inside, but explicitly left presentation divergent); `#367`/DP-DPCM-05 (the
  adjacent "NO DRUMS"/"PARTIAL DPCM MISS" labeling, which both call sites *do* handle
  identically); `#381` (the sibling legacy-mapping guard gap, a harder failure of the same
  root dependency in `run_full_pipeline`'s mapping stage).
- **Suggested Fix**: Add the same `if not pack_result.index_found:` info-line branch to
  `run_export` that `run_full_pipeline` already has (or, better, move that one line of
  presentation into `pack_dpcm_into_asm` itself as an optional always-consistent print gated
  by a shared `print_status=True` flag), so the two call sites can no longer disagree on
  what a missing index looks like to the user.

---

## Dimensions confirmed clean (no new findings)

- **D2 Malformed-Input Resilience**: both `mido.MidiFile` sites guarded → `InvalidMIDIError`;
  no other unguarded `mido.MidiFile`/`open()`/`read_text()` on a user-supplied path found.
- **D3 Subprocess/CC65 Safety**: argv lists throughout; `check_toolchain()` gates every
  build entry point (verified as the only two `.assemble(`/`.link(` call sites repo-wide);
  returncode+stderr checked; timeouts present at every `subprocess.run` call; the one
  `shell=True` is fed only by a verified static constant (no mapper overrides it).
- **D4 Unsafe Deserialization**: no `eval`/`exec`/`yaml.load`/`pickle.load`/`os.system`
  anywhere in the repo outside `venv/`; config loading uses `yaml.safe_load`.
- **D5 JSON-Intermediate Guards**: `load_json_stage` covers all four inter-stage
  subcommand reads; the song-bank family has its own equivalent guard (`#220`/SAFE-09); no
  bare `json.loads(...).read_text()` remains on a user-supplied path.
- **D6 File/Resource Handling & Temp Cleanup**: no bare `open()` without `with` in any
  in-scope module; `TemporaryDirectory` auto-cleans; backup create/delete/restore contract
  correct and centralized in one `finally` block per entry point.
- **D7 Exception-Type Discipline**: typed hierarchy (`core/exceptions.py`) used
  consistently; `config_manager.py`'s `save()`/`validate()`/`_load_from_file()` all raise
  typed exceptions (confirmed better than the audit skill's own stale hotspot text assumes —
  a candidate for `/audit-sync`, not a code defect); no bare `except:` anywhere in production
  code.

Re-confirmed Existing findings (present, not regressed, not re-filed):
- **`#381`** (D1) — legacy-mode `assign_tracks_to_nes_channels(midi_data["events"],
  'dpcm_index.json')` (`main.py:926-927`) still hard-requires the index file to exist;
  `EnhancedDrumMapper._load_sample_index` (`dpcm_sampler/enhanced_drum_mapper.py:268-276`)
  raises `FileNotFoundError` when it's absent, aborting the entire pipeline at step 2 even
  for a drum-free song.
- **`#384`** (D1) — `run_full_pipeline`'s 8-step `try` (`main.py:900`) / broad `except
  Exception as e` (`main.py:1193`) still can't discriminate failure classes
  programmatically, though every failure surface underneath raises a specific typed
  exception whose message this catch-all faithfully relays.
- **`#385`** (D8) — `run_export`'s `.asm` write
  (`exporter/exporter_ca65.py:996`, `:1430`) remains a direct `open(output_path, 'w')`,
  not atomic (no write-to-temp + rename).

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_SAFETY_2026-08-06.md
```
