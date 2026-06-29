# Safety & Robustness Audit — MIDI2NES

- **Date**: 2026-06-29
- **Scope**: Python layer robustness — error handling, input validation, subprocess/CC65 safety, deserialization, JSON inter-stage guards, file/resource handling, exception-type discipline, partial-output-on-failure.
- **Branch**: `fix/pipeline-safety-gates-6-10-11`
- **Method**: live-tree read of `main.py`, `tracker/parser_fast.py`, `tracker/parser.py`, `tracker/pattern_detector_parallel.py`, `compiler/cc65_wrapper.py`, `compiler/compiler.py`, `config/config_manager.py`, `core/exceptions.py`, `nes/song_bank.py`. Deduped against the 22 open issues in `/tmp/audit/issues.json` and prior reports in `docs/audits/`.

## Summary

### Finding counts by severity
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 4
- LOW: 4
- **Total: 8** (5 NEW, 3 Existing)

### Counts by dimension
| Dimension | Count |
|-----------|-------|
| 1 — Swallowed-Error Handling | 2 |
| 2 — Malformed-Input Resilience | 2 |
| 3 — Subprocess / CC65 Safety | 1 |
| 4 — Unsafe Deserialization | 0 (clean — see note) |
| 5 — JSON-Intermediate Guards | 1 |
| 6 — File / Resource Handling | 1 (Existing) |
| 7 — Exception-Type Discipline | 1 |
| 8 — Partial-Output-on-Failure | 0 net-new (root cause is SAFE-05 / #23) |

### Three highest-leverage robustness fixes
1. **SAFE-01** (NEW, MEDIUM) — Wrap the unguarded `json.loads(Path(...).read_text())` + bare-key access in every step-by-step subcommand (`run_map`, `run_frames`, `run_export`, `run_detect_patterns`) so a missing/garbage/wrong-stage JSON file yields a clean diagnostic instead of a raw `FileNotFoundError` / `JSONDecodeError` / `KeyError` traceback.
2. **SAFE-02** (NEW, MEDIUM) — Guard `mido.MidiFile(...)` in both parsers (and `SongBank.add_song_from_midi`) and raise `InvalidMIDIError` so a truncated/non-MIDI input produces "Invalid MIDI file" rather than a raw `mido`/`EOFError`/`OSError` stack trace; `run_full_pipeline` validates only `Path.exists()`.
3. **SAFE-04** (NEW, MEDIUM) — The full-pipeline DPCM-pack block (`main.py:532`–`572`) catches all exceptions and continues with a warning, so a corrupt/partial `dpcm_index.json` (missing `id`/`filename` key, bad JSON) silently ships a ROM with no drums.

### Dimension 4 note (clean)
A whole-repo grep for `eval(`, `exec(`, `yaml.load(`, `pickle.load`, `os.system`, `shell=True` found **no** unsafe deserialization or shell-injection surface. Config loading uses `yaml.safe_load` (`config/config_manager.py:117`); all `subprocess.run` calls pass a list, never `shell=True`. No finding for D4 — confirmed safe, flag if it regresses.

---

## Findings

### SAFE-01: Step-by-step subcommands read user JSON with no existence/parse guard and no key guard
- **Severity**: MEDIUM
- **Dimension**: 5 — JSON-Intermediate Guards
- **Location**: `main.py:47` (`run_map`), `main.py:56` (`run_frames`), `main.py:215`,`:220` (`run_export`), `main.py:274` (`run_detect_patterns`); key access `main.py:51` (`midi_data["events"]`), `main.py:237`–`238` (`pattern_data['patterns']`/`['references']`)
- **Status**: NEW
- **Description**: Each subcommand does `json.loads(Path(args.input).read_text())` (and `--patterns`) with no `Path.exists()` check and no `try/except` around the parse, then immediately indexes a hard-coded key. A missing file raises `FileNotFoundError`; a truncated/garbage file raises `json.JSONDecodeError`; a file from the wrong stage raises `KeyError` (e.g. feeding a parse JSON to `export`, which expects frames, or a frames JSON to `--patterns`, which expects `patterns`/`references`). All surface as raw tracebacks.
- **Evidence**: `run_map`: `midi_data = json.loads(Path(args.input).read_text()); ... assign_tracks_to_nes_channels(midi_data["events"], ...)`. `run_export`: `pattern_data = json.loads(Path(args.patterns).read_text())` then `patterns = pattern_data['patterns']; references = pattern_data['references']`. No guards on any path.
- **Impact**: Poor UX on the documented debugging path (CLAUDE.md "Step-by-step pipeline for debugging"); an inter-stage contract break (`_audit-common.md` Inter-Stage Data Contracts) crashes with `KeyError` rather than "this isn't a patterns file". No corrupted ROM (these stages do not write `args.output` before the parse), so this is robustness/UX, not correctness. Blast radius: all five subcommand entry points.
- **Related**: Prior pipeline audit F-05/F-08 touch these subcommands' flags/params but not input robustness; not in any open issue.
- **Suggested Fix**: A small `load_json_stage(path, required_keys, stage_name)` helper that checks existence, catches `JSONDecodeError`, and validates the expected top-level keys, raising a typed error (`ParsingError`/`ValidationError`) with a clear message. Reuse across all four subcommands.

### SAFE-02: `mido.MidiFile()` called unguarded in both parsers and SongBank — raw mido/OSError tracebacks instead of `InvalidMIDIError`
- **Severity**: MEDIUM
- **Dimension**: 2 — Malformed-Input Resilience
- **Location**: `tracker/parser_fast.py:14`, `tracker/parser.py:11`, `nes/song_bank.py:71` (via `parse_midi_to_frames`); pipeline entry only checks `Path.exists()` at `main.py:389`
- **Status**: NEW
- **Description**: A truncated, empty, or non-MIDI input file makes `mido.MidiFile(path)` raise a raw `mido`-internal exception (`EOFError`, `OSError`, `ValueError`) which propagates unwrapped. The project defines `InvalidMIDIError(filepath, reason)` in `core/exceptions.py:38` for exactly this, but it is never raised here. `run_full_pipeline` validates only `input_midi.exists()` (`main.py:389`), so a 0-byte or `.txt`-renamed-to-`.mid` file reaches `parse_fast` and crashes inside `mido`. On the default path the outer `except Exception` at `main.py:637` does convert it to `[ERROR] Pipeline failed: <raw mido message>` — better, but still not a typed `InvalidMIDIError`; on the `parse` subcommand (`run_parse`, `main.py:42`) there is no outer handler at all.
- **Evidence**: `parser_fast.py:14`: `mid = mido.MidiFile(midi_path)` — first statement, no guard. `parser.py:11` identical. `core/exceptions.py:38` `InvalidMIDIError` exists and is unused.
- **Impact**: Non-MIDI / corrupt input produces a confusing `mido` stack trace (`run_parse`) or an opaque message rather than "Invalid MIDI file: <path>". Common user error (wrong file). No ROM corruption. Cross-refs Dimension 7 (raises raw type instead of the available typed one).
- **Related**: F-14 / #33 notes `SongBank.add_song_from_midi` uses the full parser (parser drift); this finding is orthogonal (input-guard, all parsers).
- **Suggested Fix**: Wrap `mido.MidiFile(midi_path)` in `try/except (OSError, EOFError, ValueError, Exception)` and `raise InvalidMIDIError(midi_path, str(e))`. Add the same guard once in a shared helper since three call sites need it.

### SAFE-03: `subprocess.run` for CC65 omits `timeout` — a hung ca65/ld65 hangs the whole CLI
- **Severity**: LOW
- **Dimension**: 3 — Subprocess / CC65 Safety
- **Location**: `compiler/cc65_wrapper.py:143` (`assemble`), `:198` (`link`), `:58`/`:69` (version probes in `check_toolchain`), `:94`/`:102` (`get_version`)
- **Status**: NEW
- **Description**: None of the `subprocess.run` invocations pass a `timeout=`. The return-code and stderr handling is correct (`assemble`/`link` check `result.returncode != 0` and raise `CompilationError` with stderr — D3 nonzero-exit requirement satisfied, no `shell=True`, command is a list). The only gap is that a hung or wedged assembler/linker blocks the calling process indefinitely, hanging `run_full_pipeline` / `run_compile` with no timeout backstop. The parallel pattern detector, by contrast, uses `future.result(timeout=...)`.
- **Evidence**: `cc65_wrapper.py:143`: `result = subprocess.run(cmd, cwd=working_dir, capture_output=True, text=True)` — no `timeout`. Same shape at `:198`, `:58`, `:69`, `:94`, `:102`.
- **Impact**: A misbehaving toolchain build (rare) hangs the CLI with no recovery. Low likelihood; clear hardening win.
- **Related**: `assemble()`/`link()` are not reachable without `check_toolchain()` (called by `ROMCompiler.compile` at `compiler.py:94` and `CC65Wrapper.build` at `cc65_wrapper.py:240`) — confirmed safe, no finding there.
- **Suggested Fix**: Add `timeout=` (e.g. 120 s for assemble/link, 10 s for `--version`) and catch `subprocess.TimeoutExpired` → `CompilationError`/`ToolchainError`.

### SAFE-04: Full-pipeline DPCM-pack block swallows all exceptions and continues — corrupt `dpcm_index.json` silently ships a drumless ROM
- **Severity**: MEDIUM
- **Dimension**: 1 — Swallowed-Error Handling
- **Location**: `main.py:532`–`572` (full pipeline), mirrored in `run_export` at `main.py:253`–`269`
- **Status**: NEW
- **Description**: The DPCM packing step wraps `json.load(dpcm_index.json)`, `sorted(... key=lambda x: x['id'])`, `sample['filename']`/`sample['id']`/`sample.get('pitch', 15)`, and `packer.generate_assembly()` in one broad `except Exception as e: print("... Warning: Failed to pack DPCM samples ...")` and continues. A malformed `dpcm_index.json` (bad JSON, or any sample dict missing the `id`/`filename` key) raises `JSONDecodeError`/`KeyError`, is swallowed, and the ROM is built with **no drums** — the song is silently changed with only a warning line. Per `_audit-severity.md`, "a MIDI event class dropped on the floor with no warning, changing the song" is a CRITICAL floor; here it is downgraded to MEDIUM because (a) it prints a visible warning, and (b) DPCM/drums are an optional add-on whose absence does not break the ROM, so it is closer to "swallowing on an optional path" than full silent data loss.
- **Evidence**: `main.py:568`: `except Exception as e: print(f"  ⚠️ Warning: Failed to pack DPCM samples: {str(e)}")`. The try covers `json.load`, `sorted(dpcm_index.values(), key=lambda x: x['id'])` (`:542`), and `sample['filename']` (`:547`) — any `KeyError` there drops all drums.
- **Impact**: A drum-mapping/index regression produces a silently drumless ROM that a user mistakes for a good build. Affects every ROM using DPCM samples.
- **Related**: Distinct from F-10/#23 (DPCM `'a'`-mode append clobbering); same code region, different failure mode.
- **Suggested Fix**: Narrow the catch — let a malformed-index error (`KeyError`/`JSONDecodeError`) abort with a typed error instead of warn-and-continue, OR at minimum surface "ROM built WITHOUT drums" prominently in the success banner (mirroring the `pattern_loss_warning` mechanism already used at `main.py:628`).

### SAFE-05: `run_export` writes `args.output` then appends DPCM in a separate `try` — append failure leaves a partial `.asm` with only a warning
- **Severity**: MEDIUM
- **Dimension**: 8 — Partial-Output-on-Failure (root cause shared with #23/F-10)
- **Location**: `main.py:244`–`269` (`run_export`)
- **Status**: Existing: #23
- **Description**: `run_export` first writes the full `music.asm` via `export_tables_with_patterns(... args.output ...)`, then in a separate `try` opens `args.output` in **append** mode (`open(args.output, 'a')`, `main.py:266`) to add DPCM assembly. If the append-side packing raises, the catch at `:268` only prints a warning, leaving the main export intact but the DPCM tables missing. Combined with the open issue's append-on-reuse problem, re-running `export` to a reused output also doubles/clobbers the DPCM block. Both are the same root cause: append-mode write to the final output path after the main write.
- **Evidence**: `main.py:266`: `with open(args.output, 'a') as f: f.write("\n\n" + packer.generate_assembly())` inside a `try` whose `except` (`:268`) only warns.
- **Impact**: A reused or partially-failing `export` leaves a `.asm` the user mistakes for complete. Matches open issue #23 exactly.
- **Related**: **Existing: #23** (F-10, "export appends DPCM block in 'a' mode — re-running clobbers/doubles on a reused output"). Reported here only to record that the partial-output (D8) facet is the same defect; no new issue.
- **Suggested Fix** (per #23): build the full `music.asm` content (main + DPCM) in memory and write once with `'w'`; do not append to the final output path.

### SAFE-06: `compile_rom` broad `except Exception` prints then returns False — masks the real traceback without verbose
- **Severity**: LOW
- **Dimension**: 1 — Swallowed-Error Handling
- **Location**: `compiler/compiler.py:173`–`175`
- **Status**: Existing: #32
- **Description**: `compile_rom` catches `CompilationError`/`ValidationError` specifically (good), but a trailing `except Exception as e: print(f"[ERROR] Compilation failed: {e}"); return False` swallows any unexpected bug (e.g. a `TypeError` in the wrapper) into a one-line message and a `False` return, with no traceback even under `--verbose` (the function takes no verbose-traceback path).
- **Evidence**: `compiler.py:173`: `except Exception as e: print(f"[ERROR] Compilation failed: {e}"); return False`.
- **Impact**: A real compiler-wrapper bug is indistinguishable from a normal compile failure; harder to diagnose. Recoverable path (caller exits 1), so LOW.
- **Related**: **Existing: #32** (M-9). No new issue.
- **Suggested Fix** (per #32): re-raise or print `traceback.format_exc()` when verbose; keep typed `CompilationError`/`ValidationError` as the only clean-exit paths.

### SAFE-07: Per-event `except Exception: continue` in fast parser can silently drop a note event
- **Severity**: MEDIUM
- **Dimension**: 2 — Malformed-Input Resilience
- **Location**: `tracker/parser_fast.py:61`–`79`
- **Status**: NEW
- **Description**: Inside the note loop, frame conversion + dict-build for each `note_on`/`note_off` is wrapped in `try: ... except Exception: continue` "to avoid crashes". If `tempo_map.get_frame_for_tick(...)` / `get_tempo_at_tick(...)` or any attribute access raises for a given event, that note is dropped with **no count and no warning** — per `_audit-severity.md` a dropped MIDI event class that changes the song is a CRITICAL floor. Mitigating it to MEDIUM: re-reading the path, `get_frame_for_tick` (`tempo_map.py:144`–`147`) is pure arithmetic (`calculate_time_ms` + `round`) with no `raise`, and `get_tempo_at_tick` returns a stored tempo, so on realistic MIDI no note is actually dropped — the catch is dead defense that *would* hide data loss if a future change made the hot path raise. It is the silent, uncounted nature (not a confirmed live drop) that keeps this open.
- **Evidence**: `parser_fast.py:77`: `except Exception:` / `# Skip problematic events to avoid crashes` / `continue`. No counter, no warning, unlike the tempo-change skip at `:46` which is at least scoped to `TempoValidationError`.
- **Impact**: If the per-event path ever raises (e.g. a future tempo-map regression), notes vanish silently and the ROM plays the wrong song with no signal. Today: latent.
- **Related**: Cross-refs SAFE-02 (same file's top-level `mido` guard gap).
- **Suggested Fix**: Catch only the specific expected exception (or count drops and emit a warning if >0), so a real drop is surfaced rather than swallowed. Mirror the `was_sampled` warning pattern used elsewhere.

### SAFE-08: `ConfigManager._load_from_file` re-raises as generic `ValueError`, not `ConfigurationError`
- **Severity**: LOW
- **Dimension**: 7 — Exception-Type Discipline
- **Location**: `config/config_manager.py:113`–`119`
- **Status**: NEW
- **Description**: `_load_from_file` wraps `open` + `yaml.safe_load` in `try/except Exception as e: raise ValueError(...)`. The project defines `ConfigurationError` (`core/exceptions.py:149`) for exactly this, but it is never used. Callers (`run_config_validate`, `main.py:874`, and `DrumMapperConfig.from_file`) cannot distinguish a missing/permission-denied file from malformed YAML, and catch only broad `Exception`. The broad `except Exception` also folds a genuine bug (e.g. a `TypeError` in config post-processing) into the same `ValueError`.
- **Evidence**: `config_manager.py:118`: `except Exception as e: raise ValueError(f"Failed to load configuration from {path}: {e}")`. `core/exceptions.py:149`: `class ConfigurationError(MIDI2NESError): pass` — unused.
- **Impact**: Defense-in-depth / maintainability; callers can't branch on config-error type. No incorrect ROM. LOW.
- **Related**: Same exception-discipline theme as SAFE-02 (parsers → `InvalidMIDIError`).
- **Suggested Fix**: Catch `(OSError, yaml.YAMLError)` and `raise ConfigurationError(...)`; let other exceptions propagate as real bugs.

---

## Dedup ledger

| Finding | Status | Open issue / prior report |
|---------|--------|---------------------------|
| SAFE-01 | NEW | none (pipeline F-05/F-08 cover flags, not input guards) |
| SAFE-02 | NEW | none (#33/F-14 is parser drift, not input guard) |
| SAFE-03 | NEW | none (#49/REG-09 is *test coverage* of cc65_wrapper, not the timeout gap) |
| SAFE-04 | NEW | none (#23/F-10 is the append-clobber, different failure mode) |
| SAFE-05 | Existing: #23 | F-10 — recorded as D8 facet of same defect |
| SAFE-06 | Existing: #32 | M-9 |
| SAFE-07 | NEW | none |
| SAFE-08 | NEW | none |

> Note: #49 (REG-09) asks for *tests* of cc65 missing-tool/nonzero-exit handling; SAFE-03 is a distinct code gap (no `timeout`), so it is NEW rather than a dup.

---

Next step:

```
/audit-publish docs/audits/AUDIT_SAFETY_2026-06-29.md
```
