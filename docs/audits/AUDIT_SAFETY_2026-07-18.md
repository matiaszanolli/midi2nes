# Safety & Robustness Audit — 2026-07-18

Delta/re-verify pass over the Python layer's robustness and input safety (swallowed-error
handling, malformed-input resilience, subprocess/CC65 safety, unsafe deserialization,
JSON-intermediate guards, file/resource handling, exception-type discipline,
partial-output-on-failure), against `AUDIT_SAFETY_2026-07-06.md`.

- **Scope**: `main.py`, `tracker/parser_fast.py`, `tracker/parser.py`,
  `tracker/pattern_detector_parallel.py`, `compiler/compiler.py`,
  `compiler/cc65_wrapper.py`, `config/config_manager.py`, `core/exceptions.py`,
  `mappers/*.py`, `nes/song_bank.py`, `dpcm_sampler/enhanced_drum_mapper.py`,
  `utils/profiling.py`, `debug/`.
- **Method**: Diffed the repo against the commit that produced the 2026-07-06 report
  (`04b3a8c..HEAD`) to scope what actually changed in safety-relevant files, then
  independently re-ran the whole-repo greps (`except\s*:|except Exception`,
  `eval\(|exec\(|yaml\.load\(|pickle\.load|os\.system|shell=True`, `mido.MidiFile`,
  `json.load(s)`, `open(`) and re-read every flagged call site live rather than trusting
  the prior report's line numbers. Deduped against `/tmp/audit/issues.json`
  (`gh issue list --repo matiaszanolli/midi2nes --limit 200`) and
  `docs/audits/AUDIT_SAFETY_2026-07-06.md`.
- **What changed since the last safety audit**: only `main.py` (mapper recovery from
  `nes.cfg`, #297/#269 — reads an optional file with an `.exists()` guard, no new risk),
  `tracker/tempo_map.py` (docstring-only, #97/#98), and `tracker/track_mapper.py`
  (deterministic-seed arpeggio order, #92 — a determinism fix, not an error-handling
  change). None of these touch the eight dimensions below in a way that introduces a new
  failure mode.

## Summary

### Finding counts by severity
| Severity | New | Existing (open, noted) |
|----------|-----|------------------------|
| CRITICAL | 0 | 0 |
| HIGH     | 0 | 0 |
| MEDIUM   | 0 | 0 |
| LOW      | 0 | 4 |
| **Total** | **0** | 4 |

No new findings this pass. All eight dimensions were re-verified live and are unchanged
from the 2026-07-06 report; the one previously-identified LOW (SAFE-14, `main.py`
`load_config`) is carried forward below since it was never filed as a GitHub issue.

### Counts by dimension
| Dim | Area | New | Existing |
|-----|------|-----|----------|
| 1 | Swallowed-error handling | 0 | 0 |
| 2 | Malformed-input resilience | 0 | 0 |
| 3 | Subprocess / CC65 safety | 0 | 0 |
| 4 | Unsafe deserialization | 0 | 0 |
| 5 | JSON-intermediate guards | 0 | 0 |
| 6 | File / resource / temp cleanup | 0 | 0 |
| 7 | Exception-type discipline | 0 | 1 (#222) + carried-forward SAFE-14 |
| 8 | Partial-output-on-failure | 0 | 0 |
| — | Dead code / config-guard consistency | 0 (carried forward) | 1 |
| — | Bare `except:` (KeyboardInterrupt-unsafe) | 0 | 2 (#223, #135) |

### Three highest-leverage robustness items (all pre-existing, still open)
1. **Carried-forward SAFE-14 (LOW)** — `main.py:763-767` (`load_config`) still silently
   falls back to `DrumMapperConfig()` defaults on a given-but-missing `--config` path —
   the exact anti-pattern #267 eliminated for `get_pattern_detection_caps` and #267/PL-07
   eliminated for `ConfigManager._load_config`. Still dead code (only reached from
   `tests/test_main.py:1707-1739`, no production caller), and its own test at
   `tests/test_main.py:1737` still asserts the silent-fallback behavior. Not yet filed as
   a GitHub issue — no matching title in the tracker.
2. **Existing #222 (SAFE-11)** — `ConfigManager.save()` (`config/config_manager.py:251`)
   and `validate()` (`:299`) still raise bare `ValueError` instead of
   `ConfigurationError`/`ValidationError`. Open.
3. **Existing #223 (SAFE-12) / #135 (TD-10)** — bare `except:` in
   `debug/rom_tester.py:71` and `utils/profiling.py:120` still swallow
   `KeyboardInterrupt` along with everything else. Both open.

### Re-verified live (all confirmed intact, no regressions)
- **D1** — `run_full_pipeline`'s broad `except Exception as e:` (`main.py:1096`) still
  relays typed exceptions from a specific, informative failure surface underneath. The
  DPCM-pack blocks (`run_export`: `main.py:592-627`; full pipeline:
  `main.py:970-1017`) still build and loudly print a `dpcm_pack_warning`
  (`⚠️  NO DRUMS: ...`) rather than silently shipping a drumless build. The
  parallel→sequential pattern-detector fallback (`main.py:860-870`,
  `tracker/pattern_detector_parallel.py:164-182`) is unchanged and is still the
  documented graceful fallback, and per-chunk failures are recovered serially with a
  durable end-of-run warning for any length that's truly lost
  (`tracker/pattern_detector_parallel.py:163-188`, #106).
- **D2** — `mido.MidiFile` remains guarded in both parsers:
  `tracker/parser_fast.py:9-23` (`_open_midi_file`, `FileNotFoundError` re-raised,
  `(EOFError, OSError, ValueError)` → `InvalidMIDIError`) and `tracker/parser.py:11-16`.
  `nes/song_bank.py:add_song_from_midi` (`:72-89`) routes through
  `parse_midi_to_frames` and never calls `mido.MidiFile` directly. Whole-repo grep finds
  no unguarded call outside `tests/`. The per-event `except Exception as e: ... continue`
  in `parser_fast.py` (around the note-event loop) still counts and warns on drops
  instead of silently discarding them (#124).
- **D3** — `compiler/cc65_wrapper.py` unchanged byte-for-byte since 07-06:
  `check_toolchain()` (`:34-81`) resolves via `shutil.which` then probes the resolved
  path with `timeout=10`, raising `ToolchainError` on failure or a nonzero probe;
  `get_version()` (`:83-117`) guards its own probes the same way; `assemble()`/`link()`
  check `returncode != 0` and surface stderr/stdout via `CompilationError`, with
  `timeout=120`. The one `shell=True` in the repo (`compiler/compiler.py:92`) remains
  `# nosec B602`-annotated and gated by the SECURITY INVARIANT docstring in
  `mappers/base.py:143-161` (static compile-time constant only), backed by
  `tests/test_mappers.py:306-334`. No override found that interpolates a runtime value
  into the post-process snippet.
- **D4** — repo-wide grep for `eval(|exec(|yaml\.load\(|pickle\.load|os\.system` returns
  no matches anywhere. `shell=True` returns only the guarded
  `compiler/compiler.py:92` line (plus a doc comment and a test file mentioning the
  string). `config/config_manager.py:127` still uses `yaml.safe_load`.
- **D5** — `load_json_stage` (`main.py:64`) still gates all four inter-stage subcommand
  reads: `run_map` (`:106`, required key `events`), `run_frames` (`:117`),
  `run_export`'s patterns input (`:536`, required keys `patterns`/`references`), and
  `run_detect_patterns` (`:636`). Existence/parse/dict-type/required-key checks all
  intact.
- **D6** — `run_full_pipeline` still uses `with tempfile.TemporaryDirectory(prefix=
  "midi2nes_")` (`main.py:795`). Backup/restore is centralized:
  `_backup_existing_rom` (`:365-370`), `_restore_backup` (`:373-380`), invoked from a
  single `finally:` block (`:1104-1108` for the full pipeline, `:483-487` for
  `run_compile`) that fires only when `build_succeeded` is still `False`; on success the
  backup is explicitly `unlink(missing_ok=True)`d (`:1093-1094`, `:486-487`). No bare
  `open()` found outside a `with` statement in any pipeline-reachable path.
- **D7** — `ConfigManager._load_config` (`config/config_manager.py:108-118`) raises
  `ConfigurationError` for a given-but-missing `--config` path (#267/PL-07);
  `_load_from_file` (`:120-134`) catches only `(OSError, yaml.YAMLError)` →
  `ConfigurationError`. `save()`/`validate()` bare `ValueError` remains **Existing
  #222** (unchanged, still open).
- **D8** — `run_export` writes `args.output` via `export_tables_with_patterns` then
  appends DPCM in a separate guarded block, surfacing `⚠️  NO DRUMS` on failure
  (`main.py:629-631`); the full-pipeline DPCM block does the same and echoes the warning
  again in the final summary (`main.py:1086-1087`). ROM copy to the final path still
  happens only via `shutil.copy` at the end of `ROMCompiler.compile()`
  (`compiler/compiler.py:144`).

## Findings

### SAFE-14 (carried forward): `main.py:load_config` silently falls back to defaults on a missing config path
- **Severity**: LOW
- **Dimension**: Dead code / config-guard consistency (cross-refs Dimension 7)
- **Location**: `main.py:763-767`
- **Status**: NEW (first reported in `AUDIT_SAFETY_2026-07-06.md` as SAFE-14; never
  filed as a GitHub issue — no matching title found in `/tmp/audit/issues.json` — so it
  is carried forward here rather than referenced as `#NNN`)
- **Description**: The drum-mapper config helper still uses the pre-#267 idiom
  `if config_path and Path(config_path).exists(): return DrumMapperConfig.from_file(...)`
  — a `--config` path that is *given but does not exist* is treated identically to no
  path at all, silently returning built-in `DrumMapperConfig()` defaults. This is the
  same class of bug commit `f4a1f54` (#267) eliminated in
  `get_pattern_detection_caps`, and that `ConfigManager._load_config`
  (`config/config_manager.py:108-118`) now also rejects. Two mitigating facts still keep
  this LOW: (a) `load_config` has no production caller — grep across the repo finds it
  invoked only from `tests/test_main.py:1707,1715,1726,1737`, i.e. it is dead code not
  wired into any subcommand; and (b) its own test at `tests/test_main.py:1732-1739`
  (`test_load_config_missing_file`) still asserts the silent-fallback behavior, so any
  future wiring would inherit and lock in the anti-pattern.
- **Evidence**:
  ```python
  # main.py:763-767
  def load_config(config_path: Optional[str] = None) -> DrumMapperConfig:
      """Load drum mapper configuration from file or use defaults"""
      if config_path and Path(config_path).exists():
          return DrumMapperConfig.from_file(config_path)
      return DrumMapperConfig()
  ```
- **Impact**: None today (unreachable from any CLI subcommand). Latent: if a future
  `map`/drum subcommand wires `load_config` to a user-supplied `--config`, a typo'd path
  would silently use default drum mapping instead of the user's file — the exact "silent
  wrong output" class of bug the rest of the config-loading surface (`ConfigManager`,
  `get_pattern_detection_caps`) has been explicitly hardened against.
- **Related**: #267 (`get_pattern_detection_caps` missing-path guard); the analogous fix
  in `ConfigManager._load_config` (`config/config_manager.py:108-118`); `main.py:1100`
  area note that drum-mapper `--config` is intentionally unconsumed.
- **Suggested Fix**: Either delete `load_config` (and its three tests) as dead code, or —
  if intended for future use — change it to raise `ConfigurationError` for a
  given-but-missing path (matching `ConfigManager._load_config`) and update
  `tests/test_main.py:1737` to assert the raise rather than the silent fallback.

## Existing findings confirmed open (deduped, not re-filed)

- **#222 (SAFE-11)** — `ConfigManager.save()`/`validate()` raise bare `ValueError`
  (`config/config_manager.py:251,299`), Dimension 7. Open. LOW.
- **#223 (SAFE-12)** — bare `except:` in `debug/rom_tester.py:71` swallows all
  exceptions incl. `KeyboardInterrupt`, Dimension 1. Open. LOW.
- **#135 (TD-10)** — bare `except:` in `utils/profiling.py:120` (memory-sampler loop)
  swallows all errors incl. `KeyboardInterrupt`, Dimension 1. Open. LOW.

## Note on adjacent, out-of-scope changes

The working tree carries two uncommitted changes outside `main` at the time of this
audit — `arranger/voice_allocator.py` (clamps `arp_speed` to `>= 1` via a property
setter, #91/ARR-08, preventing a `ZeroDivisionError`) and `nes/envelope_processor.py`
(sets the length-counter halt bit, #167/NH-25). Both are defensive/correctness fixes
already tracked under the arranger and NES-hardware audit domains respectively, not new
safety-dimension findings (no error-handling, subprocess, or deserialization surface
touched), so they are not re-reported here.

---

_Next step:_

```
/audit-publish docs/audits/AUDIT_SAFETY_2026-07-18.md
```
