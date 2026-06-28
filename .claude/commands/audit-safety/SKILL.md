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
Hot spots to confirm: `run_full_pipeline` in `main.py` wraps the entire 8-step pipeline
in one broad `except Exception as e` (`main.py:488`) that only prints + `sys.exit(1)` —
distinguishes nothing between an `InvalidMIDIError` and a real bug. The DPCM-pack block
(`main.py:374`–`411`) catches everything and continues with `print(... Warning ...)`,
so a corrupt `dpcm_index.json` yields a ROM missing its drums with no failure. The
parallel→sequential fallback at `main.py:314`–`327` catches bare `Exception` — verify
it is the *documented* fallback (`_audit-common.md` Multiprocessing rule) and not
masking a real bug. Severity: swallowing on a recoverable/optional path = LOW–MEDIUM;
swallowing where the song is silently changed (dropped DPCM, dropped channel) escalates
per `_audit-severity.md`.

### Dimension 2: Malformed-Input Resilience
Both parsers call `mido.MidiFile(...)` with **no guard** — `tracker/parser_fast.py:14`
and `tracker/parser.py:11`. A truncated, empty, or non-MIDI file raises a raw `mido`
exception / `OSError` / `EOFError` / `EOFError`-wrapped error, not the project's
`InvalidMIDIError` (defined in `core/exceptions.py`), so the user sees a stack trace
instead of a clean message. Inside `parser_fast.py`, the per-event `except Exception:
continue` (`tracker/parser_fast.py:77`) silently drops any note event that fails frame
conversion — confirm whether a dropped `note_on`/`note_off` can change the song (data
loss → escalate). Check that `run_full_pipeline` validates the input is a real MIDI
file beyond `Path.exists()` (`main.py:232`). Grep for other unguarded `mido.MidiFile`
and `open(`/`read_text()` on user-supplied paths.

### Dimension 3: Subprocess / CC65 Safety
`compiler/cc65_wrapper.py` shells out to `ca65`/`ld65`. Confirm (currently looks
correct — verify it stays correct, and flag any regression):
- No `shell=True` and the command is a list, not a string (no shell-injection surface).
- Missing-tool detection: `check_toolchain()` (`compiler/cc65_wrapper.py:34`) uses
  `shutil.which` + `--version` and raises `ToolchainError`. Verify `assemble()` /
  `link()` are never reachable without `check_toolchain()` first — `build()`
  (`compiler/cc65_wrapper.py:207`) calls it, but a direct `assemble()` call does not.
- Nonzero exit handling: `assemble()` (`:139`) and `link()` (`:194`) check
  `result.returncode != 0` and raise `CompilationError` with stderr. A path that drops
  the return code or stderr is **HIGH** (`_audit-severity.md`: "CC65 nonzero exit /
  stderr ignored"). Also check `subprocess.run` calls that omit a `timeout` (a hung
  assembler hangs the whole CLI) and the `--version` probes at `:55`/`:66` that ignore
  a nonzero return without surfacing stderr.

### Dimension 4: Unsafe Deserialization (yaml / pickle / eval / exec)
```bash
grep -rnE 'eval\(|exec\(|yaml\.load\(|pickle\.load|os\.system|shell=True' --include='*.py' .
```
Current state: config loading uses `yaml.safe_load` (`config/config_manager.py:117`) —
**confirm it stays `safe_load`**; a switch to `yaml.load` without `SafeLoader` on a
user-supplied config is HIGH (arbitrary object construction). Flag any new `eval`/`exec`
on user input (HIGH), any `pickle.load` of attacker-influenceable data, and any
multiprocessing path that pickles untrusted args (cross-ref `_audit-common.md`
Multiprocessing rule for `ParallelPatternDetector` in
`tracker/pattern_detector_parallel.py`).

### Dimension 5: JSON-Intermediate Guards
Every pipeline stage round-trips JSON. The subcommand entry points read user-supplied
paths with **no existence check and no parse guard**: `run_map` (`main.py:41`),
`run_frames` (`main.py:49`), `run_export` (`main.py:67` and `:72` for `--patterns`),
`run_detect_patterns` (`main.py:126`) all do `json.loads(Path(args.input).read_text())`
bare — a missing file raises `FileNotFoundError`, a truncated/garbage file raises
`json.JSONDecodeError`, both as raw tracebacks. Also check **key access** after load:
`run_map` does `midi_data["events"]` and `run_export` does `pattern_data['patterns']` /
`['references']` (`main.py:89`) with no `KeyError` guard — a stage fed the wrong JSON
(an inter-stage contract break per `_audit-common.md`) crashes with `KeyError` rather
than a clear "this isn't a patterns file" message.

### Dimension 6: File / Resource Handling & Temp Cleanup
Check that file handles use context managers and temp dirs are cleaned up.
`run_full_pipeline` correctly uses `with tempfile.TemporaryDirectory(...)`
(`main.py:258`), which auto-cleans — confirm nothing escapes it. Verify `open(...)`
sites use `with` (e.g. the DPCM `open(music_asm, 'a')` at `main.py:403`, the
benchmark `open(results_file, 'w')` at `main.py:793`, and `config/config_manager.py`
`save()` at `:238`). Flag any bare `open()` without `with` that can leak a handle on
exception. Note the backup/restore dance around `output_rom` (`main.py:244`–`247`,
`:436`–`439`, `:463`–`466`) — confirm the `.nes.backup` is removed on success (search
for cleanup; if it is left behind on every run, that is a resource/cleanliness LOW).

### Dimension 7: Exception-Type Discipline
The project defines a typed hierarchy in `core/exceptions.py` (`MIDI2NESError` base;
`InvalidMIDIError`, `CompilationError`, `ValidationError`, `ToolchainError`,
`DataTooLargeError`, `ConfigurationError`, …). Flag code that raises bare `Exception`/
`ValueError` where a typed exception exists, or catches broad `Exception` where it
could catch a specific subclass and let real bugs propagate. Example: `_load_from_file`
in `config/config_manager.py:118` catches `Exception` and re-raises as a generic
`ValueError` instead of the available `ConfigurationError` — callers can't distinguish a
missing file from malformed YAML. Cross-ref Dimension 2 (parsers raising raw `mido`
errors instead of `InvalidMIDIError`). Severity: usually LOW–MEDIUM (defense-in-depth /
maintainability) unless the wrong type causes a real failure to be swallowed.

### Dimension 8: Partial-Output-on-Failure
A pipeline that fails mid-way must not leave a half-written `.nes` / `.asm` that a user
mistakes for a good build. `run_full_pipeline` builds the ROM inside the temp dir and
only `shutil.copy(...)` to the final `output_path` on success (`compiler/compiler.py:144`),
which is the safe pattern — **verify** no stage writes directly to `args.output` before
the final step. Check the subcommand exporters: `run_export` writes `args.output` then
**appends** DPCM assembly in a separate `try` (`main.py:118`) — if the append fails after
the main write, a partial/truncated `.asm` is left with only a warning. Check the
backup-restore on compile/validate failure (`main.py:436`, `:463`) actually restores the
prior good ROM and does not leave the broken one. Flag any writer that opens the final
output path, then can raise before completing it.

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
