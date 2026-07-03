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
Hot spots to confirm: `run_full_pipeline` in `main.py` still wraps the entire 8-step
pipeline in one broad `try`/`except Exception as e` (`main.py:501`–`735`) that prints
the message and `sys.exit(1)`, without discriminating by exception type. This is less
concerning than it looks: every failure surface underneath now raises a specific,
informative typed exception (`InvalidMIDIError`, `ConfigurationError`, `ToolchainError`,
`CompilationError`, `ValidationError`) whose message this catch-all simply relays, so
the user-facing output is meaningful even though the `except` clause itself still can't
distinguish failure classes programmatically — still worth a LOW–MEDIUM finding
(defense-in-depth / testability), not a live "swallows a real bug" bug.
The DPCM-pack block (`main.py:625`–`676`, `try:` at `:627`, `except Exception as e:` at
`:667`) **no longer just warns and silently continues** — it builds a
`dpcm_pack_warning` string and prints it prominently (`⚠️ Warning: ...` at `:672`,
echoed again in the final success banner at `:725`–`726`) so a corrupt/partial
`dpcm_index.json` no longer ships a drumless ROM with an easy-to-miss message (fixed,
#123 — see Dimension 8 for the step-by-step `run_export` counterpart at
`main.py:317`–`345`, which got identical treatment). Verify: does the warning fire on
*every* path that can leave DPCM unpacked, or is there a code path inside the `try`
that could still exit early without setting `dpcm_pack_warning`? The parallel→sequential
fallback (`main.py:557`–`580`, catches bare `Exception` at `:562`) is unchanged
behavior (just line-shifted) — confirm it is still the *documented* fallback
(`_audit-common.md` Multiprocessing rule) and not masking a real bug, and that the
lossy-resample warning (`:573`–`579`) still fires whenever the fallback had to
downsample. Severity: swallowing on a recoverable/optional path = LOW–MEDIUM;
swallowing where the song is silently changed (dropped DPCM, dropped channel) escalates
per `_audit-severity.md`.

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
- No `shell=True` anywhere in the repo (confirmed via
  `grep -rnE 'shell=True' --include='*.py' .`) and every command is built as a list.
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
Current state: this grep returns **no matches anywhere in the repo** — confirmed
clean. Config loading uses `yaml.safe_load` (`config/config_manager.py:119`, line
shifted from the SAFE-08 fix's added comment) — **confirm it stays `safe_load`**; a
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

### Dimension 6: File / Resource Handling & Temp Cleanup
Check that file handles use context managers and temp dirs are cleaned up.
`run_full_pipeline` still correctly uses
`with tempfile.TemporaryDirectory(prefix="midi2nes_")` (`main.py:498`, line-shifted),
which auto-cleans — confirm nothing escapes it. All the named `open(...)` sites still
use `with`: the step-by-step DPCM append (`main.py:339`), the full-pipeline DPCM append
(`main.py:652`), the benchmark `open(results_file, 'w')` (`main.py:1080`), and
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
`exporter.export_tables_with_patterns(...)` (`main.py:301`–`308`) then **appends** DPCM
assembly in a separate `try` (`main.py:317`–`345`) — the structural risk is unchanged
(a DPCM-pack failure after the main write leaves an ASM file without the DPCM append),
but the consequence is now loudly surfaced — `⚠️  NO DRUMS: ...` (`main.py:348`–`349`)
— instead of a warning a user could scroll past, which meaningfully mitigates (if not
eliminates) the risk (#123). The full-pipeline DPCM block (`main.py:625`–`676`) got the
identical treatment, with the warning echoed again in the final summary
(`main.py:725`–`726`). Check the backup-restore on compile/validate failure: now
centralized in the single `finally` block described in Dimension 6
(`main.py:743`–`747`) rather than duplicated at multiple call sites — confirm it still
restores the prior good ROM and never leaves the broken one in place (it does). Flag
any writer that opens the final output path directly and can raise before completing
it (e.g. `exporter/exporter_ca65.py`'s `with open(output_path, 'w')` sites) as a
lower-priority hardening item if not already covered above.

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
