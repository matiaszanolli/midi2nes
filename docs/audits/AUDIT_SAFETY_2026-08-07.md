# Safety & Robustness Audit — 2026-08-07

Scope: the **Python layer** — error handling, malformed-input resilience, subprocess/CC65
safety, unsafe deserialization, inter-stage JSON guards, file/resource handling, exception-type
discipline, and partial-output-on-failure. This is not a NES-hardware audit.

Base commit: `f4c2283` (branch `feat/song-bank-rom-build`, includes `c864426`: "feat: song
bank -> ROM (#30/F-13) -- multi-song 'jukebox' builds"). Dedup source: `gh issue list --repo
matiaszanolli/midi2nes --state all --limit 200` (`/tmp/audit/issues_all.json`) + scan of
`docs/audits/`.

## Summary

This audit gave the brand-new `song build` subcommand (`main.py`'s `run_song_build`,
`midi_to_frames_for_song`, `_song_has_dpcm_events`; `exporter/exporter_ca65.py`'s
`export_song_bank_bytecode`/`_build_song_bytecode`; `nes/project_builder.py`'s `song_count`
param; `nes/song_bank.py`'s resolved `midi_path`) focused, adversarial scrutiny — every
finding below was reproduced live (not just read) with small standalone Python
repros that call `run_song_build` directly against a malformed bank file, a corrupt
source MIDI, a mocked `prepare_project` failure, and a pre-existing output ROM. All
four dimensions of the task's specific ask ("corrupt bank file, missing/relocated
source MIDI, empty bank, malformed JSON") were exercised; three produce a raw,
uncaught Python traceback instead of the clean `[ERROR] ...` + exit-1 pattern the rest
of `main.py` uses consistently, and one silently destroys a pre-existing good ROM file.
The previously-audited surface (D3 subprocess/CC65, D4 deserialization) is untouched by
this commit and re-confirmed clean by fresh repo-wide greps.

- **D1 Swallowed-/Missing-Error Handling**: `run_song_build`'s own top-level guards
  (`bank.import_bank`, `export_song_bank_bytecode`, `check_mapper_capacity`,
  `compile_rom`, `validate_rom`) are all present and correctly narrowed — this part of
  the new code follows the established `main.py` convention well. But two specific
  calls inside the same function break that convention: `midi_to_frames_for_song`'s
  result is only guarded by `except FileNotFoundError` even though the function can
  raise several other exception types (SAFE-2026-08-07-2), and `builder.prepare_project(...)`
  has **no** guard at all, unlike the textually adjacent `run_prepare`, which wraps the
  identical call specifically to avoid this (`main.py:623-630`, comment cites #15)
  (SAFE-2026-08-07-3).
- **D2 Malformed-Input Resilience**: the parser-level guards from #121/SAFE-02 and
  #124/SAFE-07 are intact and unregressed (confirmed by re-reading
  `tracker/parser_fast.py:9-21`). But `run_song_build` is a new *caller* of that guarded
  parser that doesn't handle the typed exception it produces — see
  SAFE-2026-08-07-2, reproduced live with a garbage-bytes `.mid` file.
- **D3 Subprocess/CC65 Safety**: unchanged by this commit (`compiler/`, `mappers/base.py`
  not touched — confirmed via `git diff --stat` against the prior audit's base commit).
  `run_song_build`'s own use of `compile_rom`/`validate_rom` is safe: both are
  non-raising wrappers (`compile_rom` catches `CompilationError`/`ValidationError`/
  `Exception` internally and returns `bool`, `compiler/compiler.py:286-303`), and
  `run_song_build` checks the return value before proceeding — the two severe CC65-level
  bugs found independently by the exporters/mappers audits (single-song link failure;
  2+-song instrument-table mis-banking) are both surfaced through this same clean
  return-value path rather than crashing `run_song_build` itself. Re-confirmed clean, no
  new findings.
- **D4 Unsafe Deserialization**: repo-wide fresh grep for
  `eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system`/`shell=True` finds only the one
  documented, guarded `shell=True` (`compiler/compiler.py:120`, fed by a verified static
  constant). Confirmed clean, no new findings.
- **D5 JSON-Intermediate Guards**: `SongBank.import_bank` (`nes/song_bank.py:191-218`,
  #220/SAFE-09) validates the bank-level JSON shape (`bank_info`, `songs` key presence)
  but never validates the *shape of each song entry* inside `songs`. This gap predates
  `c864426` but was never reachable as a crash before — `run_song_build` (new) and
  `run_song_list` (pre-existing) both index into `song_data['metadata']` unguarded
  immediately after `import_bank` returns. Reproduced live: a bank with a song entry
  missing `'metadata'` crashes `run_song_build` with an uncaught `KeyError: 'metadata'`
  — see SAFE-2026-08-07-1.
- **D6/D8 File/Resource Handling & Partial-Output-on-Failure**: `run_song_build` builds
  inside a `tempfile.TemporaryDirectory` (`main.py:992`, auto-cleans, correct) and its
  bytecode export goes through `atomic_write_text` (`exporter/exporter_ca65.py:1657`,
  matches #385's pattern — confirmed, no finding). But unlike `run_compile`
  (`main.py:586,601-605`) and `run_full_pipeline` (`main.py:1309`, `:1427-1428`,
  `:1460`), `run_song_build` never calls `_backup_existing_rom`/`_restore_backup` around
  its `compile_rom`/`validate_rom` sequence. Reproduced live (byte-level): pointing
  `song build` at an existing, good `.nes` file and forcing a post-compile validation
  failure leaves the **new, broken** ROM bytes at the output path — the prior good file
  is gone, unrecoverable, with only an `[ERROR] ROM validation failed` message and no
  hint that the old file was lost. This is the exact defect class #178/PL-05 fixed for
  `compile`/the full pipeline, reintroduced in the one new entry point that skipped it —
  see SAFE-2026-08-07-4 (**Regression of #178**).
- **D7 Exception-Type Discipline**: unchanged elsewhere (typed hierarchy in
  `core/exceptions.py` used consistently outside this feature). Within the new feature,
  SAFE-2026-08-07-2 is also a D7 instance: `midi_to_frames_for_song` legitimately raises
  a typed `InvalidMIDIError`/`MappingError` the rest of the codebase knows how to
  present cleanly, but this one caller doesn't catch it.

### Counts

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 4 |
| LOW | 0 |
| **Total new findings** | **4** |

By dimension: D1 ×2 (SAFE-2026-08-07-2, -3), D2 ×1 (SAFE-2026-08-07-2, cross-ref D1),
D5 ×1 (SAFE-2026-08-07-1), D6/D8 ×1 (SAFE-2026-08-07-4, Regression of #178), D7 ×1
(SAFE-2026-08-07-2, cross-ref). D3 and D4 confirmed clean, zero findings (new or
existing).

### Three highest-leverage robustness fixes

1. **SAFE-2026-08-07-4** (Regression of #178) — give `run_song_build` the same
   `_backup_existing_rom`/`_restore_backup` treatment `run_compile`/`run_full_pipeline`
   already have. This is the only finding with real data-loss consequences (a
   previously-good ROM silently destroyed), and it directly interacts with the
   independently-confirmed 2+-song instrument-table corruption bug: today, running
   `song build` again over a known-good single/prior ROM with a newly-added second song
   can compile "successfully" and clobber the good file with corrupted audio, with no
   way back.
2. **SAFE-2026-08-07-2** — widen `run_song_build`'s per-song `except FileNotFoundError`
   to also catch `MIDI2NESError` (or specifically `InvalidMIDIError`/`ValueError`/
   `MappingError`), matching the exact malformed/corrupt-MIDI scenario this audit's
   task description called out by name.
3. **SAFE-2026-08-07-3** — wrap `builder.prepare_project(...)` in `run_song_build` the
   same way `run_prepare` already does two hundred lines away in the same file (cite
   #15 in the fix, matching the existing comment style).

---

## Findings

### SAFE-2026-08-07-1: `SongBank.import_bank` doesn't validate per-song entry shape — a bank with a malformed song crashes `song build`/`song list` with a raw `KeyError`
- **Severity**: MEDIUM
- **Dimension**: D5 (JSON-Intermediate Guards) / D1 (Swallowed-/Missing-Error Handling)
- **Location**: `nes/song_bank.py:191-218` (`import_bank` — validates `bank_info` and
  the presence of the `songs` key, never the shape of `songs`' values); consumed
  unsafely at `main.py:953-954` (`run_song_build`'s `sorted(..., key=lambda name:
  bank.songs[name]['metadata'].get('order', 0))`) and `main.py:845`
  (`run_song_list`'s `metadata = song_data['metadata']`)
- **Status**: NEW (the shallow bank-level validation in `import_bank` is pre-existing,
  #220/SAFE-09, and unchanged by `c864426`; this specific gap — per-song entry shape —
  was never reachable as a live crash before `run_song_build` existed as a new,
  more-exposed caller that hand-crafted/externally-sourced bank files are likely to hit)
- **Description**: `import_bank` (`nes/song_bank.py:191-218`) checks that the top-level
  JSON is a dict, that `bank_info` exists with `total_banks`/`bank_size`, and that a
  `songs` key exists — but never checks that `data['songs']` is itself a dict, nor that
  each value in it has the keys downstream code assumes (`'metadata'`, `'bank'`,
  `'midi_path'`). `run_song_build` immediately sorts `bank.songs` by
  `bank.songs[name]['metadata'].get('order', 0)` (`main.py:953-954`) — before any
  per-song try/except — so a single malformed song entry anywhere in the bank aborts
  the whole build with an uncaught `KeyError`, not the clean `[ERROR] Failed to load
  song bank: ...` message the surrounding `bank.import_bank(...)` try/except
  (`main.py:941-945`) was clearly meant to guarantee for exactly this class of input.
  `run_song_list` has the identical exposure one line later (`main.py:845`).
- **Evidence**: Live repro (bank JSON with one song entry that has no `'metadata'`
  key — a totally plausible hand-edited or partially-written bank file):
  ```python
  from main import run_song_build
  # bank.json: {"version": "0.3.0",
  #   "bank_info": {"total_banks": 8, "bank_size": 16384},
  #   "songs": {"song_a": {"segments": {...}, "bank": 0, "size": 100,
  #                         "midi_path": "/tmp/whatever.mid"}}}  # no 'metadata' key
  run_song_build(args)
  # UNCAUGHT: KeyError 'metadata'
  ```
  Confirmed by direct execution — no `SystemExit`, no `[ERROR]` message, a raw
  traceback all the way to `main.py:954`.
- **Impact**: Any bank JSON that's been hand-edited, partially written by a killed
  process, produced by a future tool version with a different schema, or merged
  incorrectly from two banks will crash `song build` and `song list` with a confusing
  traceback instead of a message pointing at the actual problem ("song entry missing
  metadata"). No ROM is produced either way (fails before any I/O to the output path),
  so this is a UX/robustness gap, not data corruption.
- **Related**: #220/SAFE-09 (the bank-level guard this finding extends); analogous in
  spirit to #256/D-18 ("`run_map` crashes with a raw traceback ... unlike the packer
  path") — a caller of a partially-guarded input path that falls through the gap.
- **Suggested Fix**: In `import_bank`, after confirming `songs` is present, validate it
  is a `dict` and that each value is a `dict` containing at least `'metadata'` (itself a
  dict) — raise the same `ValueError` style used for the other structural checks in that
  method so the existing `except Exception` call sites convert it to a clean message for
  free.

---

### SAFE-2026-08-07-2: `run_song_build` only catches `FileNotFoundError` from per-song parsing — a corrupt (but present) source MIDI crashes with a raw `InvalidMIDIError` traceback
- **Severity**: MEDIUM
- **Dimension**: D2 (Malformed-Input Resilience) / D1 / D7 (Exception-Type Discipline)
- **Location**: `main.py:973-978` (`run_song_build`'s
  `try: frames = midi_to_frames_for_song(...) except FileNotFoundError as e:`) calling
  `main.py:878-908` (`midi_to_frames_for_song`, which calls
  `tracker.parser_fast.parse_midi_to_frames` → `_open_midi_file`
  (`tracker/parser_fast.py:9-21`, raises `InvalidMIDIError` for a corrupt file) and, for
  degenerate SMPTE-timing MIDI, a bare `ValueError`
  (`tracker/parser_fast.py:89-94`, `_parse_frames_and_tempo_map`, never wrapped by
  `parse_midi_to_frames`); legacy (non-arranger) mode can additionally raise
  `MappingError`/`ChannelOverflowError` from `assign_tracks_to_nes_channels`
- **Status**: NEW
- **Description**: `run_song_build` explicitly re-checks `Path(midi_path).exists()`
  (`main.py:968-970`) before parsing, and its `try/except FileNotFoundError` around
  `midi_to_frames_for_song` reads as if it were meant to cover "problems reading this
  song's MIDI file" generally — but it only actually catches the one case already ruled
  out by the preceding `.exists()` check (a TOCTOU race aside). `parse_midi_to_frames`
  is the same, well-guarded parser entry point the rest of the codebase relies on to
  convert corrupt/invalid MIDI content into a typed `InvalidMIDIError` instead of a raw
  `mido` traceback (#121/SAFE-02) — but `InvalidMIDIError` is a `MIDI2NESError`, not a
  `FileNotFoundError`, so this specific `except` clause never catches it. The exact
  scenario named in this audit's task ("a missing/relocated source MIDI") is handled
  cleanly by the `.exists()` pre-check; the closely related and equally realistic
  scenario — the file exists but is corrupt/truncated/not-a-MIDI-file (e.g. from a
  failed download, a bad copy, or the file having been overwritten) — is not.
- **Evidence**: Live repro (bank entry pointing at a real, existing, but garbage file):
  ```python
  midi_path.write_bytes(b"not a real midi file, just garbage bytes 1234567890")
  # bank.json references midi_path, valid 'metadata', etc.
  run_song_build(args)
  # Parsing 'song_a' (/tmp/.../corrupt.mid)...
  # UNCAUGHT: InvalidMIDIError Invalid MIDI file: /tmp/.../corrupt.mid: MThd not found. Probably not a MIDI file
  ```
  Confirmed by direct execution — no `SystemExit`, no `[ERROR]` message.
- **Impact**: A user building a jukebox ROM from a bank containing one corrupt MIDI
  (out of possibly many songs) gets a raw Python traceback pointing into
  `tracker/parser_fast.py` instead of a message naming which song and why — a
  materially worse experience than every other MIDI-corruption path in the codebase,
  which was specifically hardened for this (#121/SAFE-02, #124/SAFE-07). No ROM/output
  file is touched (fails before any output I/O), so this is a UX/robustness gap only.
- **Related**: #121/SAFE-02 (the guard this caller fails to use); #124/SAFE-07 (sibling
  parser-level hardening); SAFE-2026-08-07-1 (same root pattern — a new caller not
  matching an established guard's contract).
- **Suggested Fix**: Broaden the `except` clause to
  `except (FileNotFoundError, MIDI2NESError) as e:` (covers `InvalidMIDIError`,
  `MappingError`/`ChannelOverflowError`, etc. in one place) — or, since
  `main.py:MIDI2NESError` is already imported for `run_full_pipeline`'s equivalent
  split, add a second clause the same way. The SMPTE-timing bare `ValueError`
  (`tracker/parser_fast.py:89-94`) is a separate, smaller pre-existing gap (also unwrapped
  in `run_full_pipeline`'s own direct call to `parse_midi_to_frames` — not unique to
  `song build`) worth folding into the same `except` tuple defensively.

---

### SAFE-2026-08-07-3: `builder.prepare_project(...)` is called unguarded in `run_song_build` — a bad project path/permissions/missing-engine-file crashes with a raw traceback, unlike the identical call in `run_prepare`
- **Severity**: MEDIUM
- **Dimension**: D1 (Swallowed-/Missing-Error Handling) / D7
- **Location**: `main.py:1013-1014` (`run_song_build`:
  `builder.prepare_project(str(music_asm), song_count=len(songs))`, no try/except) vs.
  `main.py:622-630` (`run_prepare`'s identical call, explicitly wrapped:
  `try: prepared = builder.prepare_project(args.input) except Exception as e: print(...); sys.exit(1)`,
  with a comment citing #15); `nes/project_builder.py:127-131`
  (`prepare_project` raises `ExportError` if `audio_engine.asm` is missing/relocated)
  and `nes/project_builder.py:101,104` (`Path.mkdir`, `Path(music_asm_path).read_text()`
  — both can raise `OSError`/`PermissionError`)
- **Status**: NEW
- **Description**: `run_prepare` wraps its call to `NESProjectBuilder.prepare_project`
  in a try/except specifically because the method "may raise (bad path/permissions) or
  return falsy" (`main.py:623-625`'s own comment, referencing #15 — the issue that
  established this exact pattern across `main.py`). `run_song_build` calls the same
  method with the same failure modes available (a corrupted/incomplete install missing
  `nes/audio_engine.asm`; a read-only or full temp filesystem; a permissions issue on
  the temp project directory) but has no guard at all around the call — any exception
  propagates straight out of `run_song_build` as a raw traceback, bypassing every other
  `[ERROR] ...` + `sys.exit(1)` guard in the same function.
- **Evidence**: Live repro (mocking the one realistic failure mode —
  `prepare_project` raising, which is exactly what a missing `audio_engine.asm` or a
  permissions error produces in the real implementation):
  ```python
  mock_builder.prepare_project.side_effect = RuntimeError("disk full / permission denied simulation")
  run_song_build(args)
  # Parsing 'song_a' (.../a.mid)...
  # 🔧 CA65 Exporter: MMC3 Macro Bytecode mode (1-song jukebox build)
  # ✅ Macro Bytecode jukebox export complete: ...
  # UNCAUGHT: RuntimeError disk full / permission denied simulation
  ```
  No `SystemExit`, no `[ERROR]` message — confirms the call is genuinely unguarded, not
  merely untested.
- **Impact**: Low likelihood in a normal, intact install (the shipped `nes/` directory
  always carries `audio_engine.asm`), but the failure mode is real (packaging/install
  issues, read-only filesystems, disk-full mid-build) and, when it happens, produces the
  one raw traceback in an otherwise fully `[ERROR]`-guarded function — inconsistent with
  every other step in the same `song build` sequence and with the sibling `run_prepare`
  path that already solved this.
- **Related**: #15 (the issue that established the "wrap `prepare_project`, surface a
  clean nonzero exit" pattern `run_prepare` follows and `run_song_build` doesn't);
  SAFE-2026-08-07-2 (same class of gap, different call site in the same function).
- **Suggested Fix**: Wrap the call exactly like `run_prepare` does:
  `try: builder.prepare_project(...) except Exception as e: print(f"[ERROR] Failed to
  prepare NES project: {e}"); sys.exit(1)`.

---

### SAFE-2026-08-07-4: `run_song_build` has no backup/restore around compile+validate — a post-compile validation failure silently destroys a pre-existing good ROM at the output path (Regression of #178/PL-05)
- **Severity**: MEDIUM
- **Dimension**: D6 (File/Resource Handling) / D8 (Partial-Output-on-Failure)
- **Location**: `main.py:1017-1025` (`run_song_build`'s
  `compile_rom(...)` / `validate_rom(...)` sequence — no `_backup_existing_rom`/
  `_restore_backup` calls anywhere in the function) vs. `main.py:475-503`
  (`_backup_existing_rom`/`_restore_backup`, the shared helpers) and their use at
  `main.py:586` + `:601-605` (`run_compile`) and `main.py:1309` + `:1427-1428`/`:1460`
  (`run_full_pipeline`); `compiler/compiler.py:263` (`ROMCompiler.compile()`'s
  `shutil.copy(rom_path, output_path)` — happens on successful compile, **before**
  `run_song_build`'s separate `validate_rom` call)
- **Status**: **Regression of #178/PL-05** ("A validation-failed (unbootable) ROM is
  left at the output path — always for the `compile` subcommand, and on the default
  path whenever no backup existed" — CLOSED, fixed via the `_backup_existing_rom`/
  `_restore_backup` pair now used by both `run_compile` and `run_full_pipeline`).
  `run_song_build` is a new third call site that never received the same fix.
- **Description**: `ROMCompiler.compile()` copies the freshly-linked ROM to the final
  output path as soon as CC65 succeeds (`compiler/compiler.py:263`) — validation is a
  separate, later step. `run_compile` and `run_full_pipeline` both back up any
  pre-existing file at the output path *before* calling `compile_rom`, and restore that
  backup in a `finally:` block if either compilation or the subsequent validation fails
  — this is exactly what #178/PL-05 was filed and fixed for. `run_song_build` calls
  `compile_rom` then `validate_rom` in the identical sequence (`main.py:1017-1025`) but
  never creates or restores a backup: if `compile_rom` succeeds (copying a new ROM over
  any existing file at `args.output`) and `validate_rom` then fails, the old good ROM is
  already gone, and `run_song_build` reports `[ERROR] ROM validation failed` and exits
  1 with no mention that the previous file was lost.
- **Evidence**: Live repro (byte-level, with `compile_rom` mocked to write real bytes
  the way the real implementation does, and `validate_rom` mocked to fail — modeling
  exactly the independently-confirmed "2+ song bank links and boots but corrupts
  playback" scenario, which a correct validator should ideally catch):
  ```python
  output_rom.write_bytes(b"GOOD-EXISTING-ROM-BYTES-DO-NOT-LOSE-ME")
  def fake_compile(project_path, out_rom, verbose=False, mapper=None):
      Path(out_rom).write_bytes(b"NEW-BROKEN-ROM-BYTES")
      return True
  # main.compile_rom -> fake_compile, main.validate_rom -> False
  run_song_build(args)
  # ... [ERROR] ROM validation failed / SystemExit 1
  print(output_rom.read_bytes())
  # b'NEW-BROKEN-ROM-BYTES'   <-- the good ROM is gone, no backup existed
  ```
- **Impact**: Realistic and directly relevant to the two severe bugs the parallel
  exporters/mappers audits confirmed live: (1) a single-song bank fails to *link*
  (caught cleanly — `compile_rom` returns `False`, no copy happens, existing file
  untouched, not this finding), but (2) a 2+-song bank *does* link and boot, with the
  corruption only in the instrument/macro table data — exactly the kind of defect a
  ROM's ordinary CC65 link success plus a validator that doesn't specifically probe
  jukebox instrument-table wiring would miss or only partially catch. Any user
  iterating on a song bank (adding a song, rebuilding to the same output path) who
  hits either that bug or any other post-compile validation failure loses their last
  known-good ROM with no recovery path, differing from the guarantee `compile`/the full
  pipeline already give.
- **Related**: #178/PL-05 (the original fix this regresses); #26/F-11 ("Backup restore
  does not fire on prepare-failure or top-level exception exits" — same helper pair,
  different original gap); #29/F-12 (".nes.backup is never cleaned up on success" — the
  success-path half of the same mechanism, also absent here since there's no backup to
  clean up). Interacts with, but is independent of, the exporters audit's
  EXP-2026-08-07-1 (single-song link failure) and the separately-confirmed 2+-song
  instrument-table mis-banking bug.
- **Suggested Fix**: Give `run_song_build` the same
  `backup_path = _backup_existing_rom(output_rom)` /
  `try: ... finally: _restore_backup(...) if not build_succeeded else
  backup_path.unlink(missing_ok=True)` structure `run_compile` uses (`main.py:586-605`)
  around its `compile_rom`/`validate_rom` calls.

---

## Dimensions confirmed clean (no new findings)

- **D3 Subprocess/CC65 Safety**: `compiler/`, `compiler/cc65_wrapper.py`, and
  `mappers/base.py` are untouched by `c864426` (confirmed via `git diff --stat`).
  `run_song_build`'s own use of `compile_rom` is safe — the function is a non-raising
  `bool`-returning wrapper (`compiler/compiler.py:286-303`) and `run_song_build` checks
  its return value before proceeding, so a CC65 link failure (including the
  independently-confirmed single-song-bank link bug) surfaces as a clean
  `[ERROR] Compilation failed` + exit 1, not a crash.
- **D4 Unsafe Deserialization**: fresh repo-wide grep for
  `eval(`/`exec(`/`yaml.load(`/`pickle.load`/`os.system`/`shell=True` finds only the
  one documented, guarded `shell=True` in `compiler/compiler.py:120`, fed by a verified
  static mapper-constant string. No new matches introduced by the song-bank feature.
