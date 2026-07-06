# Safety & Robustness Audit — 2026-07-06

Audit of the Python layer for robustness and input safety (swallowed-error handling,
malformed-input resilience, subprocess/CC65 safety, unsafe deserialization,
JSON-intermediate guards, file/resource handling, exception-type discipline,
partial-output-on-failure).

- **Scope**: `main.py`, `tracker/parser_fast.py`, `tracker/parser.py`,
  `tracker/pattern_detector_parallel.py`, `compiler/compiler.py`,
  `compiler/cc65_wrapper.py`, `config/config_manager.py`, `core/exceptions.py`,
  `mappers/*.py`, `dpcm_sampler/enhanced_drum_mapper.py`, `utils/profiling.py`,
  `debug/`.
- **Method**: Whole-repo greps for `eval(`/`exec(`/`yaml.load(`/`pickle.load`/
  `os.system`/`shell=True`/bare `except`/`subprocess.run`/`mido.MidiFile`/`open(`, plus
  live-tree re-reads of every path the `audit-safety` skill flags as "fixed" and of the
  code touched since the previous safety audit (commits through `8308a63`, incl.
  `f4a1f54` #267/#268). Deduped against `/tmp/audit/issues.json` and prior reports
  `AUDIT_SAFETY_2026-06-29.md`, `AUDIT_SAFETY_2026-07-03.md`,
  `AUDIT_SAFETY_2026-07-05.md`.

## Summary

### Finding counts by severity
| Severity | New | Existing (open, noted) |
|----------|-----|------------------------|
| CRITICAL | 0 | 0 |
| HIGH     | 0 | 0 |
| MEDIUM   | 0 | 0 |
| LOW      | 1 | 3 |
| **Total new** | **1** | 3 |

### Counts by dimension (new findings)
| Dim | Area | New |
|-----|------|-----|
| 1 | Swallowed-error handling | 0 |
| 2 | Malformed-input resilience | 0 |
| 3 | Subprocess / CC65 safety | 0 |
| 4 | Unsafe deserialization | 0 |
| 5 | JSON-intermediate guards | 0 |
| 6 | File / resource / temp cleanup | 0 |
| 7 | Exception-type discipline | 0 (Existing #222) |
| 8 | Partial-output-on-failure | 0 |
| — | Dead code / config-guard consistency | 1 (SAFE-14) |

### Three highest-leverage robustness items
1. **SAFE-14 (NEW, LOW)** — `main.py:load_config` (drum-mapper config loader) silently
   falls back to defaults on a given-but-missing `--config` path — the exact anti-pattern
   #267 just fixed for pattern-detection caps — but is *dead code* (no production caller;
   only reached by tests, one of which asserts the silent-fallback). Align it with #267
   or delete it.
2. **Existing #222 (SAFE-11)** — `ConfigManager.save()`/`validate()` still raise bare
   `ValueError` instead of typed `ConfigurationError`/`ValidationError`. Already filed.
3. **Existing #223 (SAFE-12) / #135 (TD-10)** — bare `except:` in `debug/rom_tester.py`
   and `utils/profiling.py` swallows `KeyboardInterrupt`. Already filed.

### State of prior "fixed" claims (all re-verified this run)
- **SAFE-13 (was NEW/MEDIUM in `AUDIT_SAFETY_2026-07-05.md`) is now FIXED (#263).** The
  one `shell=True` in the repo (`compiler/compiler.py:92`) now carries a `# nosec B602`
  and a SECURITY INVARIANT docstring at both the call site (`compiler/compiler.py:81-87`)
  and the source of its argument (`mappers/base.py:149-155`). A regression test
  (`tests/test_mappers.py:318-334`, `test_shipped_mappers_emit_no_post_process` +
  static-constant test) asserts every shipped mapper returns `""` for both `is_windows`
  values and that the value never varies between calls. **Confirmed closed.**
- **D1** — `run_full_pipeline`'s broad `except Exception` relays typed exceptions; the
  DPCM-pack blocks set/echo the `⚠️ NO DRUMS` warning; the parallel→serial fallback
  (`tracker/pattern_detector_parallel.py:164-182`) is the documented graceful fallback.
  **Confirmed intact.**
- **D2** — `mido.MidiFile` is guarded in both parsers: `parser_fast` routes both opens
  through `_open_midi_file` (`tracker/parser_fast.py:9-23`), `parser.py:11-16` guards its
  single call. `FileNotFoundError` re-raised; `(EOFError, OSError, ValueError)` →
  `InvalidMIDIError`. Whole-repo grep finds no unguarded `mido.MidiFile` outside tests.
  **Confirmed intact.**
- **D3** — `cc65_wrapper` has `timeout=` on every `subprocess.run` (10s probes at
  `:62,74,100,109`; 120s assemble/link at `:153,216`), checks `returncode != 0`, and
  surfaces stderr. `compiler.py:_run_post_process` has `timeout=60` + `TimeoutExpired`
  handling. No `shell=True` outside the guarded/nosec-annotated MAP-3 path.
- **D4** — whole-repo grep for `eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system`
  returns **no matches**; `config/config_manager.py:127` uses `yaml.safe_load`.
  `shell=True` returns only the guarded `compiler/compiler.py:92`. **Confirmed clean.**
- **D5** — the four inter-stage subcommand reads go through `load_json_stage`
  (`main.py:64-93`, existence/JSON/dict/required-keys guard). The new
  `get_pattern_detection_caps` (`main.py:39-62`) additionally catches
  `ConfigurationError` from a missing/bad `--config` and exits cleanly (#267/PL-07).
  **Confirmed intact.**
- **D6** — `run_full_pipeline` uses `tempfile.TemporaryDirectory`; final ROM written only
  via `shutil.copy` at the end of `compile()`. No bare `open()` (all `open(` sites use
  `with`). **Confirmed intact.**
- **D7** — `_load_from_file` catches only `(OSError, yaml.YAMLError)` → `ConfigurationError`
  (`config/config_manager.py:117-134`). `save()`/`validate()` bare `ValueError`
  (`:251,299`) is **Existing #222**.
- **D8** — post-process runs before the final copy; DPCM-pack failures surface as loud
  warnings rather than a silently drumless ROM. **Confirmed intact.**

## Findings

### SAFE-14: `main.py:load_config` silently falls back to defaults on a missing config path (dead code, contradicts #267)
- **Severity**: LOW
- **Dimension**: Dead code / config-guard consistency (cross-refs Dim 5)
- **Location**: `main.py:738-742`
- **Status**: NEW
- **Description**: The drum-mapper config helper still uses the pre-#267 idiom
  `if config_path and Path(config_path).exists(): return DrumMapperConfig.from_file(...)`
  — a `--config` path that is *given but does not exist* is treated exactly like no path
  at all, silently returning built-in `DrumMapperConfig()` defaults. This is the same
  class of bug that commit `f4a1f54` (#267) just eliminated in
  `get_pattern_detection_caps`, which now raises/exits cleanly on a given-but-missing
  path. Two mitigating facts keep this LOW rather than MEDIUM: (a) `load_config` has
  **no production caller** — grep across the repo finds it invoked only from
  `tests/test_main.py` (`:1715,1726,1737`), i.e. it is dead code not wired into any
  subcommand (the `map --config` flag is deliberately not consumed, per the note at
  `main.py:1100`); and (b) its own test at `tests/test_main.py:1737`
  (`load_config("nonexistent.json")`) asserts the silent-fallback behavior, so any future
  wiring would inherit and lock in the anti-pattern.
- **Evidence**:
  ```python
  # main.py:738-742
  def load_config(config_path: Optional[str] = None) -> DrumMapperConfig:
      """Load drum mapper configuration from file or use defaults"""
      if config_path and Path(config_path).exists():
          return DrumMapperConfig.from_file(config_path)
      return DrumMapperConfig()
  ```
- **Impact**: None today (unreachable in the pipeline). Latent: if a future `map`/drum
  subcommand wires `load_config` to a user `--config`, a typo'd path would silently use
  default drum mapping instead of the user's, mirroring exactly the bug #267 fixed
  elsewhere — a class of "silent wrong output" the project has explicitly decided to
  reject.
- **Related**: #267 (`get_pattern_detection_caps` missing-path guard); `main.py:1100`
  (note that drum-mapper `--config` is intentionally unconsumed).
- **Suggested Fix**: Either delete `load_config` (and its three tests) as dead code, or —
  if it is intended for future use — change it to raise `ConfigurationError` for a
  given-but-missing path (matching `get_pattern_detection_caps`) and update
  `test_main.py:1737` to assert the raise rather than the silent fallback.

## Existing findings confirmed open (deduped, not re-filed)

- **#222 (SAFE-11)** — `ConfigManager.save()`/`validate()` raise bare `ValueError`
  (`config/config_manager.py:251,299`), Dimension 7. Open. LOW.
- **#223 (SAFE-12)** — bare `except:` in `debug/rom_tester.py:71` swallows all exceptions
  incl. `KeyboardInterrupt`, Dimension 1. Open. LOW.
- **#135 (TD-10)** — bare `except:` in `utils/profiling.py:120` (memory-sampler loop)
  swallows all errors incl. `KeyboardInterrupt`, Dimension 1. Open. LOW.

---

_Next step:_

```
/audit-publish docs/audits/AUDIT_SAFETY_2026-07-06.md
```
