# Safety & Robustness Audit — 2026-07-18

Delta/re-verify pass over the Python layer's robustness and input safety (swallowed-error
handling, malformed-input resilience, subprocess/CC65 safety, unsafe deserialization,
JSON-intermediate guards, file/resource handling, exception-type discipline,
partial-output-on-failure). This pass supersedes the earlier `AUDIT_SAFETY_2026-07-18.md`
(00:28) run, which predated commits `8a2457a` (#318–#321) and `08e7fb2` (#312–#315).

- **Scope**: `main.py`, `tracker/parser_fast.py`, `tracker/parser.py`,
  `tracker/pattern_detector.py`, `tracker/pattern_detector_parallel.py`,
  `compiler/compiler.py`, `compiler/cc65_wrapper.py`, `config/config_manager.py`,
  `core/exceptions.py`, `mappers/*.py`, `nes/song_bank.py`, `debug/rom_tester.py`,
  `utils/profiling.py`.
- **Method**: Re-ran the whole-repo greps live (`except\s*:|except Exception`,
  `eval\(|exec\(|yaml\.load\(|pickle\.load|os\.system|shell=True`, `MidiFile(`,
  `json.load`, `open(`) and re-read every flagged call site rather than trusting prior
  line numbers. Diffed the safety-relevant files that changed since the prior audit
  (`git diff 272a186..HEAD`) and read each change. Deduped against
  `/tmp/audit/issues.json` (`gh issue list --repo matiaszanolli/midi2nes --limit 200`)
  and the prior `docs/audits/AUDIT_SAFETY_*` reports.
- **What changed since the prior safety pass**: commit `8a2457a` (#318–#321) hardened
  config loading and removed dead code; commit `08e7fb2` (#312–#315) fixed a FamiStudio
  crash, DPCM aliases, coverage labeling, and dead-ASM removal. The safety-relevant
  effects are: **SAFE-14/#318** (`main.py:load_config`) now raises `ConfigurationError`
  on a given-but-missing path; **#222** (`ConfigManager.save()`/`validate()`) now raise
  typed `ConfigurationError`/`ValidationError`; **#223** (`debug/rom_tester.py` header
  check) now uses `except OSError`; and `utils/profiling.py` (#135) now uses
  `except Exception: break` instead of a bare `except:`. All four previously-carried
  safety findings are resolved in the tree. The remaining changed files
  (`pattern_detector*.py`, `main.py` coverage-note additions, `nes/*`, `dpcm_sampler/*`,
  `exporter_famistudio.py`) are cosmetic labeling / correctness fixes in other audit
  domains and introduce no new error-handling, subprocess, or deserialization surface.

## Summary

### Finding counts by severity
| Severity | New | Existing (open, noted) |
|----------|-----|------------------------|
| CRITICAL | 0 | 0 |
| HIGH     | 0 | 0 |
| MEDIUM   | 0 | 0 |
| LOW      | 0 | 0 |
| **Total** | **0** | **0** |

No new findings this pass, and no open safety findings remain. All eight dimensions were
re-verified live against the current tree. The four items carried by the previous safety
report (SAFE-14/#318, SAFE-11/#222, SAFE-12/#223, TD-10/#135) are all fixed in the code
as of `HEAD` (`308d712`); see "Previously-open findings, now fixed in-tree" below.

### Counts by dimension
| Dim | Area | New | Open |
|-----|------|-----|------|
| 1 | Swallowed-error handling | 0 | 0 |
| 2 | Malformed-input resilience | 0 | 0 |
| 3 | Subprocess / CC65 safety | 0 | 0 |
| 4 | Unsafe deserialization | 0 | 0 |
| 5 | JSON-intermediate guards | 0 | 0 |
| 6 | File / resource / temp cleanup | 0 | 0 |
| 7 | Exception-type discipline | 0 | 0 |
| 8 | Partial-output-on-failure | 0 | 0 |

### Three highest-leverage robustness items
None outstanding. The three carried into the prior report are now closed in-tree:
1. **SAFE-14/#318** — `load_config` given-but-missing `--config` path now raises
   `ConfigurationError` (was a silent fallback to `DrumMapperConfig()` defaults).
2. **SAFE-11/#222** — `ConfigManager.save()`/`validate()` now raise
   `ConfigurationError`/`ValidationError` (was bare `ValueError`).
3. **SAFE-12/#223 + TD-10/#135** — the KeyboardInterrupt-swallowing bare `except:` in
   `debug/rom_tester.py` and `utils/profiling.py` are gone (`except OSError` and
   `except Exception: break` respectively — both now let `KeyboardInterrupt` propagate).

## Re-verified live (all confirmed intact, no regressions)

- **D1 — Swallowed-error handling.** `run_full_pipeline`'s broad `except Exception as e:`
  (`main.py:1116` area) still relays typed exceptions from a specific, informative failure
  surface underneath. `compiler.py:compile_rom` (`:246-260`) discriminates
  `CompilationError`/`ValidationError` first and only falls through to a broad `except`
  that surfaces the traceback under `--verbose` (#32). The DPCM-pack blocks
  (`run_export`; full pipeline) still build and loudly print a `⚠️  NO DRUMS` /
  `dpcm_pack_warning` rather than silently shipping a drumless build (#123). The
  parallel→sequential pattern-detector fallback (`tracker/pattern_detector_parallel.py:
  168-186`) is unchanged and is still the documented graceful fallback; per-chunk failures
  are recovered serially with a durable end-of-run warning (#106). `parser_fast.py`'s
  per-event `except Exception` (`:154-163`) still counts drops and warns
  (`:165-168`, #124) instead of silently discarding note events.
- **D2 — Malformed-input resilience.** `mido.MidiFile` remains guarded in both parsers:
  `tracker/parser_fast.py:9-23` (`_open_midi_file`: `FileNotFoundError` re-raised,
  `(EOFError, OSError, ValueError)` → `InvalidMIDIError`) and `tracker/parser.py:11-16`
  (same pattern inline). `nes/song_bank.py` routes through `parse_midi_to_frames` and
  never calls `mido.MidiFile` directly. Whole-repo grep finds no unguarded `MidiFile(`
  outside `tests/`.
- **D3 — Subprocess / CC65 safety.** `compiler/cc65_wrapper.py` unchanged since the prior
  pass: `check_toolchain()` resolves via `shutil.which` then probes the resolved path with
  `timeout=10`, raising `ToolchainError`; `assemble()`/`link()` check `returncode != 0`,
  surface stderr/stdout via `CompilationError`, and use `timeout=120`. The only
  `shell=True` in the repo (`compiler/compiler.py:92`, `# nosec B602`) is gated by the
  SECURITY INVARIANT docstring in `mappers/base.py` (post-process snippet is a static
  compile-time constant), backed by `tests/test_mappers.py:311`. No override interpolates a
  runtime/user value into that snippet.
- **D4 — Unsafe deserialization.** Whole-repo grep for
  `eval(|exec(|yaml\.load\(|pickle\.load|os\.system` returns no matches. `shell=True`
  returns only the guarded `compiler/compiler.py:92` line (plus a doc comment and one test
  assertion referencing the string). `config/config_manager.py:127` still uses
  `yaml.safe_load`.
- **D5 — JSON-intermediate guards.** `load_json_stage` still gates every inter-stage
  subcommand read: `run_map` (required key `events`), `run_frames`, `run_export`'s patterns
  input (required keys `patterns`/`references`), and `run_detect_patterns`. The
  `was_sampled` local added to `run_detect_patterns` (#312) is assigned before use — no
  NameError.
- **D6 — File / resource / temp cleanup.** `run_full_pipeline` still uses
  `with tempfile.TemporaryDirectory(prefix="midi2nes_")`. Backup/restore is centralized in
  `_backup_existing_rom`/`_restore_backup`, invoked from single `finally:` blocks that fire
  only when `build_succeeded` is `False`; on success the backup is
  `unlink(missing_ok=True)`d. All `open(...)` sites in pipeline-reachable paths use `with`.
- **D7 — Exception-type discipline.** `ConfigManager._load_config` raises
  `ConfigurationError` on a given-but-missing `--config` path; `_load_from_file` catches
  only `(OSError, yaml.YAMLError)` → `ConfigurationError`. `save()` now raises
  `ConfigurationError` and `validate()` raises `ValidationError` (both imported at
  `config/config_manager.py:8`). `main.py:load_config` raises `ConfigurationError`
  (imported at `main.py:28`). No bare `ValueError` remains on these paths.
- **D8 — Partial-output-on-failure.** `run_export` writes `args.output` then appends DPCM
  in a separate guarded block that surfaces `⚠️  NO DRUMS` on failure. The full-pipeline
  build happens inside the temp dir and only reaches the final path via `shutil.copy` at
  the end of `ROMCompiler.compile()`; a mid-pipeline failure restores the prior good ROM
  via the centralized `finally` and never leaves a broken one in place.

## Findings

None.

## Previously-open findings, now fixed in-tree (dedup)

- **SAFE-14 / #318** — `main.py:load_config` now raises `ConfigurationError` on a
  given-but-missing `--config` path (was a silent fallback to defaults). Verified at
  `main.py:770-776`. Fixed by commit `8a2457a`.
- **SAFE-11 / #222** — `ConfigManager.save()` (`config/config_manager.py:251`) raises
  `ConfigurationError`; `validate()` (`:258-303`) raises `ValidationError`. Not present in
  the open-issue list — closed.
- **SAFE-12 / #223** — `debug/rom_tester.py` header check now uses `except OSError`
  (regression test at `tests/test_rom_tester.py:40`). Not present in the open-issue list —
  closed.
- **TD-10 / #135** — `utils/profiling.py:_monitor_loop` now uses `except Exception: break`
  (restored by commit `ed5900d`), so the memory-sampler thread no longer swallows
  `KeyboardInterrupt`. Issue #135 is still marked OPEN in the tracker but the code fix is in
  place; the KeyboardInterrupt concern that motivated it is resolved. Recommend closing
  #135 (or re-scoping it, if it tracks the remaining broad-`Exception` catch, which is an
  acceptable background-thread pattern, not a safety defect).

---

_No safety findings to publish. If closing the tracker-vs-tree gap on #135 is desired,
that is a tracker hygiene action, not an audit finding._
