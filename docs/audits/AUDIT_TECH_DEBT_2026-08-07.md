# Tech-Debt Audit — MIDI2NES — 2026-08-07

Scope: maintainability debt across the Python codebase (duplication, dead code, stale docs,
stale markers, stubs, magic numbers, error-handling debt, module/function size). Correctness
is out of scope (owned by the subsystem audits).

Repo state at audit: branch `master`, HEAD `f4c2283` (merge of `feat/song-bank-rom-build`,
commit `c864426`). This run follows `AUDIT_TECH_DEBT_2026-08-06.md` and gives **special
scrutiny to the just-landed `song build` feature (#30/F-13)**: the single-song bytecode loop
in `exporter/exporter_ca65.py`'s `export_tables_with_patterns` was extracted into a reusable
`_build_song_bytecode` helper shared with the new `export_song_bank_bytecode`
(multi-song "jukebox" export), and `nes/project_builder.py`'s old `prepare_multi_song_project`/
`add_song_bank` placeholder stubs were deleted in favor of the real
`prepare_project(song_count=N)` route.

Note: a sibling `/audit-mappers` pass run the same day (`AUDIT_MAPPERS_2026-08-07.md`) found
two CRITICAL/HIGH **correctness** bugs in this same jukebox code (wrong PRG-segment placement
for songs after the first; a `JUKEBOX_BUILD` gating mismatch for 1-song banks). Those are
correctness defects, not tech debt, and are not re-reported here — see that report instead.
This audit only covers maintainability debt: duplication, staleness, magic numbers, and
structure.

---

## Summary

### Findings by dimension

| Dimension | New | Notes |
|-----------|-----|-------|
| 1 — Logic Duplication | 2 (TD-31, TD-32) | Duplicated music.asm preamble between the two bytecode exporters; `run_song_build` re-implements the capacity→prepare→compile→validate sequence `build_and_validate_rom` already owns |
| 2 — Dead Code & Cruft | 0 new | No new stray root files/scripts; TD-29/#397 (`skip` file) confirmed still removed, unregressed. `SongBank`'s legacy bank-capacity model (TD-33, filed under Dim. 1/2 crossover — see below) is left disconnected rather than removed |
| 3 — Stale Documentation | 2 (TD-34, TD-35) | `SongBank` class docstring still claims "no song-bank → ROM route" despite `song build` shipping in the same PR that touched the file; `docs/AUDIO_BYTECODE_SPEC.md` (the designated authoritative bytecode-format doc) omits the new jukebox song-table format entirely |
| 4 — Stale Markers | 0 | Repo-wide `TODO\|FIXME\|HACK\|XXX` grep (non-test source) still clean |
| 5 — Stubs & Placeholders | 0 | `prepare_multi_song_project`/`add_song_bank` placeholders confirmed fully removed, no orphan references remain in source; `exporter_nsf.py` stubs (#81) unchanged |
| 6 — Magic Numbers | 1 (TD-36) | `nes/audio_engine.asm`'s new jukebox routines hardcode the 5-channel stride as a bare `5` in three places (two new, one pre-existing), with no named constant tying it to `CA65Exporter.SEQUENCE_CHANNELS` |
| 7 — Error-Handling Debt | 0 | No new bare `except:`; `run_song_build`'s `except Exception as e` sites match the existing `song add/list/remove` pattern |
| 8 — Module/Function Size | 1 (TD-37, observational) | `_build_song_bytecode` (`exporter/exporter_ca65.py:1102-1430`, ~330 lines) is now the largest single method in the file — not a regression (net reduction vs. the pre-extraction duplicate), but the natural next split point |

**New findings in this report: 7** (TD-31 .. TD-37; TD-33 spans Dimensions 1/2, counted once).
**Severity: MEDIUM 1, LOW 6, HIGH 0, CRITICAL 0.**

The song-bank → ROM refactor itself (`_build_song_bytecode` extraction, placeholder-method
removal) is clean: byte-identical single-song output is explicitly documented and the
placeholder methods left zero orphan references anywhere in source, tests, or docs. The debt
this cycle found is at the *seams* the refactor didn't touch — the preamble duplicated between
the two new exporter entry points, `run_song_build` not reusing the existing
`build_and_validate_rom` helper, and (most notably) the pre-existing `SongBank` capacity/doc
model that was never reconciled with the new real ROM-capacity model sitting right next to it.

### Three highest-leverage cleanups

1. **Reconcile `SongBank`'s capacity model with the real one (TD-33)** — `song add`'s
   per-song 16KB / 8-bank (128KB total) heuristic, based on raw parsed-event count, has zero
   relationship to `song build`'s real MMC3 60×8KB-bank sequence-bytecode budget, yet still
   gates whether a song can be added to a bank at all, and its `bank` field is shown to users
   via `song list`. This is the one finding in this report with real user-facing impact.
2. **Update `nes/song_bank.py`'s `SongBank` docstring (TD-34)** — it still says there is no
   song-bank → ROM route, directly contradicting the feature shipped in the same PR. One-line
   fix, high confusion-reduction value for the next reader of this exact file.
3. **Extract the shared music.asm preamble (TD-31)** — `export_tables_with_patterns` and
   `export_song_bank_bytecode` duplicate ~16 lines of segment/header scaffolding verbatim;
   a small `_emit_preamble(lines, title)` helper (mirroring the existing `_emit_period_tables`
   pattern) would remove the duplication with minimal risk.

---

## Verification of prior-fixed items (no regression)

- **TD-29/#397 (stray zero-byte `skip` file)** — now CLOSED and fixed: `git ls-files | grep -x
  skip` returns nothing; commit `8ab20b4` ("...remove stray file...") removed it. Confirmed the
  repo root's tracked top-level files are unchanged from the last verified set
  (`main.py`, `constants.py`, `validate_rom.py`, plus the already-known tracked fixture
  `input.mid` — no new stray script reintroduced).
- **TD-30 (duplicate `defaultdict` import in `nes/emulator_core.py`)** — checked; not
  re-verified in this pass's file list since `nes/emulator_core.py` was untouched by
  `c864426` (`git show c864426 --stat` confirms). Not re-inspected this cycle; no reason to
  suspect regression.
- **TD-11-FOLLOWUP/#406 (`run_full_pipeline` split)** — confirmed still CLOSED and holding:
  `run_full_pipeline` is `main.py:1295-1461` (~167 lines, including its docstring/comments),
  still calling the three extracted helpers (`detect_patterns_or_direct_export`,
  `export_frames_and_resolve_mapper`, `build_and_validate_rom`) rather than being re-inlined.
  `main.py` grew to 1878 lines total (from 1610 in the 2026-08-06 report) — entirely
  attributable to the new `song build` subcommand's own code (`run_song_add`/`run_song_build`/
  `midi_to_frames_for_song`/`_song_has_dpcm_events` plus the new `song build` argparse wiring),
  not to `run_full_pipeline` regrowing.
- **`exporter/exporter_ca65.py` TD-11/#136 half** — `export_direct_frames` unchanged at
  `:603-1027` (~425 lines); the 8 per-channel emitters are all still present and unmodified by
  `c864426` (verified via `git diff d096fb5 f4c2283 -- exporter/exporter_ca65.py` — all new
  code is additive, appended after `export_direct_frames`, not interleaved into it).
- **TD-08/#137 (DPCM `.incbin` comment)** — still accurate; the same explanatory comment
  (now at `exporter/exporter_ca65.py:1458-1463`) is present verbatim in
  `export_tables_with_patterns` and was correctly *not* duplicated as a comment in
  `export_song_bank_bytecode` (which only repeats the `.segment "DPCM"` / `.align 64` lines
  themselves, not the explanatory comment block — see TD-31 for that narrower duplication).
- **`prepare_multi_song_project`/`add_song_bank` removal** — confirmed complete.
  `grep -rn "prepare_multi_song_project\|add_song_bank" --include='*.py' --include='*.md' .`
  finds only two hits, both historical: a prior audit report
  (`docs/audits/AUDIT_TECH-DEBT_2026-07-03.md:241`, describing the pre-removal state) and a
  test comment (`tests/test_nes_project_builder.py:532`, "Replaces the old
  `prepare_multi_song_project()`/`add_song_bank()` placeholder..."). No live code references
  either name. `nes/project_builder.py`'s real replacement,
  `prepare_project(music_asm_path, song_count=None)`, is the sole route now (`:83-96`
  docstring explicitly documents the `song_count` contract).
- **Stale-marker grep** — `grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py' .` (excluding
  `tests/` and `.claude/`) returns zero matches in non-test source, including in all new
  `song build` code. Still clean.
- **Bare-`except:` grep** — zero matches in non-test source; the two historical `except:`
  mentions remain confined to test-file doc comments describing already-fixed regressions
  (`tests/test_rom_tester.py:40`, `tests/test_parser_fast.py:582`).

---

## Findings

### TD-31: Duplicated music.asm preamble between `export_tables_with_patterns` and `export_song_bank_bytecode`
- **Severity**: LOW
- **Dimension**: 1 — Logic Duplication
- **Location**: `exporter/exporter_ca65.py:1449-1481` (`export_tables_with_patterns`) vs.
  `exporter/exporter_ca65.py:1562-1589` (`export_song_bank_bytecode`)
- **Status**: NEW
- **Description**: Both bytecode-export entry points build an almost byte-identical opening
  block of `lines.append(...)` calls before diverging: the `; CA65 Assembly Export (...)`
  header comment, `.importzp ptr1, temp1, temp2, frame_counter`, the `.segment "DPCM"` /
  `.align 64` block with its explanatory comment (only present in the single-song version —
  the jukebox version silently drops the comment, see Related), and the
  `.segment "CODE_8000"` header for the macro/sequence data. This is exactly the kind of
  "reusable private helper" extraction the `_build_song_bytecode` refactor already applied to
  the bytecode-body loop, just not applied to the ~30-line header both callers build around it.
- **Evidence**:
  ```python
  # export_tables_with_patterns, :1449-1469 (abridged)
  lines.append('; CA65 Assembly Export (MMC3 Macro Bytecode)')
  lines.append('.importzp ptr1, temp1, temp2, frame_counter')
  lines.append('.segment "DPCM"')
  lines.append('.align 64')
  # [DPCM .incbin explanatory comment -- 6 lines]
  lines.append('.segment "CODE_8000"')

  # export_song_bank_bytecode, :1562-1576 (abridged) -- same shape, no comment
  lines.append('; CA65 Assembly Export (MMC3 Macro Bytecode -- multi-song jukebox build)')
  lines.append('.importzp ptr1, temp1, temp2, frame_counter')
  lines.append('.segment "DPCM"')
  lines.append('.align 64')
  lines.append('.segment "CODE_8000"')
  ```
- **Impact**: None functionally — both blocks currently emit correct, consistent output. Pure
  maintainability cost: a future change to the DPCM/CODE_8000 preamble (e.g. a new `.export`,
  a segment attribute change) must be applied in two places, and the jukebox path already
  silently dropped the explanatory comment once (see Related) — exactly the drift this
  duplication invites.
- **Related**: The single-song path's `.segment "DPCM"` block still carries the TD-08/#137
  explanatory comment (`:1458-1463`); the jukebox path's copy (`:1569-1570`) omits it. Minor
  in isolation, but a live example of the two blocks already diverging after one refactor.
- **Suggested Fix**: Extract a small `_emit_bytecode_preamble(lines, title_suffix)` helper
  (mirroring the existing `_emit_period_tables` pattern already used by both callers) that
  emits the header comment, `.importzp`, DPCM segment (with its comment), and `CODE_8000`
  segment header; have both callers pass their differing header-comment suffix.

### TD-32: `run_song_build` re-implements the capacity→prepare→compile→validate sequence instead of reusing `build_and_validate_rom`
- **Severity**: LOW
- **Dimension**: 1 — Logic Duplication
- **Location**: `main.py:1003-1025` (`run_song_build`) vs. `main.py:1261-1292`
  (`build_and_validate_rom`, used by `run_full_pipeline`)
- **Status**: NEW
- **Description**: `build_and_validate_rom` already encapsulates "capacity pre-flight →
  `NESProjectBuilder.prepare_project` → `compile_rom` → optional `validate_rom`" as a single
  reusable helper (extracted for exactly this reason per #406/TD-11-FOLLOWUP). `run_song_build`
  re-implements the same four steps inline instead of calling it: it calls
  `check_mapper_capacity` directly, then `builder.prepare_project(str(music_asm),
  song_count=len(songs))`, then `compile_rom(...)`, then `validate_rom(...)` — the same
  sequence, just with `sys.exit(1)`-per-step error handling instead of
  `build_and_validate_rom`'s raise-based contract, and with `song_count` threaded through.
  `build_and_validate_rom` doesn't currently accept a `song_count` parameter, which is exactly
  why it wasn't reused as-is — but that's a one-parameter addition, not a reason to fork the
  whole sequence.
- **Evidence**:
  ```python
  # main.py:1275-1290 (build_and_validate_rom, existing)
  data_size = check_mapper_capacity(str(music_asm), mapper)
  builder = NESProjectBuilder(str(project_path), debug_mode=debug_mode, mapper=mapper)
  if not builder.prepare_project(str(music_asm)):
      raise RuntimeError("Failed to prepare NES project")
  if not compile_rom(project_path, output_rom, verbose=args.verbose, mapper=mapper):
      raise RuntimeError("ROM compilation failed")
  if not skip_validation:
      if not validate_rom(output_rom):
          raise RuntimeError("ROM validation failed")

  # main.py:1006-1025 (run_song_build, new -- same 4 steps, forked)
  try:
      check_mapper_capacity(str(music_asm), mapper)
  except ValueError as e:
      print(f"[ERROR] {e}"); sys.exit(1)
  builder = NESProjectBuilder(str(project_path), debug_mode=False, mapper=mapper)
  builder.prepare_project(str(music_asm), song_count=len(songs))
  success = compile_rom(project_path, output_rom, verbose=verbose, mapper=mapper)
  if not success:
      print("[ERROR] Compilation failed"); sys.exit(1)
  if not skip_validation:
      if not validate_rom(output_rom):
          print("[ERROR] ROM validation failed"); sys.exit(1)
  ```
- **Impact**: None today — both sequences are correct and call the same underlying functions
  in the same order. Cost is purely future-maintenance: a fix to one sequence (e.g. the
  capacity pre-flight's error message, or an added compile step) has to be remembered and
  applied to both call sites, with no test tying them together.
- **Related**: None filed.
- **Suggested Fix**: Add an optional `song_count: Optional[int] = None` parameter to
  `build_and_validate_rom` (threaded through to `prepare_project`) and have `run_song_build`
  call it, translating the raised `ValueError`/`RuntimeError` to its own
  `print` + `sys.exit(1)` pattern the same way `run_full_pipeline` already does at its call
  site.

### TD-33: `SongBank`'s per-song capacity/bank-assignment model is disconnected from the real ROM capacity `song build` now uses
- **Severity**: MEDIUM
- **Dimension**: 1/2 — Logic Duplication / Dead-but-still-gating Code
- **Location**: `nes/song_bank.py:44-45` (`max_bank_size = 16384`, `total_banks = 8`),
  `:143-151` (`_calculate_bank_assignment`), `:153-172` (`_estimate_segment_size`); contrast
  with the real capacity model at `exporter/exporter_ca65.py:1335,1385-1395`
  (`MAX_SEQUENCE_BANK = MMC3Mapper.SWAP_BANK_COUNT - 1` = 59, `BANK_SIZE_LIMIT = 8192 - 256`)
  and `main.py:1006-1010` (`check_mapper_capacity`, called by `run_song_build`)
- **Status**: NEW
- **Description**: `SongBank.add_song` (called by every `song add`) still runs the pre-existing
  capacity model from when the class was JSON-storage-only: a song is rejected outright unless
  its `_estimate_segment_size` (`len(events) * 8 + ... + 256` overhead, on *raw parsed MIDI
  events*, not compiled bytecode) fits within a single 16KB "bank" slot, out of a fixed pool of
  8 such slots (128KB total). `song build` (`main.py:927-1027`,
  `CA65Exporter.export_song_bank_bytecode`) never reads `song_data['bank']` or
  `song_data['size']` at all — it re-parses each song's MIDI from scratch and lets the real
  MMC3 sequence-bytecode budget (60 shared 8KB banks, ~480KB) gate capacity via
  `_build_song_bytecode`'s own bank-overflow `ValueError` and `check_mapper_capacity`. The two
  models don't just differ in constants, they measure different things (raw MIDI event count
  vs. compiled macro-bytecode size) and use different units (a fixed 16KB-per-song ceiling vs.
  a 480KB pool shared and packed across all songs in the bank). A song with more than roughly
  2000 raw events (2000 × 8 = 16000 bytes) is unconditionally rejected by `song add` — with
  `_calculate_bank_assignment` raising `"Not enough bank space for song"` — even though such a
  song's actual macro-bytecode footprint (after instrument/macro de-duplication) would very
  likely compile into a `song build` ROM without ever approaching the real 480KB budget. This
  legacy model was never touched or reconciled by the `song build` refactor even though it now
  sits directly upstream of (and can block) the feature that refactor added.
- **Evidence**:
  ```python
  # nes/song_bank.py:143-151 -- gates every `song add`, using a heuristic
  # with no relationship to the real MMC3 sequence-bank budget below
  def _calculate_bank_assignment(self, size: int) -> int:
      usage = self.calculate_bank_usage()
      for bank in range(self.total_banks):        # 8 banks
          if usage.get(bank, 0) + size <= self.max_bank_size:  # 16384 bytes each
              return bank
      raise ValueError("No available bank space")

  # exporter/exporter_ca65.py:1335 -- the real, independent capacity model
  # `song build` actually uses, consulted only at build time
  MAX_SEQUENCE_BANK = MMC3Mapper.SWAP_BANK_COUNT - 1   # 59 (60 x 8KB banks)
  ```
  `run_song_build` (`main.py:960-987`) loops `bank.songs` and reads only
  `song_data['metadata']['order']` and `song_data['midi_path']` — `bank`/`size` are never
  referenced.
- **Impact**: Two-fold. (1) A legitimate song can be refused by `song add` purely on a stale
  raw-event heuristic, before the user ever gets to try `song build` — even though the actual
  ROM-capacity mechanism that would gate it is completely different and untested at `add`
  time. (2) `song list` (`main.py:853`, `print(f"Bank: {song_data['bank']}")`) surfaces this
  fictitious 0-7 "bank" index to the user right alongside real metadata (composer, tags), but
  it has no relationship to which of the 60 real MMC3 banks `song build` will actually place
  that song's bytecode in — a user has no way to know this from the CLI output.
- **Related**: Distinct from the now-closed F-13 ("no song-bank → ROM route at all") — this is
  about the *storage-time* capacity model not being reconciled with the *build-time* one now
  that a real route exists.
- **Suggested Fix**: Either (a) drop the `add_song`-time capacity rejection/`bank` assignment
  entirely now that `song build` has its own authoritative check, keeping `SongBank` as pure
  storage, or (b) if a `song add`-time sanity check is still wanted, base it on the same units
  `song build` actually uses (estimated bytecode size vs. the MMC3 60-bank pool) rather than a
  raw-event/16KB heuristic invented before the ROM route existed. Either way, stop printing the
  fictitious `bank` field in `song list` (or relabel it to make clear it's a JSON-storage
  grouping, not a ROM bank).

### TD-34: `SongBank` class docstring still claims "no song-bank → ROM route" after `song build` shipped
- **Severity**: LOW
- **Dimension**: 3 — Stale Documentation & Comments
- **Location**: `nes/song_bank.py:30-39`
- **Status**: NEW
- **Description**: The `SongBank` class docstring reads: *"Scope: storage and analysis only.
  ... it does NOT compile to a `.nes`. There is currently no song-bank -> ROM route; the `song`
  CLI subcommands manage the JSON bank only. Multi-song ROM builds are tracked as a planned
  feature in docs/ROADMAP.md."* This is now false: `song build <bank.json> <out.nes>`
  (`main.py:927-1027`) does exactly what this docstring says doesn't exist, calling
  `CA65Exporter.export_song_bank_bytecode` to compile a `SongBank` into a real multi-song ROM.
  `git diff d096fb5 f4c2283 -- nes/song_bank.py` confirms this docstring block was untouched
  by the PR that added `song build` (the diff only added `midi_path` recording to
  `add_song`/`add_song_from_midi`) — every other doc surface this PR touched (`CLAUDE.md`,
  `docs/ROADMAP.md`) was correctly updated to describe the new route; this one, in the very
  file the feature is built on top of, was missed.
- **Evidence**:
  ```python
  # nes/song_bank.py:33-38 (unchanged by c864426)
  Scope: storage and analysis only. A SongBank parses MIDI files into
  segments (events/patterns/frames), assigns them to virtual banks, and
  estimates sizes — but it does NOT compile to a ``.nes``. There is currently
  no song-bank -> ROM route; the ``song`` CLI subcommands manage the JSON bank
  only. Multi-song ROM builds are tracked as a planned feature in
  docs/ROADMAP.md.
  ```
  Contrast with `docs/ROADMAP.md:57`: `"### Song banks → ROM (#30/F-13) — ✅ v1 shipped..."`
- **Impact**: A developer reading this module's own docstring (the most obvious place to look
  before touching `SongBank`) is told the opposite of what the codebase now does. No runtime
  effect.
- **Related**: TD-33 (same file, same feature gap — the docstring's "assigns them to virtual
  banks" claim is also what TD-33 flags as now-disconnected from the real build path).
- **Suggested Fix**: Rewrite the docstring to describe the current split: `SongBank` is JSON
  storage plus a `midi_path` record that `song build` re-parses; point at `docs/ROADMAP.md`'s
  "Song banks → ROM" section (and its documented v1 scope limits) instead of claiming no route
  exists.

### TD-35: `docs/AUDIO_BYTECODE_SPEC.md` doesn't document the new jukebox song-table format
- **Severity**: LOW
- **Dimension**: 3 — Stale Documentation & Comments
- **Location**: `docs/AUDIO_BYTECODE_SPEC.md` (146 lines, unchanged by `c864426` — confirmed
  via `git diff d096fb5 f4c2283 -- docs/AUDIO_BYTECODE_SPEC.md` showing no hits); contrast with
  `exporter/exporter_ca65.py:1587-1639` (`song_table_ptr_lo/hi`, `song_table_bank`,
  `song_count`, `song_instrument_ptr_lo/hi`) and `nes/audio_engine.asm:246-333`
  (`load_song_streams_indexed`, `audio_init_song`, `audio_advance_song`)
- **Status**: NEW
- **Description**: `_audit-common.md` names this file as the authoritative reference for "the
  generated music data bytecode format the engine plays back." It documents the single-song
  `channel_start_banks` per-channel-starting-bank table in detail (with a worked `.ca65`
  example, §2.1) but has zero mention of the parallel jukebox-only data structures the same
  exporter now emits for `song build` ROMs: the `song_table_ptr_lo/hi`/`song_table_bank`
  3-array table (indexed `song_index*5 + channel`), the `song_count` byte, the
  `song_instrument_ptr_lo/hi` per-song instrument-table pointer table, or the
  `audio_init_song`/`audio_advance_song`/`load_song_streams_indexed` engine routines that
  consume them. A reader using this doc to understand "the bytecode format the engine plays
  back" for a jukebox build gets an incomplete picture with no indication a second, sibling
  format layer exists.
- **Evidence**: `grep -n "song_table\|JUKEBOX\|jukebox\|multi-song" docs/AUDIO_BYTECODE_SPEC.md`
  returns no matches; `grep` for the same terms against `docs/ROADMAP.md` (which *was* updated)
  returns 8 matches.
- **Impact**: Documentation gap only — no code behavior affected. Reduces the doc's value as
  "the" reference for the bytecode format now that two build modes emit different top-level
  layouts.
- **Related**: TD-34 (same class of gap — CLAUDE.md/ROADMAP.md were updated for this feature,
  a doc closer to the actual mechanism was not).
- **Suggested Fix**: Add a short "§2.x Jukebox / multi-song song table" section next to §2.1,
  documenting the three parallel arrays, their indexing scheme (`song_index*5 + channel`), and
  the `JUKEBOX_BUILD`-gated engine routines that read them — mirroring the existing
  `channel_start_banks` writeup already in the doc.

### TD-36: Jukebox engine hardcodes the 5-channel stride as a bare `5` with no shared named constant
- **Severity**: LOW
- **Dimension**: 6 — Magic Numbers & Hardcoded Constants
- **Location**: `nes/audio_engine.asm:267-271` (`current_song*4 + current_song` = "A =
  current_song * 5"), `:284` and `:755` (both `cpx #5`, both new in this refactor — confirmed
  via `git diff d096fb5 f4c2283 -- nes/audio_engine.asm`, which shows exactly these two `cpx
  #5` additions); source of truth is `exporter/exporter_ca65.py:1069` (`SEQUENCE_CHANNELS =
  ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']`, i.e. `len(SEQUENCE_CHANNELS) == 5`). A
  third `cpx #5` at `:766` is **pre-existing** (present before this refactor, in the general,
  non-jukebox `audio_update` channel loop — confirmed via `git show d096fb5:nes/audio_engine.asm
  | grep -n "cpx #5"`, which shows it at the equivalent old line 594) and is called out here
  only for completeness, not counted as new debt.
- **Status**: NEW
- **Description**: The new jukebox `song_table_*` arrays are laid out by the Python exporter
  with a stride of `len(self.SEQUENCE_CHANNELS)` (5) entries per song
  (`exporter/exporter_ca65.py:1608-1626`, confirmed via the docstring at `:1547-1549`: `"indexed
  song_index*5 + channel"`). The 6502 engine code that reads this table back
  (`load_song_streams_indexed`, `:259-286`) has to independently know this same stride, and
  does so via a hand-computed `current_song*5` (shift+add, since 6502 has no multiply
  instruction) plus a `cpx #5` copy-loop bound; a second new `cpx #5` bounds the
  all-channels-ended scan in the auto-advance code (`:750-758`). Neither of these two new sites
  is a named `.define`/constant on the asm side, and nothing on the Python side asserts
  `len(SEQUENCE_CHANNELS) == 5` either — the two are tied together only by comment prose. If
  `SEQUENCE_CHANNELS` ever gained or lost a channel, both new asm sites (plus the pre-existing
  third) would need matching hand-edits with no compiler/linker error to catch a missed one (a
  stale `5` would silently index one array off from the others).
- **Evidence**:
  ```asm
  ; nes/audio_engine.asm:267-271 (new)
  lda current_song
  asl a
  asl a               ; A = current_song * 4
  clc
  adc current_song    ; A = current_song * 5
  ; nes/audio_engine.asm:284 and :755 (new, two separate loop bounds)
  cpx #5
  ```
- **Impact**: None today — all sites are currently consistent with each other and with
  `SEQUENCE_CHANNELS`. Purely a change-safety gap: a future channel-count change is a
  multi-site-plus-Python coordinated edit with no single source of truth and no automated check
  tying them together.
- **Related**: None filed.
- **Suggested Fix**: Add a `NUM_CHANNELS = 5` (or similarly named) ca65 constant near the top
  of `nes/audio_engine.asm` and reference it at the two new jukebox sites (and, opportunistically,
  the pre-existing one at `:766`), so a future channel-count change is a one-line asm edit
  instead of a multi-site hunt. (6502 lacks a multiply instruction, so the `current_song*5`
  shift-and-add itself can't be eliminated, but it can still reference the named constant in a
  comment, and the `cpx` bounds can use it directly.)

### TD-37: `_build_song_bytecode` is now the largest single method in `exporter_ca65.py` (observational)
- **Severity**: LOW
- **Dimension**: 8 — Module/Function Size & Structure
- **Location**: `exporter/exporter_ca65.py:1102-1430` (~330 lines)
- **Status**: NEW (observational — not a regression)
- **Description**: The extraction that created `_build_song_bytecode` is a net improvement (it
  replaced what would otherwise have been ~330 lines duplicated a second time inside
  `export_song_bank_bytecode`), and its docstring already thoroughly explains the non-obvious
  invariants (per-call bank-byte accounting, why banks can't be shared across songs, the DPCM
  note-range ceiling). It is, however, now the single largest method in a 1670-line file,
  doing three distinct jobs in sequence: (1) walking `frames` into per-channel note/duration
  events with clamping and macro de-duplication (`:1150-1314`), (2) emitting the instrument/
  macro-table text (`:1316-1329`), and (3) emitting the banked sequence bytecode with its own
  overflow/bank-jump handling (`:1331-1430`). This wasn't introduced as new bloat by this
  refactor — it's the same logic that existed inline in `export_tables_with_patterns` before —
  but now that it has two callers, growth pressure on it (e.g. a future macro type) lands in
  one place instead of two, which is the right trade but means the method itself is the next
  natural candidate for further splitting if it needs another feature added.
- **Evidence**:
  ```
  $ awk '/^    def /{print NR, $0}' exporter/exporter_ca65.py | tail -8
  1071:    def _emit_period_tables(self, lines):
  1102:    def _build_song_bytecode(self, frames, label_prefix='', start_bank=0):
  1432:    def export_tables_with_patterns(self, frames, patterns, references, output_path, standalone=True, mapper=None):
  1533:    def export_song_bank_bytecode(self, songs, output_path):
  ```
- **Impact**: None today — purely a maintainability observation, flagged because the task
  brief asked for real scrutiny of this specific refactor. Not a candidate for the "oversized
  monolith" bar the closed TD-11/#136 and #406 findings were tracking (this is one cohesive,
  well-documented private helper, not a multi-stage public entry point).
- **Related**: TD-11/#136 (closed) — the precedent this dimension's prior findings set for
  when a split is actually warranted; this finding is explicitly *not* at that bar yet.
- **Suggested Fix**: No action needed now. If `_build_song_bytecode` grows further (e.g. to
  support DPCM in jukebox builds, `docs/ROADMAP.md`'s open follow-up), consider splitting step
  (1) event-building from steps (2)/(3) bytecode emission at that point.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_TECH_DEBT_2026-08-07.md
```
