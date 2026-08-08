# Exporters Audit — 2026-08-07

Scope: `exporter/exporter_ca65.py` (default CA65 path — `export_direct_frames`,
the MMC3 macro-bytecode `export_tables_with_patterns`, and the new song-bank
"jukebox" serializer `export_song_bank_bytecode`), `exporter/exporter_nsf.py`,
`exporter/exporter_famistudio.py`, and their consumers (`nes/project_builder.py`,
`nes/audio_engine.asm`, `main.py` export/song-build dispatch). Cross-checked
against `docs/AUDIO_BYTECODE_SPEC.md`, `docs/MACRO_USAGE_GUIDE.md`, and
`docs/ROADMAP.md`.

Since the last exporter audit (`AUDIT_EXPORTERS_2026-08-06.md`, 0 findings),
one commit touched `exporter/`: `c864426` (#30/F-13, "song bank -> ROM —
multi-song 'jukebox' builds"). It refactors the single-song bytecode-emission
loop out of `export_tables_with_patterns` into a reusable private helper
`_build_song_bytecode(frames, label_prefix='', start_bank=0)` and adds a new
public method `export_song_bank_bytecode(songs, output_path)` that calls the
helper once per song with a `song{i}_` prefix, then emits a combined
`song_table` in place of the single-song `channel_start_banks`. This audit
re-derived the "byte-identical" refactor claim directly (see Verification
below) rather than trusting the commit message/docstring, and gave the new
multi-song code its own scrutiny rather than treating it as boilerplate
extension of already-audited code.

## Summary

### Counts by severity
| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 1 |
| LOW      | 2 |
| **Total**| **4** |

### Counts by dimension
| Dimension | Count |
|-----------|-------|
| D1 CA65 well-formedness / builder compat | 3 |
| D2 APU register serialization | 0 |
| D3 Pattern-vs-empty paths | 0 |
| D4 Byte-range safety | 0 |
| D5 Bytecode-spec conformance | 1 |
| D6 Macro emission | 0 |
| D7 Cross-exporter consistency | 0 |
| D8 Format-string / CLI choices | 0 |

### Three highest-impact findings
1. **EXP-2026-08-07-1 (HIGH)** — `song build` on a bank with exactly one song
   fails to link: `export_song_bank_bytecode` always emits jukebox-format
   symbols, but `nes/project_builder.py`'s `JUKEBOX_BUILD` gate only fires for
   `song_count > 1`. Independently confirmed via a real CC65 build in this
   audit; already found and documented in depth by two sibling audits run in
   parallel today (see Dedup note in the finding).
2. **EXP-2026-08-07-2 (MEDIUM)** — `export_song_bank_bytecode`/
   `_build_song_bytecode` have no self-contained guard against a DPCM channel
   in a song's frames; the only enforcement is a caller-side check in
   `main.py`'s `run_song_build`. Calling the exporter method directly (a
   plausible library-consumer path) silently emits DPCM sequence bytecode
   against a table the exporter never defines.
3. **EXP-2026-08-07-3 (LOW)** — `docs/AUDIO_BYTECODE_SPEC.md` documents none
   of the new jukebox-only data structures (`song_table_ptr_lo/hi`,
   `song_table_bank`, `song_count`, `song_instrument_ptr_lo/hi`) the exporter
   now emits.

The default `python main.py input.mid output.nes` CA65 path (both
`export_direct_frames` and single-song `export_tables_with_patterns`) is
**unaffected by this commit** and remains clean — confirmed by direct
byte-diff (see Verification), not just by reading the refactor's docstring.

## Verification: refactor claimed "byte-identical to before"

`_build_song_bytecode`'s docstring and the commit message both assert
`export_tables_with_patterns` calling the extracted helper with `label_prefix=''`,
`start_bank=0` produces output identical to the pre-refactor inline loop. Rather
than trust this, the pre-refactor `exporter/exporter_ca65.py` (`git show
c864426^:exporter/exporter_ca65.py`) was loaded side-by-side with the current
module and both were run against the same synthetic `frames` (5 active
channels, 40 frames, mixed notes/silences) through `export_tables_with_patterns`
with a non-empty `patterns` dict (selecting the bytecode path). `diff` on the
two `.asm` outputs is empty — confirmed byte-identical, corroborating the
existing golden-byte tests (`tests/test_ca65_export.py`) rather than
duplicating them.

## Findings

### EXP-2026-08-07-1: `song build` on a single-song bank fails to link (jukebox symbols emitted below the `JUKEBOX_BUILD` threshold)
- **Severity**: HIGH
- **Dimension**: 1 (CA65 Assembly Well-Formedness & Builder Compatibility)
- **Spec ref**: consumer `nes/project_builder.py` (`JUKEBOX_BUILD` gate) and `nes/audio_engine.asm` (`.ifdef JUKEBOX_BUILD` routines)
- **Location**: `exporter/exporter_ca65.py:1533-1670` (`export_song_bank_bytecode` — never special-cases `len(songs) == 1`, always emits `.import audio_init_song, audio_advance_song` and `init_music: jmp audio_init_song` at `:1645-1649`), `main.py:927-1027` (`run_song_build` — unconditionally calls `export_song_bank_bytecode` then `builder.prepare_project(..., song_count=len(songs))` for any `len(songs) >= 1`, no separate 1-song path), `nes/project_builder.py:308,336` (`JUKEBOX_BUILD` is only defined / `jukebox_mode` is only `True` when `song_count > 1`), `nes/audio_engine.asm:22-25,134-185,246-333` (`.ifdef JUKEBOX_BUILD` is the *only* place `audio_init_song`/`audio_advance_song`/`load_song_streams_indexed` are defined; with it undefined, `audio_init`'s `.else` branch — referencing the fixed single-song labels `pulse1_sequence`/`channel_start_banks`/`instrument_table`/etc. that a jukebox `music.asm` never defines — is what assembles instead).
- **Status**: NEW (no matching open/closed GitHub issue; feature landed same day in commit `c864426`)
- **Description**: `run_song_build` always serializes a song bank through the
  jukebox-format exporter (`export_song_bank_bytecode`) regardless of how many
  songs it contains, and always forwards that same count as `song_count` to
  `prepare_project`. But `prepare_project`/`_generate_main_asm` treat
  `song_count == 1` as "ordinary single-song project, do not touch
  `audio_engine.asm`'s jukebox branches" — a threshold that assumes a 1-song
  build would go through the *other* exporter (`export_tables_with_patterns`).
  `run_song_build` never makes that distinction, so for a 1-song bank the two
  halves of the build disagree: the emitted `music.asm` is in jukebox format
  (`song0_pulse1_sequence`, `song_table_*`, `jmp audio_init_song`) while
  `audio_engine.asm` assembles in **non**-jukebox mode (references
  `pulse1_sequence`, `channel_start_banks`, `instrument_table`, and
  `audio_init_song` is never even defined). This is exactly the class of
  producer/consumer contract break `_audit-common.md` floors at HIGH.
- **Evidence**: Live reproduction against this exact commit, using the
  system's real `ca65`/`ld65`, via the actual `song build` CLI path:
  ```
  $ python3 main.py song build bank.json out.nes -v --dpcm-index dpcm_index.json
    (bank.json built from test_midi/simple_loop.mid, 1 song)
  🔧 CA65 Exporter: MMC3 Macro Bytecode mode (1-song jukebox build)
  ✅ Macro Bytecode jukebox export complete: .../music.asm (1 songs, 1 bank(s) used)
  🔨 Compiling 1-song jukebox ROM...
  [ERROR] Failed to link ROM: ...
  Unresolved external 'audio_init_song' referenced in: .../music.asm(192)
  Unresolved external 'channel_start_banks' referenced in: .../audio_engine.asm(155,162,169,176,183)
  Unresolved external 'instrument_table' referenced in: .../audio_engine.asm(494,494,495,495,505,505,511,511)
  Unresolved external 'pulse1_sequence'/'pulse2_sequence'/'triangle_sequence'/'noise_sequence'/'dpcm_sequence' ...
  ld65: Error: 8 unresolved external(s) found - cannot create output file
  [ERROR] Compilation failed
  ```
  A control run with the same bank plus a second song (`song_count=2`,
  `JUKEBOX_BUILD` correctly defined) compiled, linked, and produced a working
  524,304-byte ROM in the same environment — isolating the break to exactly
  the `song_count == 1` boundary, not a general jukebox-format problem.
  `tests/test_main.py::TestRunSongBuild::test_skip_validation_skips_validate_rom`
  is the only existing test that builds a 1-song bank through
  `run_song_build`, but it mocks `NESProjectBuilder` entirely (`mock_builder_class.return_value = Mock()`),
  so it never exercises the real `prepare_project`/CC65 interaction that this
  bug lives in; the only real-CC65 jukebox test
  (`tests/test_ca65_export.py::TestJukeboxCompilationIntegration::test_two_song_jukebox_rom_compiles_and_passes_diagnostics`)
  uses 2 songs, matching the commit message's "Verified with a real CC65
  build (2-song jukebox ROM...)".
- **Impact**: `python main.py song build <bank.json> <out.nes>` produces no
  ROM at all for any song bank containing exactly one song — the most likely
  first thing a new user tries (add one song, build before adding a second).
  The failure surfaces loudly (`ld65` nonzero exit → `compile_rom` returns
  `False` → `run_song_build` exits 1), so it is not silent data corruption,
  but it makes the shipped `song build` subcommand non-functional for its
  smallest legal input. The ordinary single-song pipeline
  (`python main.py input.mid out.nes`) remains an unaffected workaround, but
  it does not exercise the song-bank route at all.
- **Related**: New feature #30/F-13. **Dedup note**: this exact defect (root
  cause, evidence, and CC65 reproduction) was independently found and
  documented in full by two sibling audits run in parallel today:
  `docs/audits/AUDIT_NES_HARDWARE_2026-08-07.md` (`NH-HW-2026-08-07-1`, HIGH)
  and `docs/audits/AUDIT_PIPELINE_2026-08-07.md` (`PL-2026-08-07-1`, HIGH).
  Verified independently here from the exporter's own call graph rather than
  copied from either report. Recommend filing **one** GitHub issue for all
  three, not three duplicates.
- **Suggested Fix**: Either (a) have `run_song_build` fall back to
  `export_tables_with_patterns` + `song_count=None` when `len(songs) == 1`
  (matching `prepare_project`'s documented single-song contract), or (b) make
  the `JUKEBOX_BUILD` threshold `song_count and song_count >= 1` specifically
  for music.asm produced by `export_song_bank_bytecode`. Add a real
  (non-mocked) CC65 round-trip test for exactly `song_count == 1` alongside
  the existing 2-song coverage.

### EXP-2026-08-07-2: `export_song_bank_bytecode` has no self-contained guard against DPCM channels — enforcement lives entirely in the CLI caller
- **Severity**: MEDIUM
- **Dimension**: 1 (CA65 Assembly Well-Formedness & Builder Compatibility)
- **Spec ref**: `nes/project_builder.py` DPCM-table stub logic (`:202-217`); `docs/ROADMAP.md` ("`song build` currently rejects any song ... DPCM/drums")
- **Location**: `exporter/exporter_ca65.py:1102-1430` (`_build_song_bytecode` — the DPCM per-note guard at `:1198-1209` only checks `note >= 0x60`, never "is this song's DPCM channel non-empty at all"), `:1533-1670` (`export_song_bank_bytecode` — no DPCM check at the song level, no docstring mention of the restriction); the only actual enforcement is `main.py:910-924` (`_song_has_dpcm_events`) called from `run_song_build` at `:980`.
- **Status**: NEW
- **Description**: v1 `song build` explicitly does not support DPCM in
  multi-song ROMs (per `docs/ROADMAP.md` and `main.py`'s
  `_song_has_dpcm_events` check) because DPCM sample *data* packing has no
  per-song bank-range treatment yet — only the sequence bytecode does. But
  that restriction is enforced nowhere inside `exporter_ca65.py` itself; it
  is purely a `main.py`-side pre-check on the caller's `frames`. Every other
  hard invariant this same file enforces (instrument count > 256, DPCM note
  ≥ `$60`, sequence bank budget) raises a `ValueError` from inside the
  exporter. This one doesn't. Confirmed by calling the public method
  directly, bypassing `main.py`:
  ```python
  from exporter.exporter_ca65 import CA65Exporter
  exp = CA65Exporter()
  songs = [{'frames': {'pulse1': {'0': {'note': 60, 'volume': 10}}}},
           {'frames': {'dpcm': {'0': {'note': 5, 'volume': 15}},
                       'pulse1': {'0': {'note': 60, 'volume': 10}}}}]
  exp.export_song_bank_bytecode(songs, 'out.asm')
  # -> succeeds, emits a real song1_dpcm_sequence with note bytes, no error
  ```
  The resulting `song1_dpcm_sequence` triggers the shared engine's DPCM
  playback path, which indexes `dpcm_bank_table`/`dpcm_pitch_table`/
  `dpcm_addr_table`/`dpcm_len_table` by `sample_id`. Since no `DpcmPacker`
  runs in the `song build` flow, `nes/project_builder.py`'s fallback stub
  (`:209-217`) defines each of those tables as a single `.byte $00` — any
  `sample_id > 0` read from a genuinely triggered DPCM note reads past the
  1-byte stub into whatever RODATA happens to follow, feeding garbage
  bank/address/length values into a real DMC DMA trigger (`sta $4012`/
  `$4013`/`$4015`).
- **Impact**: Confined today because `main.py:run_song_build` is the only
  caller and it always pre-checks. But it is a real API robustness gap on a
  public `CA65Exporter` method: any other caller (a test, a future CLI flag,
  a library consumer) that reaches `export_song_bank_bytecode` with
  DPCM-bearing `frames` gets silent acceptance and a ROM whose DPCM channel
  reads out-of-bounds table data instead of a clear rejection — the same
  failure class the file already guards against everywhere else it applies
  an invariant.
- **Related**: #30/F-13 (v1 scope note in `docs/ROADMAP.md`).
- **Suggested Fix**: Move (or duplicate) the `_song_has_dpcm_events`-style
  check into `_build_song_bytecode`/`export_song_bank_bytecode` itself —
  raise `ValueError` for a non-empty, non-silent `dpcm` channel the same way
  the existing DPCM-note-range check already does, so the invariant holds
  for every caller, not just `main.py`.

### EXP-2026-08-07-3: `docs/AUDIO_BYTECODE_SPEC.md` doesn't document the jukebox `song_table` format
- **Severity**: LOW
- **Dimension**: 5 (Bytecode-Spec Conformance) / 6 (Macro Emission — data-structure documentation)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` (no `song_table`/`jukebox`/`song_count` mentions anywhere)
- **Location**: `exporter/exporter_ca65.py:1533-1670` (`export_song_bank_bytecode` — emits `song_table_ptr_lo/hi`, `song_table_bank`, `song_count`, `song_instrument_ptr_lo/hi` as new persistent on-disk data structures) vs. `docs/AUDIO_BYTECODE_SPEC.md` (unchanged by commit `c864426`)
- **Status**: NEW
- **Description**: The spec doc is called out by this audit's own protocol as
  "the authoritative reference the 6502 engine plays back", and Dimension 5/6
  explicitly ask to cross-check emitted bytes against it. The new jukebox
  data layout (three parallel byte arrays indexed `song_index*5 + channel`,
  plus the per-song instrument-pointer table) is entirely undocumented there
  — `docs/ROADMAP.md` describes the feature at a narrative level but not the
  byte layout, and `docs/MACRO_USAGE_GUIDE.md` is unchanged. The only
  authoritative description of the format today is the docstrings in
  `exporter_ca65.py` and the mirrored comments in `nes/audio_engine.asm`.
- **Impact**: Cosmetic/maintainability only — the format itself was verified
  consistent between exporter and engine (see the DPCM-adjacent check above
  and Dimension 1's analysis), so nothing plays wrong today. But the spec
  doc's authority is exactly what future audits and future engine changes
  are told to treat as ground truth; a silent gap here increases the risk
  that a future change to the song-table layout on one side (exporter or
  engine) goes unnoticed by the other, since there is no third, independent
  document to cross-check against — the same drift risk `docs/AUDIO_BYTECODE_SPEC.md`
  §3 already had to be reconciled for once before (#83/EXP-07).
- **Related**: #83/EXP-07 (same doc, different gap, closed).
- **Suggested Fix**: Add a `docs/AUDIO_BYTECODE_SPEC.md` section documenting
  `song_table_ptr_lo/hi`/`song_table_bank`/`song_count`/`song_instrument_ptr_lo/hi`
  (layout, indexing formula, channel order) alongside the existing §2 data
  structures.

### EXP-2026-08-07-4: Multi-song bank-overflow error loses which song failed
- **Severity**: LOW
- **Dimension**: 1 (CA65 Assembly Well-Formedness & Builder Compatibility)
- **Spec ref**: N/A (error-message quality, not emitted bytecode)
- **Location**: `exporter/exporter_ca65.py:1385-1395` (the `ValueError` raised inside `_build_song_bytecode` when a song's sequence bytecode overflows the shared 60-bank pool) called from `:1598-1599` inside `export_song_bank_bytecode`'s per-song loop
- **Status**: NEW
- **Description**: `_build_song_bytecode`'s overflow message
  (`"Sequence bytecode exceeds the MMC3 {N}-bank budget ...: channel '{channel}' needs bank {next_bank}, but the linker config defines only BANK_00..BANK_{NN}..."`)
  names the offending channel but not which song in the bank triggered it.
  `export_song_bank_bytecode`'s loop (`for prefix, song in zip(song_labels, songs): body_lines, ... = self._build_song_bytecode(song['frames'], label_prefix=prefix, ...)`)
  has the song index/label in scope at the call site but doesn't catch and
  re-raise with that context, and `main.py:927-1027`'s `run_song_build` only
  prints the caught `ValueError`'s message verbatim.
- **Impact**: Cosmetic/debuggability only — the build still fails loudly and
  correctly (no wrong ROM produced). But on a bank with several songs, a user
  hitting the shared 60-bank budget has to bisect the bank (remove songs one
  at a time) to find which song is oversized, since the exporter already
  knows (`prefix`/song index) and simply doesn't say.
- **Related**: None.
- **Suggested Fix**: In `export_song_bank_bytecode`'s per-song loop, catch
  `ValueError` from `_build_song_bytecode` and re-raise with the song's index
  (and name, if threaded through from `main.py`) prepended to the message.

## Verified fixes re-confirmed in place (unaffected by this commit)

The following prior-audit fixes were spot-checked against current code as
part of scoping this audit (none touched by `c864426`) and all still hold:
`export_direct_frames`/`export_tables_with_patterns` label/segment
well-formedness (D1), APU register serialization and the triangle-control
fix #364 (D2), the empty-`patterns` early return and unused-`references`
docstring (#4, D3), the instrument-count guard #80, macro-offset reservation
#77, note-range clamps #158/#298, and DPCM note-range guard #369 (D4 — the
DPCM guard's presence was directly re-verified as still firing inside
`_build_song_bytecode` per Finding EXP-2026-08-07-2 above, just scoped to
value range rather than channel presence), bytecode length/note encoding and
the `$FE`/`$83`/`$87` documentation state (D5), instrument-tuple ordering and
sustain-only macro compression (D6), NSF `NotImplementedError` and
FamiStudio's `.get()`-guarded reads (D7), and the `--format` CLI choices gate
(D8). No regression found in any of these.

## Deduped against open issues / prior audits (noted, not counted)
- #30/F-13 (song bank → ROM feature) is CLOSED — this audit's findings are
  against the shipped v1 implementation, not the (already-resolved) feature
  request itself.
- `AUDIT_NES_HARDWARE_2026-08-07.md` and `AUDIT_PIPELINE_2026-08-07.md` both
  independently found and reproduced EXP-2026-08-07-1 above the same day;
  see that finding's Dedup note.
- `gh issue list --repo matiaszanolli/midi2nes --state all --limit 300` was
  checked for `song`/`bank`/`jukebox`/`dpcm`/`bytecode spec` keyword overlap
  with each finding above; no open or closed issue matches any of
  EXP-2026-08-07-2 through -4.

Then suggest:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-08-07.md
```
