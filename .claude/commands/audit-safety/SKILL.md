---
description: "Audit Python robustness — error handling, input validation, subprocess and deserialization safety"
argument-hint: "[--focus <dims>]"
---

# Safety & Robustness Audit

Audit the **Python layer** for robustness and input safety — the failure modes that
turn a bad input or a missing tool into a confusing crash, a swallowed error, or a
half-written ROM. This is **not** a NES-hardware audit (that's `/audit-nes-hardware`);
the boundary here is "what happens when the Python pipeline meets hostile or broken
input, a missing toolchain, or a mid-pipeline failure."

Shared protocol: `.claude/commands/_audit-common.md` — read the **Python-Specific
Context Rules** there (error-handling, subprocess, inter-stage JSON drift) before
starting; they define the lens for every dimension below.
Severity: `.claude/commands/_audit-severity.md`. Key floors for this audit:
`eval`/`exec`/shell-injection on user input = **HIGH**; CC65 nonzero exit / stderr
ignored = **HIGH**; bare `except:` swallowing an error on a non-recoverable path =
**MEDIUM**.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 3,4`). Default: all.

## Extra Per-Finding Field
- **Dimension**: one of the 8 below.

## Dimensions

### Dimension 1: Swallowed-Error Handling
Find `except` blocks that hide a real failure on a path where the pipeline should
abort (and instead produces a broken or silently-wrong ROM). Grep:
```bash
grep -rnE 'except\s*:|except Exception' --include='*.py' main.py tracker/ nes/ exporter/ compiler/ config/
```
**#384/SAFE-2026-07-19-2 is CLOSED**: `run_full_pipeline` in `main.py` used to wrap the
entire 8-step pipeline in one broad `try`/`except Exception as e`, unable to
discriminate by exception type — a caller/test couldn't tell an expected typed error
apart from a genuinely unexpected defect. It now narrows into two clauses: `except
MIDI2NESError as e` (the typed base every failure surface underneath raises —
`InvalidMIDIError`, `ConfigurationError`, `ToolchainError`, `CompilationError`,
`ValidationError`, ...) prints `"[ERROR] Pipeline failed: ..."` unchanged, and a final
`except Exception as e` for anything else prints the distinct `"[ERROR] Unexpected
pipeline failure: ..."` (`main.py`, both clauses immediately after the `try` covering
the 8-step body, `finally:` restore-backup logic unchanged below both). Since #406,
three of the steps this wraps are extracted stage helpers (`detect_patterns_or_direct_export`,
`export_frames_and_resolve_mapper`, `build_and_validate_rom`, all defined just above
`run_full_pipeline`) that raise on failure rather than calling `sys.exit` themselves —
these two clauses are still the only place that decides how to report it. **Fixed
(#457/SAFE-2026-08-21-3, PIPE-2026-08-21-8/#428, verify)**: `build_and_validate_rom`
itself used to raise bare `RuntimeError` for prepare/compile/validate failure — three
ordinary, actionable outcomes (the most common trigger being a missing CC65 toolchain)
that misreported as "Unexpected pipeline failure" despite the clauses above already
existing. It now raises `ExportError`/`CompilationError`/`ValidationError` respectively
(matching `prepare_project`'s own `ExportError` type for its other failure mode).
`check_mapper_capacity`/`resolve_mapper`/`enforce_direct_export_dpcm_mapper` had the
same gap for their documented `ValueError` contract (not a `MIDI2NESError` subclass) —
fixed by making `MapperError` inherit from *both* `MIDI2NESError` and `ValueError`
(`core/exceptions.py`) rather than migrating every existing `except ValueError`/
`pytest.raises(ValueError)` call site, so both catch it. `compiler/compiler.py`'s
`compile_rom` also gained an explicit `except ToolchainError` clause — it used to catch
only `CompilationError`/`ValidationError` (whose comment claimed to "cover every
anticipated failure") and let a missing/vanished toolchain fall to the generic
`except Exception`. Verify-the-fix: confirm every raise site under `run_full_pipeline`
that is meant to be "expected" (not a defect) actually derives from `MIDI2NESError` — a
new failure surface that raises a bare `ValueError`/`RuntimeError` instead would silently
fall into the "Unexpected pipeline failure" branch even though it's a normal user-facing
error, which is a regression of this fix's intent, not a crash.
**#380/TD-28 is CLOSED**: the DPCM-pack block that used to be copy-pasted separately
into `run_export` and `run_full_pipeline` (and had already diverged — `run_export`
never passed `verbose=`) is now a single shared `pack_dpcm_into_asm(frames, asm_path,
*, verbose=False) -> DpcmPackResult` helper (`main.py:126`–`215`, `try:` at `:151`,
`except Exception as e:` at `:194`). It **still doesn't just warn and silently
continue** — a failure or a no-samples-resolved pack sets `DpcmPackResult.warning`,
which each call site prints prominently (`run_export` at `main.py:713`–`719`;
`export_frames_and_resolve_mapper` at `:1056`–`1057` — the stage helper
`run_full_pipeline` calls for this since #406 — echoed again in the final success
banner) so a
corrupt/partial `dpcm_index.json` no longer ships a drumless ROM with an easy-to-miss
message (fixed, #123). **#367/DP-DPCM-05 is CLOSED** on top of that: the warning used
to only fire on the all-missing case — a *partial* miss (some but not all referenced
samples resolve) produced no warning at all, so a song could ship with a silently
dropped drum. `pack_dpcm_into_asm` now distinguishes the two: both call sites label the
same `warning` string "NO DRUMS" when `loaded_samples == 0` and "PARTIAL DPCM MISS"
otherwise (`main.py:719` / `:1183`, mirrored at both sites so a fix to the label logic
in one can't silently miss the other now that it's one function). **#411/SAFE-2026-08-06-1
is CLOSED**: the missing-index case (`index_found=False`, `warning=None`) was the one gap
this parity didn't cover — `run_export` only ever checked `if dpcm_pack_warning:`, which
is `None` when the index is simply absent, so it printed nothing at all (identical output
to a genuinely drum-free song), while `run_full_pipeline` already branched on
`not pack_result.index_found` to print an info line. `run_export` now has the same branch
with matching wording ("No dpcm_index.json found, skipping DPCM packing."). Verify: does
the warning/info line fire on *every* path that can leave DPCM unpacked or partially
unpacked, or is there a code path inside the `try` that could still exit early without
setting `warning`? The parallel→sequential fallback (`main.py:1134`–`1160`, now inside
the extracted `detect_patterns_or_direct_export` helper; catches bare `Exception` at
`:1139`) is unchanged behavior (just relocated) — confirm it is still
the *documented* fallback (`_audit-common.md` Multiprocessing rule) and not masking a
real bug, and that the lossy-resample warning (`:1152`–`1159`) still fires whenever the
fallback had to downsample. Severity: swallowing on a recoverable/optional path =
LOW–MEDIUM; swallowing where the song is silently changed (dropped DPCM, dropped
channel) escalates per `_audit-severity.md`.

### Dimension 2: Malformed-Input Resilience
`mido.MidiFile(...)` is now **guarded** in both parsers (fixed, #121, commit
`c62bb56`): `tracker/parser_fast.py:15`–`20` and `tracker/parser.py:12`–`17` both wrap
the call — `FileNotFoundError` is re-raised as-is (a missing file, not a MIDI-validity
issue), while `(EOFError, OSError, ValueError)` is converted to `InvalidMIDIError`
(`core/exceptions.py:38`) so the user gets a clean message instead of a raw `mido`
traceback. `nes/song_bank.py` no longer calls `mido.MidiFile` directly at all — its
`add_song_from_midi` was switched to `tracker.parser_fast.parse_midi_to_frames`
(commit `d8f6a0e`, #33/#34), so it inherits the same guard for free. Verify fix
completeness: confirm no code path still constructs `mido.MidiFile` unguarded anywhere
in the repo (grep is the fastest check).
Inside `parser_fast.py`, the per-event `except Exception as e: ... continue`
(`tracker/parser_fast.py:126`) no longer silently drops a note event (fixed, #124,
SAFE-07 — see Dimension 1): it increments `dropped_note_events`, records
`last_drop_reason`, and prints a `Warning: dropped N note event(s)...` summary after
the track loop (`:137`–`140`). Verify edge cases the fix might not cover: this path is
documented as "defense against a future regression, not a known failure mode" — if an
audit or test run actually triggers a drop, treat it as a real bug to escalate (data
loss = at least HIGH per `_audit-severity.md`), not just a logged warning to accept.
`run_full_pipeline` still validates the input only via `Path.exists()`
(`main.py:471`) — unchanged; deeper content validation is now delegated to
`parse_fast`'s new `InvalidMIDIError` guard, which is a reasonable division of labor
(cheap existence check up front, real validation where the file is actually opened).
Grep for any other unguarded `mido.MidiFile` and `open(`/`read_text()` on
user-supplied paths as a final check.

### Dimension 3: Subprocess / CC65 Safety
`compiler/cc65_wrapper.py` shells out to `ca65`/`ld65`. Confirmed still correct — flag
any regression:
- The `ca65`/`ld65` invocations are all built as argv lists (no `shell=True`). The one
  deliberate `shell=True` in the repo is `ROMCompiler._run_post_process`
  (`compiler/compiler.py:92`, `# nosec B602`) — the mapper post-link fixup snippet is
  multi-line shell text, not an argv list, so it cannot be run without a shell. Its
  safety rests on the invariant (fixed, #263/SAFE-13) that
  `generate_post_process_commands` returns a **static compile-time constant** — see the
  SECURITY INVARIANT docstring in `mappers/base.py:143`–`161` and the regression test in
  `tests/test_mappers.py:306` that asserts every mapper returns a static `""` for both
  `is_windows` values. Flag any override that interpolates a runtime/user-derived value
  (project path, ROM name, song title) into that snippet as **HIGH** (shell injection).
- Missing-tool detection: `check_toolchain()` (`compiler/cc65_wrapper.py:34`–`81`) uses
  `shutil.which` + a `--version` probe via the *resolved* path (`:57`–`67` for ca65,
  `:69`–`79` for ld65) and raises `ToolchainError`. `get_version()` (`:83`–`117`) now
  guards its own probes the same way. Verify `assemble()`/`link()` are never reachable
  without `check_toolchain()` having run first: `ROMCompiler.compile()`
  (`compiler/compiler.py:94`) and `CC65Wrapper.build()`
  (`compiler/cc65_wrapper.py:238`–`272`, calls it at `:260`) both call it up front — a
  *direct* `assemble()`/`link()` call on a bare `CC65Wrapper` instance still would not,
  but nothing in `main.py`'s call paths does that (LOW, defense-in-depth only).
- Nonzero exit handling: `assemble()` (`:119`–`173`) and `link()` (`:175`–`236`) check
  `result.returncode != 0` and raise `CompilationError` with stderr/stdout (`:162`–`168`,
  `:225`–`231`). A path that drops the return code or stderr is still **HIGH**
  (`_audit-severity.md`: "CC65 nonzero exit / stderr ignored").
- Timeouts: **fixed** (#122, commit `c62bb56`). `subprocess.run` calls that previously
  had no `timeout` (the hung-assembler-hangs-the-CLI failure mode) now all pass one:
  `timeout=10` on the `--version` probes in `check_toolchain()`/`get_version()`, and
  `timeout=120` on the real `assemble()`/`link()` calls (`:153`, `:216`), each wrapped in
  `except subprocess.TimeoutExpired` that raises a clean `ToolchainError`/
  `CompilationError` instead of hanging. Verify edge cases: 120s is a fixed budget —
  confirm it's generous enough for the largest real projects the compiler handles, and
  that a legitimate slow build isn't misclassified as a hang.

### Dimension 4: Unsafe Deserialization (yaml / pickle / eval / exec)
```bash
grep -rnE 'eval\(|exec\(|yaml\.load\(|pickle\.load|os\.system|shell=True' --include='*.py' .
```
Current state: the only `shell=True` match is the documented, guarded mapper
post-process call at `compiler/compiler.py:92` (fixed, #263/SAFE-13 — see Dimension 3);
`eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system` return **no matches anywhere in
the repo** — confirmed clean. Config loading uses `yaml.safe_load`
(`config/config_manager.py:127`, line shifted from the SAFE-08 fix's added comment) —
**confirm it stays `safe_load`**; a
switch to `yaml.load` without `SafeLoader` on a user-supplied config would be HIGH
(arbitrary object construction). Flag any new `eval`/`exec` on user input (HIGH), any
`pickle.load` of attacker-influenceable data, and any multiprocessing path that pickles
untrusted args (cross-ref `_audit-common.md` Multiprocessing rule for
`ParallelPatternDetector` in `tracker/pattern_detector_parallel.py`).

### Dimension 5: JSON-Intermediate Guards
**Fixed** (#120, SAFE-01, commit `0a6f863`). A new `load_json_stage(path,
required_keys, stage_name)` helper (`main.py:36`–`65`) now guards every step-by-step
subcommand's inter-stage JSON read: existence (clean `[ERROR] ... input not found`
instead of a raw `FileNotFoundError`), parse errors (`json.JSONDecodeError` caught and
reported), a dict-type check, and a required-keys check — all exiting with a clear
message (including "is this the right stage's JSON?") and code 1 instead of a raw
traceback.
- `run_map` (`main.py:76`): `load_json_stage(args.input, ['events'], 'parse')` — the
  downstream `midi_data["events"]` access (`:80`) is now safe because `'events'` is a
  required key checked up front.
- `run_frames` (`main.py:87`): `load_json_stage(args.input, [], 'map')`.
- `run_export` (`main.py:276` for `args.input`; `main.py:284` for `args.patterns`,
  required keys `['patterns', 'references']`) — the downstream
  `pattern_data['patterns']`/`['references']` access (`:295`–`296`) is now guarded.
- `run_detect_patterns` (`main.py:354`).
Verify fix completeness: confirm every subcommand that reads inter-stage JSON goes
through `load_json_stage` (it currently does, across all four call sites above), and
flag any future subcommand that reverts to a bare `json.loads(...).read_text()`.

**A song bank is a JSON intermediate too, and it does not use this helper.**
`run_song_build` (`main.py:927`) reads the bank via `SongBank.import_bank` inside its own
`try/except Exception → [ERROR] ... sys.exit(1)` (`main.py:941-945`) rather than through
`load_json_stage`. Judge that on its merits rather than as an automatic finding — the
required-keys model doesn't fit a bank file — but do check the parts `load_json_stage`
would have covered: a bank that parses as JSON but isn't a dict, a `songs` entry missing
`metadata` (`main.py:953-954` does `['metadata'].get('order', 0)` with a **subscript**, not
`.get`), and the `except Exception` breadth (Dimension 7 — it will also swallow a
programming error inside `import_bank`, not just a bad file).

`midi_path` is the one field in that JSON that becomes a **filesystem read of an arbitrary
path** (`main.py:963-975`). Existence is checked (`:968-970`) with a clean error, which is
the important part; confirm the failure stays a clean exit for the realistic cases — a
relative path resolved against a different cwd than the one `song add` ran in, a path that
exists but isn't a MIDI file (it reaches `parse_midi_to_frames` and should surface as
`InvalidMIDIError` per Dimension 2, not a raw traceback), and a bank hand-edited to point
somewhere unexpected.

### Dimension 6: File / Resource Handling & Temp Cleanup
Check that file handles use context managers and temp dirs are cleaned up.
`run_full_pipeline` still correctly uses
`with tempfile.TemporaryDirectory(prefix="midi2nes_")` (`main.py:1292`, shifted again
by #406's stage-helper extraction above `run_full_pipeline` — re-check this number
after any future edit near the top of the file), which auto-cleans — confirm nothing
escapes it. All the named `open(...)` sites still
use `with`: the DPCM append inside the shared `pack_dpcm_into_asm` helper
(`main.py:168`, `open(asm_path, 'a')` — used by both `run_export` and
`run_full_pipeline` since #380/TD-28, see Dimension 1), the benchmark
`open(results_file, 'w')` (`main.py:1737`), and
`config/config_manager.py` `save()` (`:245`). No bare `open()` without `with` found in
these paths.
Backup/restore around `output_rom`: creation is at `main.py:482`–`486` (only when
`output_rom` already exists); restore is centralized in a `_restore_backup()` helper
(`main.py:166`–`171`) invoked from a single `finally:` block (`main.py:743`–`747`) that
fires whenever `build_succeeded` is still `False` (a `sys.exit(1)` inside the `try`
still unwinds through `finally`). On success the backup is explicitly deleted —
`backup_path.unlink(missing_ok=True)` (`main.py:732`–`733`) — so the `.nes.backup` is
**not** left behind on a successful run; it is only retained (to support a restore)
after a failed one. This resolves what was previously an open question — confirmed
correct as implemented.

### Dimension 7: Exception-Type Discipline
The project defines a typed hierarchy in `core/exceptions.py` (`MIDI2NESError` base;
`InvalidMIDIError`, `CompilationError`, `ValidationError`, `ToolchainError`,
`DataTooLargeError`, `ConfigurationError`, …). **Fixed** (#125, SAFE-08, commit
`de998dd`): `_load_from_file` in `config/config_manager.py:115`–`126` now catches only
the two expected failure classes, `(OSError, yaml.YAMLError)` — narrowed from a bare
`except Exception` — and raises `ConfigurationError(f"Failed to load configuration
from {path}: {e}")` instead of a generic `ValueError`. This is a double improvement:
callers can now distinguish a config-load failure by type, and a genuine unrelated bug
(e.g. a `TypeError` in later config processing) is no longer folded into the same
generic error — it now propagates as itself. Cross-ref Dimension 2: parsers now raise
the typed `InvalidMIDIError` instead of a raw `mido` error (also fixed, #121).
Verify fix completeness / remaining edge cases: `save()`
(`config/config_manager.py:241`) still raises a bare `ValueError("No path specified for
saving configuration")`, and `validate()` (`:280`) still raises a bare `ValueError` on
validation failure — neither was in scope of #125 (which covered *load* failures only)
but both remain a LOW opportunity to align with `ConfigurationError`/`ValidationError`
for consistency with the rest of the module. Severity: usually LOW–MEDIUM
(defense-in-depth / maintainability) unless the wrong type causes a real failure to be
swallowed.

### Dimension 8: Partial-Output-on-Failure
A pipeline that fails mid-way must not leave a half-written `.nes` / `.asm` that a user
mistakes for a good build. `run_full_pipeline` still builds the ROM inside the temp dir
and only reaches the final path via `shutil.copy(rom_path, output_path)` in
`ROMCompiler.compile()` (`compiler/compiler.py:144`) — unchanged, still the safe
pattern. Check the subcommand exporters: `run_export` writes `args.output` via
`exporter.export_tables_with_patterns(...)` (`main.py:697`–`704`) then **appends** DPCM
assembly via the shared `pack_dpcm_into_asm` helper (`main.py:709`–`711`; extracted
from a separate inline `try` in #380/TD-28, see Dimension 1) — the structural risk is
unchanged (a DPCM-pack failure after the main write leaves an ASM file without the
DPCM append), but the consequence is loudly surfaced — `⚠️  NO DRUMS: ...` or
`⚠️  PARTIAL DPCM MISS: ...` (`main.py:714`–`720`, label chosen per #367/DP-DPCM-05,
see Dimension 1) — instead of a warning a user could scroll past, which meaningfully
mitigates (if not eliminates) the risk (#123). `run_full_pipeline`'s DPCM step
(`main.py:1234`–`1246`, inside the extracted `export_frames_and_resolve_mapper`
helper) goes through the identical helper now (not a second
hand-written block), with the warning echoed again in the final summary. Check the
backup-restore on compile/validate failure: now
centralized in the single `finally` block described in Dimension 6
(`main.py:743`–`747`) rather than duplicated at multiple call sites — confirm it still
restores the prior good ROM and never leaves the broken one in place (it does).
**#385/SAFE-2026-07-19-3 is CLOSED**: `exporter/exporter_ca65.py`'s two final-output
writers (`export_direct_frames`, `export_tables_with_patterns`) used to open the
final output path directly (`with open(output_path, 'w') as f: f.write(...)`), so a
failed write (disk full, killed process) could leave a truncated `.asm` at the user's
output path, or overwrite a prior good file with a partial one on a re-export. Both
now go through a shared `atomic_write_text(output_path, content)` helper — moved to
`core/io_utils.py` by #456/SAFE-2026-08-21-2 (still re-exported from
`exporter/base_exporter.py` for existing imports, so `from exporter.base_exporter
import atomic_write_text` keeps working unchanged): it writes to a sibling temp file
in the same directory and `os.replace()`s it into place, so a reader only ever sees
the old complete file or the new complete file, never a partial one; on failure the
temp file is removed and `output_path` is left untouched. The sibling
`exporter/exporter_famistudio.py` writers (`FamiStudioExporter.export`,
`export_famistudio`) were switched to the same helper for consistency, even though
that format is not currently reachable from the CLI (`--format` only accepts `ca65`,
main.py). **#456/SAFE-2026-08-21-2 is CLOSED**: this was exactly the gap the
verify-the-fix note below already anticipated — `nes/song_bank.py`'s
`SongBank.export_bank` (the *cumulative* `song_bank.json`, built up across many
`song add`/`song remove` runs, unlike a regenerable intermediate JSON) was a direct
`Path(output_path).write_text(...)`, left out of the original #385 sweep since it
isn't in `exporter/`. It now uses the same `atomic_write_text` (imported from
`core.io_utils` directly, avoiding a `nes` → `exporter` reverse dependency).
Verify-the-fix: flag any *new* writer that opens a final output path directly with
`open(...)`/`Path(...).write_text(...)` instead of `atomic_write_text` — that's a
regression of this exact pattern, not a new bug. Cross-ref `run_song_add`/
`run_song_remove` (`main.py`) as the two callers of `export_bank` that benefit.

## Cross-Dimension Dedup
One root cause can surface across dimensions (the unguarded `json.loads` is both a
JSON-guard gap (D5) and a partial-output risk (D8); the parser `mido.MidiFile` call is
both malformed-input (D2) and exception-type (D7)). Report it once in the most
actionable dimension and cross-reference.

## Skeptical Checklist
- Did you actually grep `eval(`/`exec(`/`shell=True`/`yaml.load(`/`pickle.load` across
  the **whole** repo (not just the files named here) before claiming none exist?
- For each "swallowed error" finding: is the path truly non-recoverable, or is this the
  *documented* graceful fallback? Re-read before flagging.
- For each CC65 finding: trace the exact call path — is the unsafe `assemble()`/`link()`
  call reachable without `check_toolchain()` having run?
- For each JSON finding: confirm the consumer's key access, not just the `json.loads`
  line, and tie it to the inter-stage contract in `_audit-common.md`.
- Before reporting, run the **Deduplication** steps in `_audit-common.md` (gh issue list
  + scan `docs/audits/`).

## Output
Write the report to: **`docs/audits/AUDIT_SAFETY_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — finding counts per severity and per dimension; the 3 highest-leverage
   robustness fixes.
2. **Findings** — base per-finding format from `_audit-common.md` plus the `Dimension`
   field.

Then suggest:
```
/audit-publish docs/audits/AUDIT_SAFETY_<TODAY>.md
```
</content>
