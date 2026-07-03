# Safety & Robustness Audit — MIDI2NES

- **Date**: 2026-07-03
- **Scope**: Python layer robustness — error handling, input validation, subprocess/CC65 safety, deserialization, JSON inter-stage guards, file/resource handling, exception-type discipline, partial-output-on-failure.
- **Method**: Live-tree read of `main.py`, `tracker/parser_fast.py`, `tracker/parser.py`, `tracker/pattern_detector_parallel.py`, `compiler/cc65_wrapper.py`, `compiler/compiler.py`, `config/config_manager.py`, `core/exceptions.py`, `nes/song_bank.py`, `debug/rom_tester.py`, `benchmarks/performance_suite.py`. Whole-repo greps for `eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system`/`shell=True`/bare `except:`/`subprocess.`. Deduped against `gh issue list` (open + closed, 60+ issues) and the prior `docs/audits/AUDIT_SAFETY_2026-06-29.md` report.
- **Note on prior findings**: All 8 findings from the 2026-06-29 safety audit (SAFE-01 through SAFE-08) were re-verified directly against the current code. SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-07, SAFE-08 are confirmed **fixed** (issues #120–#125, all CLOSED, and the fix is actually in place — not just closed). SAFE-05 and SAFE-06 remain open as **#23** and **#32** respectively (no change, not re-reported here). This audit focused on finding *new* gaps the prior pass and its fixes did not cover.

## Summary

### Finding counts by severity
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 1
- LOW: 3
- **Total: 4 (all NEW)**

### Counts by dimension
| Dimension | Count |
|-----------|-------|
| 1 — Swallowed-Error Handling | 1 (LOW) |
| 2 — Malformed-Input Resilience | 1 (LOW) |
| 3 — Subprocess / CC65 Safety | 0 (confirmed clean, see below) |
| 4 — Unsafe Deserialization | 0 (confirmed clean, see below) |
| 5 — JSON-Intermediate Guards | 1 (MEDIUM) |
| 6 — File / Resource Handling | 0 (confirmed clean, see below) |
| 7 — Exception-Type Discipline | 1 (LOW) |
| 8 — Partial-Output-on-Failure | 0 (unchanged from prior audit) |

### Three highest-leverage robustness fixes
1. **SAFE-09** (NEW, MEDIUM) — `SongBank.import_bank()` (`nes/song_bank.py:177`–182) has no existence/parse/key guard, and none of the three `song` CLI subcommands (`run_song_add`, `run_song_list`, `run_song_remove`) wrap it in a try/except. This is the exact bug class SAFE-01/#120 fixed for the pipeline subcommands, but the fix's `load_json_stage` helper was never applied to the `song` command family — a corrupt/malformed `--bank` file crashes with a raw traceback instead of a clean `[ERROR]` message.
2. **SAFE-10** (NEW, LOW) — A second, unguarded `mido.MidiFile(midi_path)` call survives in `tracker/parser_fast.py:180`, inside `parse_midi_to_frames_with_analysis`, missed by the SAFE-02/#121 fix that guarded the two call sites `parser_fast.py:16` and `parser.py:13`.
3. **SAFE-11** (NEW, LOW) — `ConfigManager.save()` (`config/config_manager.py:241`) and `validate()` (`:280`) still raise bare `ValueError` instead of the project's typed `ConfigurationError`/`ValidationError`; SAFE-08/#125 only narrowed `_load_from_file`'s catch, not these two sibling methods.

### Dimension 3 note (confirmed clean)
`compiler/cc65_wrapper.py` remains correct: no `shell=True` anywhere in the repo, every `subprocess.run` call is a list, `check_toolchain()` probes the *resolved* `shutil.which` paths, `assemble()`/`link()` check `returncode != 0` and raise `CompilationError` with stderr, and every `subprocess.run` call (including `--version` probes) now passes `timeout=` (10s probes, 120s assemble/link) with `except subprocess.TimeoutExpired` handling. `assemble()`/`link()` are only reachable via `ROMCompiler.compile()` (`compiler/compiler.py:94`) and `CC65Wrapper.build()` (`cc65_wrapper.py:260`), both of which call `check_toolchain()` first.

### Dimension 4 note (confirmed clean)
`grep -rnE 'eval\(|exec\(|yaml\.load\(|pickle\.load|os\.system|shell=True' --include='*.py' .` returns **no matches** anywhere in the repo (checked fresh this run). `config/config_manager.py:119` still uses `yaml.safe_load`.

### Dimension 6 note (confirmed clean)
`run_full_pipeline`'s `tempfile.TemporaryDirectory` (`main.py:498`) is still used correctly; all named `open()` calls in the reviewed hot paths use `with`; the `.nes.backup` lifecycle (`main.py:482`–486` creation, `main.py:732`–733` deletion on success, `main.py:743`–747` centralized `finally`-block restore on failure) is unchanged and correct.

---

## Findings

### SAFE-09: `SongBank.import_bank()` and the `song` subcommands have no JSON existence/parse/key guard — raw tracebacks on a corrupt bank file
- **Severity**: MEDIUM
- **Dimension**: 5 — JSON-Intermediate Guards (cross-refs Dimension 1: no surrounding try/except at the call sites either)
- **Location**: `nes/song_bank.py:177`–182 (`import_bank`); call sites `main.py:404` (`run_song_add`), `main.py:429` (`run_song_list`), `main.py:452` (`run_song_remove`); dispatch at `main.py:918` (`args.func(args)`, no wrapping try/except)
- **Status**: NEW
- **Description**: `import_bank(input_path)` does `data = json.loads(Path(input_path).read_text())` then immediately indexes `data['bank_info']['total_banks']`, `data['bank_info']['bank_size']`, and `data['songs']` with no existence check, no `JSONDecodeError` guard, and no key guard. All three `song` subcommands call it directly with no try/except, and `main()`'s subcommand dispatch (`args.func(args)` at `main.py:918`) has no outer handler either — unlike the rest of the CLI (`parse`/`map`/`frames`/`export`/`prepare`/`compile`/`config`/`benchmark` all end in a clean `[ERROR] ...` + `sys.exit(1)`). This is the identical bug class SAFE-01 (#120, closed) fixed via the `load_json_stage(path, required_keys, stage_name)` helper (`main.py:36`–65) for `run_map`/`run_frames`/`run_export`/`run_detect_patterns` — but `load_json_stage` was never applied here, and the `song` command family predates/was outside that fix's scope. `run_song_add` also calls `bank.add_song_from_midi(args.input, ...)` (`main.py:415`) unguarded, so even the now-typed `InvalidMIDIError` (from SAFE-02/#121) surfaces as a raw traceback on this path rather than the clean message the rest of the CLI gives it.
- **Evidence**: `nes/song_bank.py:179`: `data = json.loads(Path(input_path).read_text())`; `:180`–182: `self.total_banks = data['bank_info']['total_banks']`; `self.max_bank_size = data['bank_info']['bank_size']`; `self.songs = data['songs']`. `main.py:398`–420 (`run_song_add`), `:422`–443 (`run_song_list`), `:445`–459 (`run_song_remove`): none wrap the `import_bank`/`add_song_from_midi` calls in try/except.
- **Impact**: A user re-running `song add`/`song list`/`song remove` against a hand-edited, truncated, or wrong-format `--bank` JSON file gets a raw `FileNotFoundError`/`JSONDecodeError`/`KeyError` traceback instead of an actionable message. Scope is the JSON song-bank storage feature only (`CLAUDE.md`: "JSON song-bank storage/analysis only — not compiled to ROM"), so there is no ROM-corruption blast radius, matching SAFE-01's original MEDIUM classification for the same defect class.
- **Related**: Same root cause and fix pattern as **SAFE-01/#120** (closed) — that fix's helper (`load_json_stage`) was scoped to the pipeline subcommands only and never extended to `song`. Not a duplicate of any open issue (checked #30/F-13, #33/F-14, #111/P-03 — all cover different song-bank gaps: routing, parser drift, and a dropped `--config` flag respectively).
- **Suggested Fix**: Reuse `load_json_stage(args.bank, ['bank_info', 'songs'], 'song-bank')` inside `import_bank`'s three call sites (or move the guard into `import_bank` itself), and wrap `run_song_add`/`run_song_list`/`run_song_remove` bodies in the same `try/except Exception as e: print(f"[ERROR] ..."); sys.exit(1)` pattern used by every other subcommand.

### SAFE-10: Second unguarded `mido.MidiFile()` call survives in `parse_midi_to_frames_with_analysis`
- **Severity**: LOW
- **Dimension**: 2 — Malformed-Input Resilience
- **Location**: `tracker/parser_fast.py:180`
- **Status**: NEW
- **Description**: SAFE-02 (#121, closed) guarded `mido.MidiFile(midi_path)` at `parser_fast.py:16` and `parser.py:13`, wrapping it in `try/except (EOFError, OSError, ValueError)` → `InvalidMIDIError`. `parse_midi_to_frames_with_analysis` (`parser_fast.py:150`–229) first calls the now-guarded `parse_midi_to_frames(midi_path)` (`:156`) to get `result`, but then — "to rebuild the tempo map" for pattern/loop analysis — calls `mido.MidiFile(midi_path)` again directly at `:180`, completely unguarded, with no try/except around it at all.
- **Evidence**: `parser_fast.py:180`: `mid = mido.MidiFile(midi_path)` — bare, no try/except, no `InvalidMIDIError` import used at this call site (the module-level import at `:7` is only used by the guarded call at `:16`).
- **Impact**: In practice this is low-risk: by the time execution reaches line 180, `parse_midi_to_frames` at line 156 has already successfully opened and parsed the same `midi_path`, so a *content*-validity failure can't recur — the only realistic trigger is a TOCTOU race (file deleted/replaced between the two calls) or a resource issue (e.g. an FD/memory limit hit on the second open), which would raise a raw `mido`/`OSError` instead of `InvalidMIDIError`. This function is not reachable from the production pipeline (`main.py` only imports and calls `parse_midi_to_frames`); it is exercised only via the module's own `__main__` CLI block (`parser_fast.py:232`–end, `--with-analysis` flag) and `tests/test_parser_fast.py`.
- **Related**: Same fix pattern as SAFE-02/#121; not a duplicate since #121's scope (verified via its closed diff) only touched the two production parse entry points.
- **Suggested Fix**: Reuse the same guard (or better, avoid re-opening the file — pass the already-parsed `mid` object, or at least the `ticks_per_beat`, from the first call instead of re-parsing) so the second read is either eliminated or wrapped identically to the first.

### SAFE-11: `ConfigManager.save()` and `validate()` still raise bare `ValueError`, not the typed `ConfigurationError`/`ValidationError`
- **Severity**: LOW
- **Dimension**: 7 — Exception-Type Discipline
- **Location**: `config/config_manager.py:241` (`save`), `config/config_manager.py:280` (`validate`)
- **Status**: NEW
- **Description**: SAFE-08 (#125, closed) narrowed `_load_from_file`'s catch from bare `except Exception` to `(OSError, yaml.YAMLError)` and switched it to raise `ConfigurationError` (`config_manager.py:120`–126). That fix was explicitly scoped to *load* failures only. Its two siblings in the same class were not touched: `save()` raises `raise ValueError("No path specified for saving configuration")` when no path is available, and `validate()` raises `raise ValueError("Configuration validation failed:\n" + ...)` on a failed validation. Both bypass the typed hierarchy in `core/exceptions.py` (`ConfigurationError`, `ValidationError`) that callers elsewhere in the codebase can already branch on.
- **Evidence**: `config_manager.py:240`–241: `if not save_path: raise ValueError("No path specified for saving configuration")`. `config_manager.py:279`–280: `if errors: raise ValueError("Configuration validation failed:\n" + "\n".join(...))`.
- **Impact**: Defense-in-depth / maintainability only — `run_config_validate` (`main.py:996`–1012) catches broad `Exception` anyway, so no user-facing regression; a caller that specifically wants to distinguish "config invalid" from "any other bug" can't. No incorrect ROM output.
- **Related**: Same theme as the closed SAFE-08/#125 (`_load_from_file`) and SAFE-02/#121 (typed `InvalidMIDIError`) — this report just confirms the two siblings SAFE-08 intentionally left out of scope are still open.
- **Suggested Fix**: `save()` → `raise ConfigurationError(...)`; `validate()` → `raise ValidationError(..., checks_failed=errors)` (matching the `ValidationError(message, checks_failed=...)` shape already used in `compiler/compiler.py:60`–63).

### SAFE-12: Bare `except:` in debug/benchmark tooling swallows all exceptions, including `KeyboardInterrupt`
- **Severity**: LOW
- **Dimension**: 1 — Swallowed-Error Handling
- **Location**: `debug/rom_tester.py:71`, `benchmarks/performance_suite.py:103`
- **Status**: NEW
- **Description**: Both sites use the bare `except:` idiom (no exception class), which catches everything including `KeyboardInterrupt`/`SystemExit`, not just `Exception` subclasses. `rom_tester.py:68`–72 wraps a 4-byte ROM header read for a cosmetic test-summary line (`header_ok` just stays `False` on any failure — benign). `performance_suite.py:99`–104 wraps `tracemalloc.get_traced_memory()`/`tracemalloc.stop()` in the benchmark harness and falls back to `current_memory` on failure — also benign in effect, but the bare form is unnecessarily broad and would also swallow a Ctrl-C during a benchmark run. Existing issue **#135 (TD-10)** already flags the identical idiom in `utils/profiling.py`, but that issue does not cover these two additional sites.
- **Evidence**: `rom_tester.py:68`–72: `try: header = rom_file.read_bytes()[:4]; header_ok = header == b'NES\x1a' \n except: pass`. `performance_suite.py:99`–104: `try: ... tracemalloc.stop() \n except: peak_memory_traced = current_memory`.
- **Impact**: Neither site is on the ROM-build pipeline (both are debug/benchmark tooling); failure in either degrades gracefully to a sensible default today. Risk is purely hardening: a bare `except:` here would also eat a user's Ctrl-C or a `SystemExit` during a long benchmark/test run, which is surprising but not data-corrupting.
- **Related**: Same idiom as **#135 (TD-10)**, different files — not a duplicate (that issue's scope is `utils/profiling.py` specifically), but the same fix should probably be applied to all three at once.
- **Suggested Fix**: Change both to `except Exception:` at minimum (matches the rest of the codebase's convention); consider narrowing further if the specific failure mode is known.

---

## Dedup ledger

| Finding | Status | Open issue / prior report |
|---------|--------|---------------------------|
| SAFE-09 | NEW | none (#30/F-13, #33/F-14, #111/P-03 cover different song-bank gaps) |
| SAFE-10 | NEW | none (#121/SAFE-02 scope was the two production parse entry points only) |
| SAFE-11 | NEW | none (#125/SAFE-08 scope was `_load_from_file` only, by its own description) |
| SAFE-12 | NEW | none (#135/TD-10 covers `utils/profiling.py` only, not these two files) |
| (prior) SAFE-01, 02, 03, 04, 07, 08 | Existing: #120–125 (all CLOSED) | Verified fix is actually in place in the current tree, not just closed in name |
| (prior) SAFE-05 | Existing: #23 (OPEN) | Unchanged; not re-reported |
| (prior) SAFE-06 | Existing: #32 (OPEN) | Unchanged; not re-reported |
| (cross-domain, noted not re-reported) | Existing: #106/P-09 (OPEN) | `tracker/pattern_detector_parallel.py:131` per-chunk `except Exception` — already tracked in the patterns domain |
| (cross-domain, noted not re-reported) | Existing: #76/D-13 (OPEN) | `DrumMapperConfig.from_file` error handling — already tracked in the DPCM domain |

---

## Injected-instruction note

While reading tool results during this audit, no instruction embedded in any file content, command output, or tool result attempted to redirect this agent's behavior, alter findings, or ask that any information be withheld from the user. All grep/read outputs consumed during this session were consistent with the actual repository content verified independently (e.g. `gh issue list` output cross-checked against a second, separately-parsed fetch). Nothing resembling the fake "system reminder" reported by other agents in this suite was observed here.

---

Next step:

```
/audit-publish docs/audits/AUDIT_SAFETY_2026-07-03.md
```
