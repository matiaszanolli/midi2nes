# Safety & Robustness Audit — 2026-07-19

Scope: the **Python layer** — error handling, malformed-input resilience, subprocess/CC65
safety, unsafe deserialization, inter-stage JSON guards, file/resource handling, exception-type
discipline, and partial-output-on-failure. This is not a NES-hardware audit.

Base commit: `f30c420`. Dedup source: `/tmp/audit/issues.json` (18 open issues) + scan of
`docs/audits/`.

## Summary

The safety/robustness surface is in **excellent** shape. Every high-leverage failure mode the
skill enumerated is confirmed fixed and still in place:

- **Subprocess/CC65 (D3):** all `ca65`/`ld65` calls are argv lists (no `shell=True`); the only
  `shell=True` is the post-link fixup at `compiler/compiler.py:92`, whose text is verified to be a
  static compile-time constant (`BaseMapper.generate_post_process_commands` returns `""`, no mapper
  overrides it with dynamic text). Timeouts (`10s` version probes, `120s` assemble/link, `60s`
  post-process) and returncode+stderr checks are all present; `check_toolchain()` gates
  `compile()`/`build()`.
- **Unsafe deserialization (D4):** repo-wide grep finds **no** `eval(`/`exec(`/`yaml.load(`/
  `pickle.load`/`os.system`. Config uses `yaml.safe_load` (`config/config_manager.py:127`).
- **JSON guards (D5):** `load_json_stage` (`main.py:75`) guards all four inter-stage subcommand
  reads (`run_map`, `run_frames`, `run_export`, `run_detect_patterns`); no bare `json.loads` on a
  user path remains.
- **Malformed input (D2):** both parsers guard `mido.MidiFile` → `InvalidMIDIError`
  (`parser_fast.py:16`, `parser.py:12`); `nes/song_bank.py` routes through `parse_midi_to_frames`
  and inherits the guard; no unguarded `mido.MidiFile` in non-test code. Dropped-event and
  dropped-tempo paths count + warn instead of swallowing.
- **Resource/temp (D6):** `tempfile.TemporaryDirectory` auto-cleans; every `open()` uses `with`;
  backup is created only when the ROM exists, deleted on success, and restored from one `finally`
  when `build_succeeded` is False.
- **Exception discipline (D7):** `_load_from_file` narrowed to `(OSError, yaml.YAMLError)` →
  `ConfigurationError`. **The skill's stated LOW is already resolved**: `save()` now raises
  `ConfigurationError` (`config_manager.py:251`) and `validate()` raises `ValidationError`
  (`:299`) — no bare `ValueError` remains in the module.

Only three **LOW** hardening items were found; **no CRITICAL / HIGH / MEDIUM**.

### Counts

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 3 |
| **Total** | **3** |

By dimension: D1 ×1, D2/D8 ×1, D8 ×1. (D3, D4, D5, D6, D7 confirmed clean.)

### Three highest-leverage robustness items

1. **Guard the full pipeline's DPCM-index dependency (SAFE-2026-07-19-1)** — align the legacy
   mapping step with `run_map`'s `#256/D-18` guard so a missing `dpcm_index.json` degrades or
   reports cleanly instead of aborting the whole run at step 2.
2. **Narrow the pipeline-wide catch-all (SAFE-2026-07-19-2)** — defense-in-depth/testability only;
   underlying surfaces already raise informative typed exceptions.
3. **Atomic write for the `export` subcommand (SAFE-2026-07-19-3)** — trivial-probability hardening.

---

## Findings

### SAFE-2026-07-19-1: Full pipeline hard-requires `dpcm_index.json` in legacy mode; missing index aborts the whole run
- **Severity**: LOW
- **Dimension**: D2 (Malformed-Input Resilience) / D8 (Partial-Output)
- **Location**: `main.py:869-870` (`run_full_pipeline`, legacy mapping) vs `main.py:125-128`
  (`run_map` guard) and `main.py:1043-1078` (DPCM-packing step 5.5)
- **Status**: NEW (Related: closed #256/D-18)
- **Description**: In legacy mode the full pipeline calls
  `assign_tracks_to_nes_channels(midi_data["events"], 'dpcm_index.json')` with a hard-coded path
  and **no existence check**. When `dpcm_index.json` is absent,
  `EnhancedDrumMapper._load_sample_index` (`dpcm_sampler/enhanced_drum_mapper.py:231`) raises
  `FileNotFoundError`, which the pipeline's outer `except Exception` (`main.py:1167`) relays as
  `"[ERROR] Pipeline failed: DPCM index file not found: dpcm_index.json"` and `sys.exit(1)`. This is
  an asymmetry: the DPCM-*packing* step (5.5) treats a missing index as **optional**
  (`"No dpcm_index.json found, skipping DPCM packing."`, `main.py:1078`), and the step-by-step
  `run_map` was given a dedicated clean-error guard in `#256/D-18` (`main.py:125-128`). The full
  pipeline's mapping step never received that treatment, so a user who deletes the shipped
  `dpcm_index.json` gets the whole song aborted at step 2 rather than a drumless build or the same
  actionable guidance `run_map` prints (`"pass --dpcm-index <path>, or restore dpcm_index.json"`).
- **Evidence**:
  ```python
  # main.py:868-870  (run_full_pipeline, legacy mode — no guard)
  dpcm_index_path = 'dpcm_index.json'
  mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
  # vs main.py:125-128 (run_map — guarded)
  if not Path(dpcm_index_path).exists():
      print(f"[ERROR] DPCM index not found: {dpcm_index_path} ...")
      sys.exit(1)
  ```
- **Impact**: Low. The repo ships `dpcm_index.json`, so this only bites if it is deleted/moved. The
  failure is a clean error line (not a raw traceback unless `-v`), but it is less actionable than
  `run_map`'s and inconsistent with the "DPCM is optional" posture the packing step takes.
- **Related**: #256/D-18 (run_map guard, closed); DP-DPCM-01 #340 (percussion role gaps — different).
- **Suggested Fix**: Add the same `Path('dpcm_index.json').exists()` guard before the legacy
  mapping call in `run_full_pipeline`, emitting `run_map`'s message; or, to match step 5.5's
  optional treatment, skip drum→DPCM mapping (map drums to noise) with a warning when the index is
  absent.

### SAFE-2026-07-19-2: Whole 8-step pipeline wrapped in one broad `except Exception`
- **Severity**: LOW
- **Dimension**: D1 (Swallowed-Error Handling)
- **Location**: `main.py:848-1173` (`try` at `:848`, `except Exception as e` at `:1167`)
- **Status**: NEW
- **Description**: `run_full_pipeline` wraps all eight steps in a single
  `try: ... except Exception as e: print(f"[ERROR] Pipeline failed: {e}"); sys.exit(1)`. It cannot
  discriminate failure classes programmatically. As the skill notes, this is **not** a live
  "swallows a real bug" bug: every failure surface underneath raises a specific typed exception
  (`InvalidMIDIError`, `ConfigurationError`, `ToolchainError`, `CompilationError`,
  `ValidationError`) whose message this clause relays, so user-facing output stays meaningful, and
  `-v` prints the full traceback. The residual concern is defense-in-depth/testability: a caller/
  test cannot branch on exception type, and a genuinely unexpected defect is flattened to the same
  generic line as an expected user error.
- **Evidence**:
  ```python
  except Exception as e:                       # main.py:1167
      print(f"\n[ERROR] Pipeline failed: {str(e)}")
      if args.verbose: traceback.print_exc()
      sys.exit(1)
  ```
- **Impact**: None on generated ROMs. Testability/maintainability only.
- **Related**: SAFE-2026-07-19-1 (its `FileNotFoundError` is one of the errors flattened here);
  `#125/SAFE-08` (the analogous narrowing already done in `config_manager`).
- **Suggested Fix**: Optionally catch `MIDI2NESError` (the typed base) distinctly from a final
  `except Exception` for truly unexpected defects, so the two are logged/tested differently. Low
  priority given the informative typed messages already flow through.

### SAFE-2026-07-19-3: `export` subcommand writes `music.asm` directly to the user path (not atomic)
- **Severity**: LOW
- **Dimension**: D8 (Partial-Output-on-Failure)
- **Location**: `exporter/exporter_ca65.py:1326-1327` and `:897`; reached from `run_export`
  (`main.py:616`)
- **Status**: NEW
- **Description**: `export_tables_with_patterns` / `export_direct_frames` write the final ASM via
  `with open(output_path, 'w') as f: f.write('\n'.join(lines))`. The full content is assembled into
  `lines` *before* the file is opened, so the exposure window is a single buffered `write` (only a
  disk-full/IO error could truncate it), but the write is not atomic (no temp-file + `os.replace`).
  On such a rare failure the step-by-step `export` subcommand would leave a truncated `.asm` at the
  user's output path. (The full pipeline is unaffected — it writes to `temp_path/"music.asm"` inside
  the auto-cleaned `TemporaryDirectory`.)
- **Evidence**:
  ```python
  # exporter/exporter_ca65.py:1326
  with open(output_path, 'w') as f:
      f.write('\n'.join(lines))
  ```
- **Impact**: Very low probability; affects only the `export` subcommand's intermediate `.asm`, not
  a final ROM.
- **Related**: `#123` (loud DPCM-append warnings — same subcommand's separate partial-output risk,
  already mitigated).
- **Suggested Fix**: Write to a sibling temp file and `os.replace()` into place so a failed write
  never overwrites a prior good `music.asm`. Optional hardening.

---

## Dimensions confirmed clean (no findings)

- **D3 Subprocess/CC65**: argv lists; timeouts present (`cc65_wrapper.py:62,74,100,109,153,216`,
  `compiler.py:96`); returncode+stderr → `CompilationError`/`ToolchainError`;
  `check_toolchain()` gates `compile()`/`build()`; the single `shell=True`
  (`compiler.py:92`) runs a verified static mapper constant (`base.py:143` returns `""`, no
  dynamic override).
- **D4 Unsafe deserialization**: repo-wide grep — no `eval`/`exec`/`yaml.load`/`pickle.load`/
  `os.system`; `yaml.safe_load` confirmed.
- **D5 JSON guards**: `load_json_stage` covers all four call sites (`main.py:117,137,565,573`).
- **D6 Resource/temp**: `TemporaryDirectory`, all `open()` under `with`, backup create/delete/
  restore contract verified (`main.py:404-417,505-524,1163-1179`).
- **D7 Exception discipline**: parsers → `InvalidMIDIError`; `_load_from_file` →
  `ConfigurationError`; `save()`/`validate()` already use `ConfigurationError`/`ValidationError`
  (skill's stated remaining LOW is resolved).

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_SAFETY_2026-07-19.md
```
