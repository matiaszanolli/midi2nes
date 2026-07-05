# Safety & Robustness Audit — 2026-07-05

Audit of the Python layer for robustness and input safety (error handling, input
validation, subprocess/CC65 safety, unsafe deserialization, JSON-intermediate guards,
file/resource handling, exception-type discipline, partial-output-on-failure).

- **Scope**: `main.py`, `tracker/parser_fast.py`, `tracker/parser.py`,
  `tracker/pattern_detector_parallel.py`, `compiler/compiler.py`,
  `compiler/cc65_wrapper.py`, `config/config_manager.py`, `core/exceptions.py`,
  `nes/song_bank.py`, `mappers/*.py`.
- **Method**: Whole-repo greps for `eval(`/`exec(`/`yaml.load(`/`pickle.load`/
  `os.system`/`shell=True`/bare `except`/`subprocess.run`, plus live-tree re-reads of
  every code path the `audit-safety` skill flags as "fixed". Deduped against
  `/tmp/audit/issues.json` (36 open issues) and prior reports
  `AUDIT_SAFETY_2026-06-29.md`, `AUDIT_SAFETY_2026-07-03.md`, and today's
  `AUDIT_MAPPERS_2026-07-05.md`.

## Summary

### Finding counts by severity
| Severity | New | Existing (open, noted) |
|----------|-----|------------------------|
| CRITICAL | 0 | 0 |
| HIGH     | 0 | 0 |
| MEDIUM   | 1 | 0 |
| LOW      | 0 | 3 |
| **Total new** | **1** | 3 |

### Counts by dimension (new findings)
| Dim | Area | New |
|-----|------|-----|
| 1 | Swallowed-error handling | 0 |
| 2 | Malformed-input resilience | 0 |
| 3 | Subprocess / CC65 safety | 1 (SAFE-13) |
| 4 | Unsafe deserialization | (SAFE-13 cross-ref) |
| 5 | JSON-intermediate guards | 0 |
| 6 | File / resource / temp cleanup | 0 |
| 7 | Exception-type discipline | 0 (Existing #222) |
| 8 | Partial-output-on-failure | 0 |

### Three highest-leverage robustness items
1. **SAFE-13** — the newly-introduced `shell=True` in `ROMCompiler._run_post_process`
   breaks the "no `shell=True` anywhere in the repo" invariant that both prior safety
   audits asserted. Harmless today (no user input reaches it), but it is a latent
   shell-injection surface the moment any mapper interpolates a user-controlled value
   into its post-process commands.
2. **Existing #222 (SAFE-11)** — `ConfigManager.save()`/`validate()` still raise bare
   `ValueError` instead of typed `ConfigurationError`/`ValidationError`. Already filed.
3. **Existing #223 (SAFE-12) / #135 (TD-10)** — bare `except:` in debug/benchmark and
   `utils/profiling.py` tooling swallows `KeyboardInterrupt`. Already filed.

### State of prior "fixed" claims (all re-verified this run)
- **D1** — `run_full_pipeline`'s broad `except Exception` relays typed exceptions;
  the DPCM-pack block sets `dpcm_pack_warning` and echoes `⚠️ NO DRUMS` in both
  `run_export` (`main.py:487-494`) and the full pipeline (`main.py:853-937`). The
  parallel→serial fallback (`tracker/pattern_detector_parallel.py:164-167`) is the
  documented graceful fallback. **Confirmed intact.**
- **D2** — `mido.MidiFile` is guarded in both parsers; `parser_fast` now routes both
  opens through a shared `_open_midi_file` helper (`tracker/parser_fast.py:10-24`,
  #221/SAFE-10). No unguarded `mido.MidiFile` remains outside tests. The per-event drop
  counts and warns (`parser_fast.py:139-148`). **Confirmed intact.**
- **D3** — `cc65_wrapper` has `timeout=` on every `subprocess.run` (10s probes, 120s
  assemble/link), checks `returncode != 0`, surfaces stderr, and probes resolved
  `shutil.which` paths. See SAFE-13 for the one regression against the "no `shell=True`"
  invariant.
- **D4** — whole-repo grep for `eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system`
  returns no matches; `config/config_manager.py:121` still uses `yaml.safe_load`.
  `shell=True` now returns **one** match — see SAFE-13.
- **D5** — all four inter-stage subcommand reads go through `load_json_stage`
  (`main.py:98,109,417,425,499`). `SongBank.import_bank` guards existence/parse/keys
  (`nes/song_bank.py:186-201`, #220/SAFE-09 — fixed). **Confirmed intact.**
- **D6** — `run_full_pipeline` uses `tempfile.TemporaryDirectory`; final ROM is written
  only via `shutil.copy(rom_path, output_path)` at the very end of `compile()`
  (`compiler/compiler.py:212`). Backup/restore centralized in `_backup_existing_rom`/
  `_restore_backup` (`main.py:250-278`), now also wired into `run_compile`
  (`main.py:357-376`). **Confirmed intact.**
- **D7** — `_load_from_file` catches only `(OSError, yaml.YAMLError)` and raises
  `ConfigurationError`. `save()`/`validate()` bare `ValueError` is **Existing #222**.
- **D8** — post-process runs before the final copy (`compiler/compiler.py:183-212`), so a
  post-process failure raises before any output is written; `_restore_backup` moves a
  first-time unbootable ROM aside to `<name>.nes.failed`
  (`main.py:275-278`). **Confirmed intact.**

## Findings

### SAFE-13: `ROMCompiler._run_post_process` uses `shell=True`, breaking the repo's "no shell=True" invariant
- **Severity**: MEDIUM
- **Dimension**: 3 (Subprocess / CC65 Safety); cross-refs 4 (unsafe-pattern grep)
- **Location**: `compiler/compiler.py:82-89` (call), `compiler/compiler.py:183-189`
  (call site), `mappers/base.py:129-138` (source of `commands`)
- **Status**: NEW (regression against the invariant asserted by
  `AUDIT_SAFETY_2026-06-29.md` and `AUDIT_SAFETY_2026-07-03.md`; the code itself is
  #214/MAP-3, added after 2026-07-03)
- **Description**: The mapper post-link fixup step introduced by #214/MAP-3 runs its
  command snippet with `subprocess.run(commands, shell=True, ...)`. This is the first
  and only `shell=True` in the repo — both prior safety audits explicitly certified
  "no `shell=True` anywhere," and today's `AUDIT_MAPPERS_2026-07-05.md` verified MAP-3
  only from the correctness angle ("post-process now runs"), not as a subprocess-safety
  surface. Today the call is benign: `commands` comes from
  `mapper.generate_post_process_commands(is_windows)`, whose base implementation returns
  `""` and which **no** shipped mapper (NROM/MMC1/MMC3) overrides with non-empty content,
  so the guarded `if post_process:` block at `compiler.py:186` never executes a non-empty
  string; and `working_dir` is passed as `cwd=`, never interpolated into the command
  text. So there is no user input on this path right now.
- **Evidence**:
  ```python
  # compiler/compiler.py:81-89
  result = subprocess.run(
      commands,
      shell=True,
      cwd=working_dir,
      capture_output=True,
      text=True,
      timeout=60,
  )
  ```
  ```python
  # mappers/base.py:129-138 — base returns "", no shipped mapper overrides with content
  def generate_post_process_commands(self, is_windows: bool = False) -> str:
      return ""
  ```
- **Impact**: No live exploit. The concern is latent and forward-looking: the design
  intent (mirror `build.sh`, which some future mapper's vector-fixup step may need) means
  a maintainer adding a mapper that builds a post-process command by interpolating a
  user-influenced value — a project path, output ROM name, or song title — would create a
  silent shell-injection vector with no guard, on a code path no test currently exercises
  (no mapper returns non-empty commands, so `_run_post_process` is effectively dead but
  present). Blast radius: the `compile`/full-pipeline build step on whatever mapper adds
  such a command.
- **Related**: #214/MAP-3 (introduced the path); `AUDIT_MAPPERS_2026-07-05.md` MAP-3
  (verified correctness only); prior "no `shell=True`" certifications in
  `AUDIT_SAFETY_2026-06-29.md` §D4 and `AUDIT_SAFETY_2026-07-03.md` §D3/D4.
- **Suggested Fix**: Since the return-code/stderr/timeout handling is already correct,
  the minimal hardening is to (a) document the invariant that
  `generate_post_process_commands` must only ever return static, non-user-derived text,
  and (b) prefer running the snippet as an argument list (or via `shlex.split` for the
  single-line cases) rather than `shell=True`. If genuine multi-line shell scripting is
  required for a future mapper, keep `shell=True` but add an explicit assertion/comment
  that `commands` is a compile-time constant, and add a test that fails if any mapper's
  post-process output contains an interpolated runtime value.

## Existing findings confirmed open (deduped, not re-filed)

- **#222 (SAFE-11)** — `ConfigManager.save()`/`validate()` raise bare `ValueError`
  (Dimension 7). Open. Matches the skill's D7 "LOW opportunity" note.
- **#223 (SAFE-12)** — bare `except:` in debug/benchmark tooling swallows all exceptions
  incl. `KeyboardInterrupt` (Dimension 1). Open.
- **#135 (TD-10)** — bare `except:` in `utils/profiling.py` (Dimension 1). Open.

---

_Next step:_

```
/audit-publish docs/audits/AUDIT_SAFETY_2026-07-05.md
```
