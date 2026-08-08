# Pipeline Integrity Audit — 2026-08-07

**Scope**: End-to-end `parse → map/arrange → frames → detect-patterns → export → prepare →
compile → validate` chain, per `.claude/commands/audit-pipeline/SKILL.md` Dimensions 1-8.
**Repo state audited**: commit `f4c2283` (branch `master`, merge of `feat/song-bank-rom-build`).

## Summary

This is a re-audit following `docs/audits/AUDIT_PIPELINE_2026-08-06.md` (which audited
`20f627e` and found 0 new / 3 existing LOW findings, all still open). One feature landed
since then: `c864426` ("feat: song bank -> ROM (#30/F-13) -- multi-song 'jukebox' builds"),
adding `song build <bank.json> <out.nes>` (`run_song_build`/`midi_to_frames_for_song`,
`main.py`), `CA65Exporter.export_song_bank_bytecode` (`exporter/exporter_ca65.py`),
`.ifdef JUKEBOX_BUILD`-gated multi-song routines (`nes/audio_engine.asm`), and a
`song_count` param on `NESProjectBuilder.prepare_project` (`nes/project_builder.py`). This
closes the long-standing #30/F-13 "song bank is disjoint from the pipeline" roadmap gap and
is squarely Dimension 8's territory, so this pass audited it as a full new pipeline path,
not just a doc-rot check.

The pre-existing 7-stage pipeline (`main.py`'s `run_parse`/`run_map`/`run_frames`/
`run_detect_patterns`/`run_export`/`run_prepare`/`run_compile`/`run_full_pipeline`) has
**zero code changes** in this commit — confirmed by `git diff` against the prior audited
commit showing the entire `main.py` diff is the new `run_song_build`/
`midi_to_frames_for_song`/`_song_has_dpcm_events` functions plus the new `song build`
argparse subparser. Dimensions 1-7 were re-verified against the 2026-08-06 findings with no
new issues, and a real single-song `python main.py test_midi/simple_loop.mid out.nes` build
was re-run end-to-end through real CC65 (`ca65`/`ld65` V2.18) to confirm no regression: it
still compiles, links, and passes ROM validation (`ROM size: 524,304 bytes`, `Pattern
coverage: 100.0%`).

**The new `song build` path itself has two real, independently-confirmed bugs** (both found
by tracing the code and then reproducing with a real CC65 toolchain, not just static
reading):

1. **A song bank containing exactly one song cannot be built** — `run_song_build` always
   calls the jukebox-only bytecode serializer, but `NESProjectBuilder`'s `JUKEBOX_BUILD`
   gate only activates for `song_count > 1`, so the one-song case links with 8 unresolved
   externals. Reproduced live: `ld65: Error: 8 unresolved external(s) found`. This is the
   single most dangerous contract break this pass — a 1-song bank is arguably the *most*
   likely first thing a new user of this brand-new feature tries.
2. **`run_song_build` has no backup/restore contract** — unlike `run_full_pipeline` and
   `run_compile`, it never calls `_backup_existing_rom`/`_restore_backup` and wraps none of
   its build steps in `try`/`except`/`finally`, so (a) rebuilding a jukebox ROM at a path
   that already holds a good `.nes` silently loses that good ROM with no recovery if the
   rebuild later fails validation, and (b) an unexpected exception (e.g. `prepare_project`'s
   own internal capacity re-check) surfaces as a raw traceback instead of the `[ERROR]` +
   clean-exit pattern every other build path in this file uses.

Two smaller LOW findings round out the pass (a stale CLI error message, and a latent
song-ordering collision).

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 2 |
| MEDIUM   | 0 |
| LOW      | 2 |

**Total findings this pass: 4 NEW / 0 Existing.** (The 3 LOW findings re-confirmed in the
2026-08-06 report — `#377`, `#378`, `#379` — were not re-verified line-by-line this pass
since no code they touch changed; they remain open per that report.)

**Single most dangerous contract break**: PL-2026-08-07-1 below — `song build` on a
single-song bank fails to compile because `export_song_bank_bytecode`'s output and
`prepare_project`'s `JUKEBOX_BUILD` gate disagree about what `song_count == 1` means.

**Does the step-by-step path produce the same ROM as the default path?** **Yes**, unchanged
from the 2026-08-06 finding — re-confirmed by a real single-song CC65 build this pass. This
question doesn't apply to `song build`, which is a third, independent entry point with no
step-by-step equivalent (by design, per `docs/ROADMAP.md`).

## Findings-per-Dimension

| Dimension | New findings | Existing (re-confirmed) |
|---|---|---|
| 1 — Stage JSON Contract Integrity | 0 | not re-checked this pass (no `main.py` change in this area) |
| 2 — `run_full_pipeline` vs step-by-step parity | 0 | — |
| 3 — Flag routing | 1 (LOW) | — |
| 4 — Error propagation / fail-fast | 0 (folded into Dimension 6 finding below — same root cause) | — |
| 5 — Temp-file / intermediate handling | 0 | — |
| 6 — Backup & overwrite safety | 1 (HIGH) | — |
| 7 — Large-file threshold / fallback hand-off | 0 | N/A — `song build` runs no pattern detection |
| 8 — Song-bank path | 2 (1 HIGH, 1 LOW) | — |

## Contract Map

| Producer → Key(s) → Consumer | Verified matching |
|---|---|
| `run_parse` → `{"events":[...], "metadata":...}` → `run_map` | ✓ (unchanged) |
| `run_map` → per-channel mapped events → `run_frames` → `NESEmulatorCore.process_all_tracks` | ✓ (unchanged) |
| `run_frames` → `{channel: {frame: {...}}}` → `run_export`/`run_detect_patterns` | ✓ (unchanged) |
| detectors → `{'patterns','references','stats'}` → `run_export` | ✓ (unchanged) |
| `export_tables_with_patterns(frames, patterns, references, output_path)` | ✓ bytes (unchanged; `_build_song_bytecode` extraction confirmed byte-identical for the single-song caller — `label_prefix=''`, `start_bank=0`) |
| `NESProjectBuilder.prepare_project` → `main.asm`/`music.asm`/`nes.cfg` | ✓ (unchanged for `song_count=None`/`1` on the *ordinary* single-song path; re-verified live) |
| `compiler.compile_rom(project_dir, output_rom)` → validated `.nes` | ✓ (unchanged) |
| **NEW: `SongBank.songs` (via `run_song_build`) → per-song `frames` (in-memory, `midi_to_frames_for_song`) → `CA65Exporter.export_song_bank_bytecode` → jukebox `music.asm` → `NESProjectBuilder.prepare_project(song_count=N)` → `nes/audio_engine.asm` `.ifdef JUKEBOX_BUILD`** | **✗ for `N == 1`** — PL-2026-08-07-1 below. ✓ confirmed for `N == 2` (real CC65 build succeeded). |
| **NEW: `run_song_build`'s compile/validate tail → `output_rom`** | **✗** — no `_backup_existing_rom`/`_restore_backup`, unlike `run_full_pipeline`/`run_compile` — PL-2026-08-07-2 below. |

## Findings

### PL-2026-08-07-1: `song build` cannot build a single-song bank — `JUKEBOX_BUILD` gate disagrees with what the exporter actually emitted
- **Severity**: HIGH
- **Dimension**: 8 (Song-Bank Path)
- **Both paths?**: N/A — this is the new `song build` entry point, not `run_full_pipeline` or a step-by-step subcommand. Does not affect either of those (both re-confirmed working this pass).
- **Location**: `main.py:996-1014` (`run_song_build` unconditionally calls
  `exporter.export_song_bank_bytecode(songs, str(music_asm))` regardless of `len(songs)`,
  then `builder.prepare_project(str(music_asm), song_count=len(songs))`);
  `nes/project_builder.py:308` (`if song_count and song_count > 1:` — the only place
  `JUKEBOX_BUILD = 1` gets defined) and `:336` (`jukebox_mode = bool(song_count and
  song_count > 1)`); `nes/audio_engine.asm:246-333` (`.ifdef JUKEBOX_BUILD` wraps the
  *only* definitions of `audio_init_song`, `audio_advance_song`,
  `load_song_streams_indexed`); `exporter/exporter_ca65.py:1644-1649`
  (`export_song_bank_bytecode` unconditionally emits `.import audio_init_song,
  audio_advance_song` and `init_music: jmp audio_init_song`, for any `len(songs) >= 1`).
- **Status**: NEW
- **Description**: `run_song_build` always serializes the bank through
  `export_song_bank_bytecode` — the jukebox-format bytecode path, which unconditionally
  imports and jumps to `audio_init_song`/`audio_advance_song` — for *any* song count,
  including 1. But it passes that same count straight through to `prepare_project`'s
  `song_count` parameter, whose only consumer (`_generate_main_asm`,
  `nes/project_builder.py:336`) treats `song_count == 1` as "this is really an ordinary
  single-song project, leave output unchanged" and does **not** define `JUKEBOX_BUILD`. With
  `JUKEBOX_BUILD` undefined, `nes/audio_engine.asm`'s `.ifdef JUKEBOX_BUILD` block — which is
  the *only* place `audio_init_song`/`audio_advance_song`/`load_song_streams_indexed` are
  defined — never assembles. The two sides of the contract (what
  `export_song_bank_bytecode` produced vs. what `song_count` tells `prepare_project` to
  build against) disagree for exactly the `N == 1` case, and nothing in `run_song_build`
  special-cases it. This is also codified as a false assumption in the test suite:
  `tests/test_nes_project_builder.py`'s `test_song_count_one_leaves_output_unchanged` labels
  `song_count=1` "still an ordinary single-song project" — true for the *original*
  single-song caller (which never passes `song_count` at all, defaulting to `None`), but
  false for `run_song_build`, which always exports via the jukebox serializer regardless of
  count. Every `run_song_build` test in `tests/test_main.py::TestRunSongBuild` mocks
  `NESProjectBuilder` entirely, so none of them exercise the real
  `prepare_project`/`audio_engine.asm` interaction that this bug lives in — the commit
  message's "Verified with a real CC65 build" was a 2-song build only.
- **Evidence**: Live reproduction against this exact commit (`f4c2283`), using the real
  system `ca65`/`ld65` V2.18:
  ```
  $ python3 main.py song add test_midi/simple_loop.mid --bank bank1.json --name solo
  $ python3 main.py song build bank1.json jukebox_1song.nes
    Parsing 'solo' (.../test_midi/simple_loop.mid)...
  🔧 CA65 Exporter: MMC3 Macro Bytecode mode (1-song jukebox build)
  ✅ Macro Bytecode jukebox export complete: /tmp/midi2nes_.../music.asm (1 songs, 1 bank(s) used)
    Using MMC3 with 512KB PRG-ROM
  🔨 Compiling 1-song jukebox ROM...
  [ERROR] Failed to link ROM: ld65: Warning: .../nes.cfg(200): Segment 'DPCM' isn't aligned properly...
  Unresolved external 'audio_init_song' referenced in: .../music.asm(192)
  Unresolved external 'channel_start_banks' referenced in: .../audio_engine.asm(155,162,169,176,183)
  Unresolved external 'dpcm_sequence' referenced in: .../audio_engine.asm(179,181)
  Unresolved external 'instrument_table' referenced in: .../audio_engine.asm(494,494,495,495,505,505,511,511)
  Unresolved external 'noise_sequence' / 'pulse1_sequence' / 'pulse2_sequence' / 'triangle_sequence' referenced in: .../audio_engine.asm
  ld65: Error: 8 unresolved external(s) found - cannot create output file
  [ERROR] Compilation failed
  ```
  Note the errors go *both* directions: `music.asm` wants `audio_init_song` (only defined
  under `JUKEBOX_BUILD`), while `audio_engine.asm`'s `.else` branch (assembled because
  `JUKEBOX_BUILD` is undefined) wants the old single-song labels
  (`channel_start_banks`/`pulse1_sequence`/etc.) that `export_song_bank_bytecode` never
  defines (it defines `song0_pulse1_sequence` etc. instead) — confirming the two halves of
  the build are built for genuinely incompatible engine configurations. A control build with
  a 2-song bank (`song_count=2`, `JUKEBOX_BUILD` correctly defined) compiled, linked, and
  passed `validate_rom` cleanly in the same environment, isolating the bug to exactly the
  `song_count == 1` boundary.
- **Impact**: `song build` is completely unusable on a bank with only one song — the most
  natural first thing to try when adopting a brand-new feature (add one song, try to build
  it before adding a second). The failure is at least surfaced cleanly (no ROM file is
  written; `ld65`'s nonzero exit propagates through `compile_rom` → `run_song_build`'s
  `if not success: sys.exit(1)`), so this is not a silent-corruption bug — but it blocks a
  documented, advertised capability (`docs/ROADMAP.md`: "`song build <bank.json> <out.nes>`
  compiles a `SongBank` into a real multi-song 'jukebox' ROM") for the smallest possible
  input to it.
- **Related**: #30/F-13 (the feature this bug lives in, closed by the commit under audit).
- **Suggested Fix**: Either (a) have `run_song_build` fall back to the plain single-song
  `export_tables_with_patterns`/`prepare_project(song_count=None)` path when `len(songs) ==
  1` (byte-identical to the ordinary pipeline's output, and correctly un-gated), or (b)
  change `prepare_project`'s gate from `song_count > 1` to `song_count is not None` (i.e.
  "the caller explicitly opted into jukebox mode, regardless of how many songs") — but only
  after auditing every other caller of `song_count` to confirm none of them intentionally
  pass `1` expecting the old single-song behavior. Either way, add a real (non-mocked) CC65
  round-trip test for exactly `song_count == 1` alongside the existing 2-song coverage.

### PL-2026-08-07-2: `run_song_build` has no backup/restore contract and no exception safety net around its build steps
- **Severity**: HIGH
- **Dimension**: 6 (Backup & Overwrite Safety)
- **Both paths?**: N/A — new `song build` entry point only. `run_full_pipeline` and
  `run_compile` both still correctly implement this contract (re-confirmed this pass;
  unchanged since `#26`/F-11 and `#178`/PL-05, both closed).
- **Location**: `main.py:989-1024` (`run_song_build`'s tail: no call to
  `_backup_existing_rom`/`_restore_backup`, defined at `main.py:475`/`:491` and used only by
  `run_full_pipeline` (`main.py:1309`, `:1460`) and `run_compile` (`main.py:586`, `:603`);
  no `try`/`except`/`finally` wraps `builder.prepare_project(...)` (`:1014`),
  `compile_rom(...)` (`:1017`), or `validate_rom(...)` (`:1023`)).
- **Status**: NEW
- **Description**: `run_full_pipeline` backs up any pre-existing ROM at the output path
  before building (`_backup_existing_rom`, `main.py:1309`) and restores it — or moves an
  unbootable first-time build aside to `<name>.nes.failed` — in a `finally` block
  (`main.py:1456-1460`) that fires on every failure path, including an uncaught exception
  (re-confirmed this pass). `run_compile` does the same (`main.py:586`, `:601-605`).
  `run_song_build` does
  neither: it calls `compile_rom(project_path, output_rom, ...)` directly against the user's
  `output_rom` with nothing backed up first, and nothing in the function catches an
  exception from `builder.prepare_project(...)` — notably, `prepare_project` itself performs
  its own internal `check_mapper_capacity` re-check *after* appending engine glue content
  (`nes/project_builder.py:236`), which can raise `ValueError` on an edge-case bank that's
  right at the MMC3 capacity ceiling once that extra content is folded in — a failure mode
  `run_full_pipeline`'s single outer `try/except Exception` (`main.py:1324`/`:1446`) is
  specifically designed to catch cleanly, and which `run_song_build` has no equivalent for.
- **Evidence**: `grep -n "_backup_existing_rom\|_restore_backup" main.py` returns exactly
  four lines, all inside `run_full_pipeline` and `run_compile`; zero inside
  `run_song_build`. `compile_rom`'s `output_path` argument (`compiler/compiler.py:268-283`)
  is the caller's literal `output_rom` — confirmed it links straight to that path, so any
  pre-existing file there is overwritten unconditionally by a successful `ld65` link,
  regardless of what `validate_rom` decides afterward.
- **Impact**: Two concrete scenarios: (1) A user iterating on a song bank re-runs
  `song build` at the same output path as a previously-good jukebox ROM; if the rebuild
  compiles but then fails `validate_rom` (bad vectors / no APU init — the same fatal-defect
  class `run_full_pipeline`/`run_compile` treat as build-blocking), the last-known-good ROM
  is already gone, overwritten in place, with no backup and no `<name>.nes.failed` rename to
  even flag that the file at `output_rom` is now broken. (2) Any exception `prepare_project`
  or a future change to `compile_rom` might raise propagates as a raw Python traceback to
  the user instead of the `[ERROR] ...` + clean `sys.exit(1)` pattern every other build path
  in this file uses.
- **Related**: `#26`/F-11 (Restore-on-failure, `run_full_pipeline`) and `#178`/PL-05
  (Validation-failed ROM left at output path, `run_compile`) — both closed; this finding is
  the same defect class reappearing in the one build path that wasn't updated to share the
  fix.
- **Suggested Fix**: Wrap `run_song_build`'s tail (from `_backup_existing_rom` through
  `compile_rom`/`validate_rom`) in the same `backup_path = _backup_existing_rom(output_rom)`
  / `try: ... build_succeeded = True finally: _restore_backup(...) or unlink backup`
  structure `run_compile` already uses (`main.py:586-605`) — the helpers are already
  general-purpose and take only `output_rom`/a backup path, so this is a direct reuse, not a
  new mechanism.

### PL-2026-08-07-3: Pre-subcommand `--arranger` rejection message is now stale for `song build`
- **Severity**: LOW
- **Dimension**: 3 (Flag Routing)
- **Both paths?**: N/A — CLI-parsing-only, affects discoverability of the new `song build
  --arranger` flag, not ROM output.
- **Location**: `main.py:1642-1651` (the `pre_subcommand_args` check that rejects
  `--arranger`/`-a` appearing before any subcommand name); `main.py:1592` (`p_song_build`'s
  own `--arranger` declaration).
- **Status**: NEW
- **Description**: `main()`'s subcommand dispatch rejects `--arranger`/`-a` placed *before*
  a subcommand token with: `"--arranger only applies to the default MIDI-to-ROM pipeline;
  there is no step-by-step equivalent yet."` That was accurate when written (no subcommand
  read `args.arranger`), but `song build` now declares and consumes its own `--arranger`
  flag (`p_song_build.add_argument('--arranger', ...)`, read via `getattr(args, 'arranger',
  False)` in `run_song_build`). The blanket rejection still fires for
  `python main.py --arranger song build bank.json out.nes` with a message that flatly denies
  any subcommand supports `--arranger`, when `song build` does — it just needs the flag
  placed *after* `build` (`python main.py song build bank.json out.nes --arranger`, verified
  working in this environment).
- **Evidence**: `python3 main.py --arranger song build x.json y.nes` → prints the "there is
  no step-by-step equivalent yet" error and exits 2; `python3 main.py song build x.json
  y.nes --arranger` → passes CLI parsing and reaches `run_song_build` (fails later only on
  the missing bank file, as expected).
- **Impact**: Purely a misleading diagnostic — a user who habitually puts `--arranger` first
  (matching the default-pipeline convention) gets told the flag doesn't exist for any
  subcommand, when moving it three tokens to the right would work. No functional or ROM
  impact; full workaround available (place `--arranger` after `build`).
- **Related**: `#174`/PL-01 (the original fix this message is part of).
- **Suggested Fix**: Special-case `song build` in the pre-subcommand check (or check
  `first_arg == 'song' and sys.argv[sys.argv.index(first_arg)+1:sys.argv.index(first_arg)+2]
  == ['build']` before rejecting) to point the user at `song build ... --arranger` instead
  of denying it exists.

### PL-2026-08-07-4: `metadata['order']` auto-assignment can collide after a `song remove` + `song add` cycle, now that it drives jukebox playback order
- **Severity**: LOW
- **Dimension**: 8 (Song-Bank Path)
- **Both paths?**: N/A — `song build` only; `order` was write-only (recorded but never read)
  before this commit.
- **Location**: `nes/song_bank.py:82` and `:121` (`order=len(self.songs)`, computed at add
  time in both `add_song_from_midi` and `add_song`); `main.py:873` (`run_song_remove`'s `del
  bank.songs[args.name]` — no renumbering of survivors' `order` values); `main.py:953-954`
  (`run_song_build`'s `sorted(bank.songs, key=lambda name:
  bank.songs[name]['metadata'].get('order', 0))` — the first real consumer of `order`).
- **Status**: NEW
- **Description**: `order` is assigned as `len(self.songs)` at the moment each song is
  added — effectively an auto-incrementing counter with no gap-filling. `song remove`
  deletes a dict entry without adjusting anyone else's `order`. A later `song add` computes
  its `order` from the *current* (now-smaller) `len(self.songs)`, which can collide with an
  `order` value a surviving song already has (e.g. add A(0), B(1), C(2); remove B; add D →
  `len(self.songs)` is 2 at that point, so D also gets `order=2`, tying with C). `main.py`'s
  own comment on this line calls out that `order` "was recorded at `song add` time but never
  consumed by anything until now" — i.e. this commit is what makes a collision
  behaviorally meaningful for the first time (it decides jukebox playback order via
  `sorted(...)`). In the cases traced by hand, Python's stable sort plus `dict` insertion-
  order semantics happen to still produce a reasonable (append-like) order on a tie, so this
  is not a high-likelihood practical failure — but it is an unguarded design gap with no
  collision detection, and a bank that's been edited (remove + add) several times, or a
  hand-edited bank JSON, has no guarantee against a genuinely surprising order.
- **Evidence**: Read of `add_song_from_midi`/`add_song` (`order=len(self.songs)`, both
  sites) and `run_song_remove` (`del bank.songs[args.name]`, no follow-up renumbering);
  traced by hand for add-add-remove-add sequences to confirm the collision is real but that
  the stable-sort tiebreak currently masks its user-visible effect in the simple cases
  checked.
- **Impact**: Low today (masked by stable-sort/insertion-order tiebreaking in the cases
  traced), but a latent correctness gap in a feature whose whole purpose is a specific
  song-playback order. No ROM corruption; worst case is songs playing in an order the user
  didn't intend, which is silently wrong rather than crash-prone.
- **Related**: None on GitHub; net-new consequence of #30/F-13 making `order` load-bearing.
- **Suggested Fix**: Either renumber remaining songs' `order` on `song remove`, or switch to
  a monotonically-increasing counter stored on the bank (never reused after a removal)
  instead of deriving `order` from the current song count.

## Verify-the-Fix Confirmations (re-checked this pass, no findings)

- **D2 — Parser parity**: `tracker.parser_fast.parse_midi_to_frames` is still the only
  parser imported anywhere on a live pipeline path, including the new
  `midi_to_frames_for_song` (`main.py:898`, local import mirroring `run_parse`/
  `run_full_pipeline`'s pattern) and `nes/song_bank.py`. No `tracker.parser` (full parser)
  import introduced.
- **D2/D5 — Single-song bytecode export unaffected**: `_build_song_bytecode`'s extraction
  (`exporter/exporter_ca65.py:1102`) is called by `export_tables_with_patterns` with
  `label_prefix=''`, `start_bank=0` (`:1485-1486`) — identical to the pre-extraction inline
  code by inspection, and confirmed live: a real single-song `python main.py
  test_midi/simple_loop.mid out.nes` build compiled, linked, and passed validation
  end-to-end in this environment (524,304-byte ROM, 100% pattern coverage), matching the
  2026-08-06 audit's prior confirmation.
- **D3 — `--debug` not silently accepted by `song build`**: `p_song_build` does not declare
  `--debug`; `python3 main.py song build x y --debug` correctly errors
  (`unrecognized arguments: --debug`, exit 2) rather than silently ignoring it — matches the
  documented v1 scope cut (`docs/ROADMAP.md`: "no `--debug` overlay support for jukebox
  builds").
- **D8 — DPCM rejection is not bypassable via a false-negative in `_song_has_dpcm_events`**:
  traced both `frames['dpcm']` producers (`nes/emulator_core.py:183-239` legacy path,
  `arranger/pipeline_integration.py:339-347` arranger path) — both always emit `note =
  min(255, id+1) >= 1` and `volume = 15` for every real drum hit, so
  `_song_has_dpcm_events`'s `note and volume` truthiness check (`main.py:920-923`) cannot
  miss a real hit from either producer.
- **D8 — `--mapper` correctly absent from `song build`**: `p_song_build` declares no
  `--mapper` flag; `run_song_build` hardcodes `MapperFactory.get_mapper('mmc3')`
  (`main.py:1004`), matching `docs/ROADMAP.md`'s stated v1 scope ("`--mapper` choice for
  `song build` ... always MMC3 today").
- **D8 — `docs/ROADMAP.md` accuracy**: the "Song banks → ROM" section (lines 57-78) was
  updated by this same commit and accurately describes what `song build` does and its
  documented v1 cuts (DPCM, `--mapper` choice, `--debug`, visual song-select) — no doc-rot
  found. It does not claim single-song-bank support one way or the other, so it isn't
  contradicted by PL-2026-08-07-1 above, but a follow-up fix should also note the caveat
  there once resolved.
- **D1/D4/D5/D6/D7 — unchanged pipeline stages**: re-confirmed via `git diff` that no
  `main.py` lines outside the new `run_song_build`/`midi_to_frames_for_song`/
  `_song_has_dpcm_events`/`song build` argparse block changed since `20f627e` (the
  2026-08-06 audited commit) — the `#377`/`#378`/`#379` LOW findings from that report are
  therefore still the current state of those dimensions (not re-verified line-by-line this
  pass, since nothing in their code paths moved).

## Notes on Non-`main.py` Changes (checked for contract impact only)

- `exporter/exporter_ca65.py`: the single-song bytecode-emission loop was refactored into
  `_build_song_bytecode(frames, label_prefix='', start_bank=0)`, reused by both
  `export_tables_with_patterns` (single song, defaults) and the new
  `export_song_bank_bytecode` (N songs, `song{i}_`-prefixed labels + fresh `start_bank` per
  song). The single-song call site's arguments are unchanged from what the pre-refactor
  inline code effectively used, and this was verified live (see D2/D5 above) rather than
  only by reading. `export_song_bank_bytecode` itself is new-and-only-used-by
  `run_song_build`, so its correctness is Dimension 8 territory (PL-2026-08-07-1 above);
  deeper macro/instrument-dedup correctness within it is `audit-exporters` territory, out of
  this skill's scope.
- `nes/audio_engine.asm`: all jukebox additions are `.ifdef JUKEBOX_BUILD`-gated as
  documented; confirmed the single-song (`JUKEBOX_BUILD` undefined) assembly path is
  unchanged byte-for-byte by re-running a real single-song build (see D2/D5 above). The gate
  itself is the mechanism PL-2026-08-07-1 falls through.
- `nes/project_builder.py`: `prepare_project`/`_generate_main_asm` gained the `song_count`
  parameter discussed in PL-2026-08-07-1; `check_mapper_capacity`'s ordering relative to
  the debug-overlay/DPCM-stub appends (a separate, pre-existing concern tracked as
  `#389`/MAP-2026-08-05-2 in `audit-mappers` territory) was not re-audited here — a comment
  at `nes/project_builder.py:223-236` now explicitly states the check runs on the *final*
  post-append `music.asm`, which reads as already resolved, but confirming that is squarely
  `audit-mappers`' dimension, not re-verified as part of this pass.
- `nes/song_bank.py`: `add_song`/`add_song_from_midi` now record `midi_path` (resolved to
  an absolute path at `song add` time) — see PL-2026-08-07-4 for the one gap found in the
  surrounding `order` metadata this feature also started consuming.

## Next Step

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-08-07.md
```
