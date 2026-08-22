# Safety & Robustness Audit — 2026-08-21

**Scope**: Python-layer robustness per `.claude/commands/audit-safety/SKILL.md` (all 8
dimensions), shared protocol per `.claude/commands/_audit-common.md`, severity per
`.claude/commands/_audit-severity.md`.

**Method**: repo-wide greps (`eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system`/
`shell=True`, broad `except`, unguarded `mido.MidiFile`, non-`with` `open(`,
final-output `write_text`), line-by-line re-verification of every fix the skill marks
CLOSED, and empirical CLI reproduction for the two behavioral findings (corrupt-MIDI
`song add`, wrong-stage JSON). Dedup: `gh issue list` (200 most recent; **0 open
issues**) saved to `/tmp/audit/issues.json`, plus all `docs/audits/*2026-08*` reports
including today's sibling `AUDIT_PIPELINE_2026-08-21.md`.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 4 (2 NEW, 2 Existing carried from AUDIT_SAFETY_2026-08-07, re-verified unfixed) |
| LOW      | 1 (NEW) |

| Dimension | Findings |
|-----------|----------|
| D1 Swallowed errors | 1 (SAFE-2026-08-21-5, Existing) |
| D2 Malformed input  | 2 (SAFE-2026-08-21-1 NEW, SAFE-2026-08-21-4 Existing) |
| D3 Subprocess/CC65  | 0 — verified clean |
| D4 Unsafe deserialization | 0 — verified clean |
| D5 JSON guards      | 0 new (two live defects dedup'd to sibling pipeline report, see below) |
| D6 File/temp handling | 0 — verified clean |
| D7 Exception discipline | 1 (SAFE-2026-08-21-3, NEW LOW) |
| D8 Partial output   | 1 (SAFE-2026-08-21-2, NEW) |

### Three highest-leverage robustness fixes
1. **Wrap `run_song_add`'s parse/add/save sequence in the same typed-error guard every
   sibling subcommand already has** (SAFE-2026-08-21-1) — one `try/except (MIDI2NESError,
   FileNotFoundError, ValueError)` fixes three raw-traceback classes at once, and the
   same clause added around `run_song_build`'s per-song parse retires
   SAFE-2026-08-07-2 (SAFE-2026-08-21-4) too.
2. **Make `SongBank.export_bank` atomic** (SAFE-2026-08-21-2) — reuse
   `exporter/base_exporter.py:atomic_write_text`; the bank JSON is the only cumulative,
   irreplaceable user artifact the project rewrites in place.
3. **Give `run_song_build` the backup/restore + exception net the default path has** —
   owned by sibling finding PIPE-2026-08-21-4 (verified live this pass); fixing it also
   subsumes the unguarded `prepare_project` call (SAFE-2026-08-21-5).

## Findings

### SAFE-2026-08-21-1: `song add` crashes with a raw traceback on a corrupt or missing input MIDI, a duplicate song name, or a full bank — the only song-bank subcommand with no guard around its real work
- **Severity**: MEDIUM
- **Dimension**: 2 (Malformed-Input Resilience); cross-ref D7 (the raised types are
  already the right typed exceptions — nothing catches them)
- **Location**: `main.py:799-827` (`run_song_add`; unguarded `bank.add_song_from_midi`
  at `:822`, unguarded `bank.export_bank` at `:826`); raisers:
  `tracker/parser_fast.py:16-21` (`InvalidMIDIError`/`FileNotFoundError`),
  `nes/song_bank.py:124` (`ValueError: Song '...' already exists`),
  `nes/song_bank.py:142`/`:160` (`ValueError: Not enough bank space` / `No available
  bank space`)
- **Status**: NEW — #220/SAFE-09 (closed) guarded only the **bank-JSON load** side of
  the `song` family (`import_bank` + the three `try/except` blocks at `main.py:807-811`,
  `:836-840`, `:863-867`); no prior report covers the MIDI-input/add/save side of
  `run_song_add`. AUDIT_SAFETY_2026-08-06's D5 note ("run_song_add/list/remove
  independently guard the song-bank JSON family") is true only for `import_bank`.
- **Description**: `run_song_add` guards loading an existing `--bank` file, then calls
  `bank.add_song_from_midi(args.input, ...)` and `bank.export_bank(...)` with no
  exception handling at all, and `main()`'s dispatch (`args.func(args)`,
  `main.py:1655`) has no outer net. Every documented failure mode of those two calls —
  a non-MIDI input file, a missing input file, re-adding an existing song name, a bank
  with no remaining space — escapes as an uncaught exception and a raw traceback,
  even though three of the four already raise clean typed messages
  (`InvalidMIDIError`, `ValueError`). Every sibling subcommand (`parse` via the #121
  guard's *caught* path in the pipeline, `map`/`frames`/`export`/`detect-patterns` via
  `load_json_stage`, `song list|remove|build` via their `import_bank` guards) converts
  these to `[ERROR] ...` + exit 1.
- **Evidence**: reproduced live this pass:
  ```
  $ printf 'not a midi file' > bad.mid
  $ python3 main.py song add bad.mid --bank bank.json --name test
  Traceback (most recent call last):
    ...
    File "tracker/parser_fast.py", line 21, in _open_midi_file
      raise InvalidMIDIError(str(midi_path), str(e)) from e
  core.exceptions.InvalidMIDIError: Invalid MIDI file: .../bad.mid: MThd not found. Probably not a MIDI file
  ```
  Duplicate-name and bank-full paths confirmed by code read: `add_song`
  (`nes/song_bank.py:113-142`) raises bare `ValueError` for both; nothing between it
  and `sys.excepthook` catches anything.
- **Impact**: `song add` is the entry point of the whole jukebox chain (#30/F-13); the
  most ordinary user errors (typo'd path, wrong file, adding the same song twice)
  produce a stack trace instead of the actionable one-line message the exceptions
  already carry. Exit code is 1 either way, so scripts are unaffected; humans get the
  worst UX in the CLI.
- **Related**: #220/SAFE-09 (the bank-load half of this fix), SAFE-2026-08-07-2 /
  SAFE-2026-08-21-4 (identical defect class in `run_song_build`'s per-song parse),
  #121/SAFE-02 (the parser guard whose typed error goes to waste here)
- **Suggested Fix**: Wrap `:813-827` in `try/except (MIDI2NESError, FileNotFoundError,
  ValueError) as e: print(f"[ERROR] {e}"); sys.exit(1)`, matching the `import_bank`
  guard three lines above.

### SAFE-2026-08-21-2: `SongBank.export_bank` rewrites the user's cumulative bank JSON in place non-atomically — a failed write during `song add`/`song remove` can destroy the only copy of the bank
- **Severity**: MEDIUM
- **Dimension**: 8 (Partial-Output-on-Failure)
- **Location**: `nes/song_bank.py:187-198` (`Path(output_path).write_text(...)` at
  `:198`); writers: `run_song_add` (`main.py:826`), `run_song_remove` (`main.py:874`)
- **Status**: NEW — no prior report or issue mentions `export_bank` atomicity
  (grepped `docs/audits/*.md` + `/tmp/audit/issues.json`); #385/SAFE-2026-07-19-3
  (closed) fixed exactly this pattern but scoped only to `exporter/` final-output
  writers.
- **Description**: Unlike a `music.asm` or intermediate JSON — regenerable from the
  MIDI in one command — `song_bank.json` is *cumulative* state built up across many
  `song add` runs, and both `song add` and `song remove` overwrite it **in place**
  via a plain `write_text`. A disk-full, quota, or kill mid-write leaves a truncated
  file where the previous good bank was; `import_bank`'s #220 guard will then cleanly
  *reject* it, but the data is already gone and every song must be re-added. The repo
  already solved this failure mode with `atomic_write_text`
  (`exporter/base_exporter.py:22` — sibling temp file + `os.replace`), applied to all
  three CA65 writers and both FamiStudio writers; the highest-value persistent file
  was left out.
- **Evidence**: `nes/song_bank.py:198` is a direct `write_text` on the final path;
  `grep -rn atomic_write_text nes/` → no matches. Contrast
  `exporter/exporter_ca65.py:999/:1532/:1672`.
- **Impact**: Low-probability event, but the blast radius is the user's entire song
  bank (irreplaceable if the source MIDIs' recorded `midi_path`s have since moved),
  and the two commands that trigger it are exactly the ones a user runs most often on
  a bank they care about.
- **Related**: #385/SAFE-2026-07-19-3 (same pattern, exporters), #220/SAFE-09 (the
  read-side guard that makes the corruption *visible* but not *recoverable*)
- **Suggested Fix**: `from exporter.base_exporter import atomic_write_text` (or move
  the helper to `core/`/`utils/` to avoid nes→exporter coupling) and replace `:198`
  with `atomic_write_text(output_path, json.dumps(bank_data, indent=2))`.

### SAFE-2026-08-21-3: Expected prepare/compile/validate failures (including a missing CC65 toolchain) are labeled "Unexpected pipeline failure" — the untyped-raiser list is wider than PIPE-2026-08-21-8 records
- **Severity**: LOW
- **Dimension**: 7 (Exception-Type Discipline)
- **Location**: `main.py:1281`, `:1285`, `:1290` (`build_and_validate_rom` raises bare
  `RuntimeError` for prepare/compile/validate failure); `main.py:1446-1454` (the
  `except Exception` branch that prints "Unexpected pipeline failure");
  `compiler/compiler.py:286-303` (`compile_rom` catches
  `CompilationError`/`ValidationError` but **not** `ToolchainError`, so a missing
  toolchain falls into its generic `except Exception` whose comment claims the typed
  clauses "cover every anticipated failure"); `core/exceptions.py:158`
  (`ToolchainError(MIDI2NESError)` — a sibling of, not a subclass of,
  `CompilationError`)
- **Status**: NEW — extends sibling finding PIPE-2026-08-21-8
  (`docs/audits/AUDIT_PIPELINE_2026-08-21.md`), which documents the same #384
  intent-regression but lists only the `ValueError` raisers
  (`check_mapper_capacity`/`resolve_mapper`). A fix scoped to that finding's raiser
  list would miss the three `RuntimeError` sites and the `ToolchainError` routing.
- **Description**: #384/SAFE-2026-07-19-2 split `run_full_pipeline`'s reporting into
  `except MIDI2NESError` ("expected, actionable") vs `except Exception` ("genuinely
  unexpected defect"). The skill's verify-the-fix step asks whether every *expected*
  raise site under `run_full_pipeline` derives from `MIDI2NESError`. Three do not:
  `build_and_validate_rom`'s documented failure contract is bare `RuntimeError`, so
  "Failed to prepare NES project", "ROM compilation failed", and "ROM validation
  failed" — all ordinary, user-facing outcomes — print as `[ERROR] Unexpected
  pipeline failure: ...`. The most common real-world trigger is **CC65 not
  installed**: `check_toolchain()` raises `ToolchainError` inside `compile_rom`,
  which (not catching that type in a typed clause) prints `[ERROR] Compilation
  failed: CC65 toolchain not found...` and returns False, and the pipeline then
  banners it as an *unexpected defect*. Backup restore, exit code, and the underlying
  messages are all still correct — this is labeling/contract only.
- **Evidence**: `build_and_validate_rom` docstring (`main.py:1266-1269`) declares
  "Raises ValueError (capacity) or RuntimeError (prepare/compile/validate)";
  `core/exceptions.py` — `RuntimeError` and `ToolchainError` are outside/beside the
  clause lists that classify them at each site.
- **Impact**: Cosmetic misreporting on the default path; also makes
  `except MIDI2NESError` unreliable for tests/callers wanting "any expected pipeline
  failure".
- **Related**: PIPE-2026-08-21-8, #384/SAFE-2026-07-19-2, #406/TD-11-FOLLOWUP (which
  introduced the stage helpers with the bare-`RuntimeError` contract)
- **Suggested Fix**: Raise typed errors from the helpers (`CompilationError` /
  `ValidationError` / a small `PipelineError(MIDI2NESError)`) instead of
  `RuntimeError`, and add `ToolchainError` to `compile_rom`'s typed clauses; do it
  together with PIPE-2026-08-21-8's `ValueError` sites so one fix closes both.

### SAFE-2026-08-21-4: `run_song_build` still catches only `FileNotFoundError` around per-song parsing — a corrupt (but present) source MIDI crashes the jukebox build with a raw traceback (carried from 2026-08-07, unfixed)
- **Severity**: MEDIUM
- **Dimension**: 2 (Malformed-Input Resilience)
- **Location**: `main.py:973-978` (`except FileNotFoundError` is the only clause
  around `midi_to_frames_for_song`)
- **Status**: Existing — SAFE-2026-08-07-2 in
  `docs/audits/AUDIT_SAFETY_2026-08-07.md`; never filed as an issue (0 open issues;
  no match in `/tmp/audit/issues.json`), re-verified live this pass: the clause list
  at `:976` is unchanged, and `InvalidMIDIError` (raised for a present-but-invalid
  file per `tracker/parser_fast.py:20-21`) still propagates uncaught through
  `run_song_build` and `main()`'s netless dispatch.
- **Description**: A bank entry whose recorded `midi_path` exists but is no longer a
  valid MIDI file (overwritten, truncated, wrong file at a reused path) aborts the
  multi-song build with a raw `InvalidMIDIError` traceback partway through the
  per-song loop, instead of the clean `[ERROR]` + exit 1 every neighboring failure in
  the same loop gets. Arranger-mode failures inside `arrange_for_nes` are similarly
  unnetted.
- **Evidence**: code read of `:973-978`; the sibling corrupt-file reproduction in
  SAFE-2026-08-21-1 exercises the identical raise path
  (`parser_fast._open_midi_file`).
- **Impact**: Jukebox path only; occurs at build time on hand-curated banks where
  stale `midi_path`s are the norm rather than the exception.
- **Related**: SAFE-2026-08-21-1 (same class at `song add` time),
  PIPE-2026-08-21-4 (the umbrella exception-net finding for this function)
- **Suggested Fix**: Widen the clause to
  `except (MIDI2NESError, FileNotFoundError) as e` — one-line change; or fold into
  PIPE-2026-08-21-4's whole-function net.

### SAFE-2026-08-21-5: `builder.prepare_project(...)` in `run_song_build` is unguarded and its return value is ignored — a prepare failure either raw-tracebacks or silently proceeds to compile a stale/absent project (carried from 2026-08-07, unfixed)
- **Severity**: MEDIUM
- **Dimension**: 1 (Swallowed-Error Handling — the falsy-return contract is dropped
  on the floor); cross-ref D7
- **Location**: `main.py:1012-1014` (`builder.prepare_project(str(music_asm),
  song_count=len(songs))` — no `try`, result unchecked)
- **Status**: Existing — SAFE-2026-08-07-3 in
  `docs/audits/AUDIT_SAFETY_2026-08-07.md`; never filed as an issue; re-verified
  unchanged this pass.
- **Description**: `prepare_project` signals failure two ways, and `run_song_build`
  honors neither: an exception (bad path, permissions, missing
  `nes/audio_engine.asm`) escapes as a raw traceback, and a falsy return —
  explicitly checked by both `run_prepare` (`main.py:626-633`, added for #15) and
  `build_and_validate_rom` (`main.py:1280-1281`) — is discarded, letting the build
  fall through to `compile_rom` against a half-prepared project dir. In practice
  `ROMCompiler.validate_project` then fails with a *misleading* "missing project
  files" error (clean, but pointing at the wrong stage); the raw-traceback branch has
  no such backstop.
- **Evidence**: contrast `main.py:1014` with the two guarded call sites above; all
  three call the same method with the same documented contract.
- **Impact**: Jukebox path only; wrong-stage error attribution or traceback, no
  half-written output ROM (compile happens afterward and PIPE-2026-08-21-4 covers the
  output-ROM contract).
- **Related**: PIPE-2026-08-21-4 (whole-function net would subsume this),
  SAFE-2026-08-07-3
- **Suggested Fix**: Mirror `run_prepare`: wrap in `try/except Exception` →
  `[ERROR] Failed to prepare NES project: {e}` + exit 1, and treat a falsy return the
  same way.

## Deduplicated — verified live this pass, owned by sibling reports (not counted above)

- **PIPE-2026-08-21-2** (HIGH, `docs/audits/AUDIT_PIPELINE_2026-08-21.md`): wrong-stage
  JSON fed to `frames` still silently yields empty output with exit 0 (#377 closed but
  fix absent from master). **Independently reproduced this pass**:
  `main.py parse simple_loop.mid parsed.json` then `main.py frames parsed.json out.json`
  → prints " Generated frames -> ...", exit 0, output file is `{}`. `main.py:248` still
  passes `required_keys=[]`. Dimension 5's worst live defect; report once there.
- **PIPE-2026-08-21-4** (HIGH, same report): `run_song_build` has no backup/restore
  contract and no exception net around export/prepare/compile/validate — verified live:
  `main.py:989-1027` writes `output_rom` directly via `compile_rom` with no
  `_backup_existing_rom`/`_restore_backup`/`finally`, so a failed rebuild destroys a
  previously good jukebox ROM in place (and a validation-failed ROM is left at the
  output path). SAFE-2026-08-07-4 was this report family's earlier filing; ownership
  consolidated under the pipeline ID.
- **PIPE-2026-08-21-5** (MEDIUM, same report): `import_bank` validates bank-level shape
  only — verified live: `nes/song_bank.py:227` assigns `data['songs']` with no
  per-entry (or even is-dict) check, and `main.py:954` subscripts
  `bank.songs[name]['metadata']` → raw `KeyError`/`TypeError` on a malformed bank.
  Overlaps SAFE-2026-08-07-1.

## Verify-the-Fix Confirmations (all CLOSED items re-checked; no regressions found)

- **D1**: `run_full_pipeline`'s #384 two-clause split intact (`main.py:1430-1454`,
  `finally:` restore at `:1456-1460`). `pack_dpcm_into_asm` (#380/TD-28) single shared
  helper at `main.py:126-214`; NO DRUMS vs PARTIAL DPCM MISS labeling (#367) mirrored
  at both call sites (`:726`, `:1420`); missing-index info line present on both paths
  (#411, `:714-720` / `:1236-1237`). No path inside the helper's `try` exits without
  setting `warning` on a failed/empty pack. Parallel→sequential fallback
  (`main.py:1134-1160`) is the documented fallback with the lossy-resample warning
  firing whenever `fallback_sampled` (#100/#176); per-chunk failures in
  `tracker/pattern_detector_parallel.py:215-237` retry serially and are recorded, not
  swallowed (#106).
- **D2**: only two `mido.MidiFile` constructions in production code, both guarded
  (`tracker/parser_fast.py:16-21`, `tracker/parser.py:11-16` — the latter test-only per
  TD-26). Per-event drop counter + warning intact (`parser_fast.py:157-171`); no drop
  was triggered in this pass's runs.
- **D3**: all ca65/ld65 calls are argv lists; the one `shell=True`
  (`compiler/compiler.py:118-125`) runs only the static mapper constant (#263
  invariant + regression test `tests/test_mappers.py:306`), with `timeout=60` and
  returncode/stderr checked. `check_toolchain` probes via resolved paths with
  `timeout=10`; `assemble`/`link` have `timeout=120` + `TimeoutExpired` → typed error;
  nonzero exits raise `CompilationError` carrying stderr/stdout. Both
  `ROMCompiler.compile` (`:182`) and `CC65Wrapper.build` call `check_toolchain` first.
  120s note: ca65/ld65 on the largest MMC3 project (512KB PRG) completes in seconds;
  budget is generous. No regressions.
- **D4**: repo-wide grep — no `eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system`;
  `config/config_manager.py:127` still `yaml.safe_load`.
- **D5**: `load_json_stage` (`main.py:76-105`) guards all four subcommand reads
  (`:228` `['events']`, `:248` `[]`, `:646`/`:654` `[]`/`['patterns','references']`,
  detect-patterns). The `[]`-key weakness is the dedup'd PIPE-2026-08-21-2.
  `run_song_build`'s `midi_path` handling: existence checked with clean error
  (`:968-970`); `midi_path` recorded absolute at `song add` time (per 08-07 pipeline
  report), so the relative-cwd hazard is bounded to hand-edited banks; the
  corrupt-file case is SAFE-2026-08-21-4.
- **D6**: no non-`with` `open(` in `main.py`/`tracker/`/`nes/`/`exporter/`/
  `compiler/`/`config/`/`dpcm_sampler/`; both `tempfile.TemporaryDirectory` sites
  (`main.py:992`, `:1321`) auto-clean; backup created `:1309`, deleted on success
  `:1427-1428`, restored via single `finally` `:1456-1460` (and `run_compile`'s twin
  at `:601-605`). The one non-atomic final-output writer found is
  SAFE-2026-08-21-2.
- **D7**: `_load_from_file` narrowed clauses + `ConfigurationError` intact
  (`config_manager.py:123-134`); #222/SAFE-11 fix confirmed — `save()` raises
  `ConfigurationError` (`:251`), `validate()` raises typed `ValidationError` (`:299`).
  Remaining gaps are SAFE-2026-08-21-3. Benchmark/config subcommands' broad excepts
  (`main.py:1751`, `:1769`, `:1823`, `:1855`, `:1873`) all print `[ERROR]` and exit
  1 on terminal paths — acceptable per #223's resolution.
- **D8**: ROM built in temp dir, reaches the output path only via `shutil.copy`
  (`compiler/compiler.py:263`); exporters all use `atomic_write_text`
  (`exporter_ca65.py:999/:1532/:1672`, `exporter_famistudio.py:198/:203`) — no new
  direct-`open` final writers (#385 holds). Inter-stage JSON writers
  (`main.py:223/:242/:251/:782`) are non-atomic but truncation is caught downstream by
  `load_json_stage`'s parse guard — accepted.

---

Next step:
```
/audit-publish docs/audits/AUDIT_SAFETY_2026-08-21.md
```
