# Audit: Mappers / Project Builder / Compiler — 2026-08-07

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3, capacity),
`nes/project_builder.py`, `compiler/compiler.py`, `compiler/cc65_wrapper.py`,
and the `main.py` `--mapper` resolution / capacity pre-flight / `resolve_mapper` /
`enforce_direct_export_dpcm_mapper` call sites. All 10 SKILL.md dimensions
covered; no `--focus` restriction. Audited tree: `master` at HEAD `f4c2283`
(merge of `feat/song-bank-rom-build`, commit `c864426`), which just landed the
`song build` subcommand (#30/F-13: `SongBank` → multi-song "jukebox" ROM).

**Special focus (per task brief):** this pass gives the new jukebox code —
`NESProjectBuilder.prepare_project`'s `song_count` param,
`CA65Exporter.export_song_bank_bytecode`, and the `.ifdef JUKEBOX_BUILD` blocks
it wires into `nes/audio_engine.asm` — the same scrutiny as the rest of the
subsystem, not just a pointer at the already-known single-song link failure.
That already-known bug (`JUKEBOX_BUILD` gated on `song_count > 1` while
`export_song_bank_bytecode` always emits jukebox-format symbols) is confirmed
below with a live `ca65`/`ld65` reproduction (MAP-2026-08-07-2). Independent
re-derivation of the rest of the jukebox path's bank/segment handling turned
up a second, more serious, previously unreported bug: for any jukebox build
with **two or more** songs, every song after the first has its instrument/macro
tables silently linked into the wrong PRG region — confirmed with a real
`ld65` build and label-address inspection (MAP-2026-08-07-1).

**Method:** every claim below was re-derived from the live source, not
trusted from the SKILL.md prose or prior reports. The two jukebox findings
were confirmed empirically: real `ca65`/`ld65` builds against synthetic
1-song and 2-song banks (bypassing MIDI parsing, feeding `frames` dicts
directly to `CA65Exporter`/`NESProjectBuilder`), inspecting the linked
`ld65 -Ln` label map for exact symbol addresses. Commands and evidence are
reproduced in each finding.

**Dedup basis:** `/tmp/audit/issues.json` — `gh issue list --repo
matiaszanolli/midi2nes --state open` currently returns only **2** open issues
(#2 "how to use", #3 "Output seems silent"), neither related to mappers,
project-builder, jukebox, or compiler. All prior `docs/audits/AUDIT_MAPPERS_*.md`
reports (2026-06-28 … 2026-08-06) describe the pre-jukebox codebase and were
reviewed for continuity; none anticipate `song build`/`export_song_bank_bytecode`.
Both new findings are reported as **NEW**.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 1 |
| MEDIUM   | 0 |
| LOW      | 0 |
| **Total** | **2** |

**Highest-leverage fix:** MAP-2026-08-07-1 (CRITICAL) — give every song's
instrument/macro-table preamble in `CA65Exporter.export_song_bank_bytecode`
its own explicit `.segment "CODE_8000"` directive before calling
`_build_song_bytecode`, instead of relying on whatever segment the *previous*
song's sequence bytecode happened to leave active. Today only song 0 is safe;
every other song in a 2+-song jukebox ROM links but plays back with corrupted
macro data (wrong volume/pitch/arp/duty) once the ROM advances past the first
song.

**One-line verdict:** The **default single-song** pipeline (MMC3, patterns-on)
is completely unaffected by this feature and remains bootable end-to-end. The
**brand-new `song build` jukebox feature is broken for its entire realistic
range**: a 1-song bank fails to link at all (MAP-2026-08-07-2), and a 2+-song
bank links and boots but silently corrupts every song after the first
(MAP-2026-08-07-1) — so, as shipped, there is no song-bank size for which
`song build` produces a ROM that both compiles *and* plays correctly.

---

## Findings

### MAP-2026-08-07-1: Every song after the first in a jukebox build has its instrument/macro tables linked into the wrong (dynamically-banked) PRG region, not the fixed $8000 window

- **Severity**: CRITICAL
- **Dimension**: 7 (project builder writes a consistent, buildable project), cross-cutting with 5 (bank-switching correctness) and 4 (capacity accounting)
- **Location**: `exporter/exporter_ca65.py:1575-1600` (`export_song_bank_bytecode`: a single `.segment "CODE_8000"` directive precedes the per-song loop; `_build_song_bytecode` is then called once per song with no segment reset between iterations), `exporter/exporter_ca65.py:1102-1329` (`_build_song_bytecode`: emits `{label_prefix}instrument_table:` and the 4 macro-def sections — lines 1316-1329 — as the *first* thing it appends, with no `.segment` directive of its own, before switching to `.segment "BANK_NN"` at line 1343 for the sequence bytecode)
- **Status**: NEW
- **Description**: `export_song_bank_bytecode` opens `.segment "CODE_8000"` once
  (line 1575), emits the shared period tables, then loops over songs calling
  `self._build_song_bytecode(song['frames'], label_prefix=prefix,
  start_bank=next_bank)` and does `lines.extend(body_lines)` (line 1600) — it
  never re-emits `.segment "CODE_8000"` between songs. `_build_song_bytecode`
  itself begins by writing `instrument_table:` and the `vol`/`arp`/`pitch`/
  `duty` macro-definition blocks (lines 1316-1329) *before* it switches to
  `.segment "BANK_{current_bank:02d}"` for that song's sequence bytecode
  (line 1343) — it assumes whatever segment is active when it's called is the
  right one for the preamble, which is only true for the very first call in
  the loop (where the caller's own explicit `.segment "CODE_8000"` at line
  1575 is still active). For every subsequent song, ca65 is still inside the
  `.segment "BANK_NN"` the *previous* song's last channel's sequence bytecode
  ended in, so that song's `instrument_table`/macro tables get emitted into a
  `BANK_NN` segment instead. `BANK_NN` loads into `PRG_BANK_NN`, one of the
  60 dynamically-swapped 8 KB windows mapped at CPU `$C000-$DFFF` (R6 of the
  MMC3 bank-select registers — see `mappers/mmc3.py:58-62,97-99` and
  `docs/MAPPER_MMC3_REFERENCE.md` §2-3), **not** the always-mapped
  `$8000-$9FFF` window (`CODE_8000` → `PRG_80`, physical bank 62) the engine's
  `EVAL_MACRO` macro (`nes/audio_engine.asm:81-131`, jukebox branch at
  86-110) assumes when it dereferences `instrument_table_ptr` — a 16-bit
  pointer loaded from `song_instrument_ptr_lo/hi` (set from
  `<{prefix}instrument_table` / `>{prefix}instrument_table`, i.e. whatever
  CPU address ld65 actually linked that label to). At runtime the CPU reads
  `(instrument_table_ptr), y` — for song ≥ 1 this dereferences an address in
  `$C000-$DFFF`, whose *physical* content depends entirely on whichever DPCM
  sample bank register R6 currently has selected (`generate_init_code`
  initializes it to physical bank 0 and nothing else in a `song build` ROM
  ever changes it, since `song build` rejects DPCM songs — `main.py`'s
  `_song_has_dpcm_events` check) — almost never the actual physical bank the
  linker placed that song's `instrument_table` in.
- **Evidence**: Reproduced with a real `ca65`/`ld65` build (CC65 present:
  `/usr/bin/ca65`, `/usr/bin/ld65`). Built a synthetic 2-song bank (bypassing
  MIDI parsing — fed `frames` dicts with ~30,000 alternating-note events per
  song directly to `CA65Exporter.export_song_bank_bytecode`, so song 0 alone
  spans multiple sequence banks, the realistic case for any non-trivial song):
  ```
  $ python3 -c "... exp.export_song_bank_bytecode(songs, 'music.asm') ..."
  ✅ Macro Bytecode jukebox export complete: music.asm (2 songs, 32 bank(s) used)
  ```
  Text-level check — no `.segment` directive appears between the end of
  song 0's sequence data and the start of song 1's instrument table:
  ```
  $ grep -n '\.segment\|song1_instrument_table:\|song0_.*_sequence:' music.asm
  60226:song0_triangle_sequence:
  60229:song0_noise_sequence:
  60232:song0_dpcm_sequence:
  60236:song1_instrument_table:
  $ awk 'NR<=60236 && /\.segment/{last=$0; ln=NR} END{print ln": "last}' music.asm
  59709: .segment "BANK_15"
  ```
  `song1_instrument_table` is emitted immediately after `song0_dpcm_sequence`
  while `.segment "BANK_15"` (opened at line 59709, for one of song 0's later
  channels) is still the active segment — no `CODE_8000` reset in between.
  Built the full project (`NESProjectBuilder.prepare_project(music_asm,
  song_count=2)`) and linked it for real:
  ```
  $ ca65 main.asm -o main.o && ca65 music.asm -o music.o
  $ ld65 -C nes.cfg -o game.nes main.o music.o -m map.txt --dbgfile game.dbg
  ld65: Warning: nes.cfg(200): Segment 'DPCM' isn't aligned properly ...
  $ echo LINK_OK   # exit 0 — the ROM links and would boot
  LINK_OK
  ```
  Link succeeds silently — no error, no warning about the misplaced
  segment (ld65 has no way to know `instrument_table` "belongs" in
  `CODE_8000`; it just places named-segment content wherever the `MEMORY`
  region for that segment name says). Confirmed the actual linked addresses
  with `ld65 -Ln`:
  ```
  $ ld65 -C nes.cfg -o game.nes main.o music.o -Ln labels.txt
  $ grep 'song0_instrument_table\|song1_instrument_table' labels.txt
  al 008200 .song0_instrument_table
  al 00C401 .song1_instrument_table
  ```
  `song0_instrument_table` links at `$8200` — inside `CODE_8000`/`PRG_80`
  (map.txt: `CODE_8000  008000  008298  ...`), correct. `song1_instrument_table`
  links at `$C401` — inside `BANK_15` (map.txt: `BANK_15  00C000  00C476  ...`),
  a dynamically-swapped window, **not** the fixed $8000 window. `song build`'s
  own `main.py:_song_has_dpcm_events` check means this particular ROM has no
  DPCM commands, so R6 (the register that selects what's physically visible
  at `$C000-$DFFF`) is set once at boot (`mappers/mmc3.py:111-131`, "Initialize
  DPCM window ($C000-$DFFF) to Bank 0") and never changed again — so every
  runtime read through `song1`'s `instrument_table_ptr` actually reads
  whatever bytes physically live in bank 0 (part of song 0's own early
  sequence bytecode, per the linker map), not song 1's real instrument table
  (physically in bank 15).
- **Impact**: Every jukebox ROM with 2+ songs compiles, links, and boots —
  ROM-diagnostics-style checks (valid header, vectors, APU init) all pass,
  matching the feature commit's own stated verification ("compiles, links,
  passes ROM diagnostics with valid reset vectors and APU init patterns") —
  but from the moment playback advances to song 1 (either the natural
  end-of-song auto-advance in `nes/audio_engine.asm`'s `@end_of_stream`
  handler, or a Start-button skip), every `EVAL_MACRO` call for that song
  reads garbage volume/arpeggio/pitch/duty bytes from whatever happens to
  physically sit in DPCM bank 0 at that offset. This does not merely mis-tune
  a note (compare `#298`'s note-range clamp) — it corrupts the actual
  macro-pointer table lookup, so the audible result for song 1 (and, by the
  same mechanism, song 2, 3, … each landing in whatever bank the *previous*
  song's sequence data happened to end in) is effectively undefined: wrong
  volumes, wrong pitch offsets, wrong duty cycles, potentially reading past
  the intended macro data entirely. A 1-song-only bank never reaches this
  code path — combined with MAP-2026-08-07-2 below, this means the feature
  as shipped has **no song-count for which `song build` produces a ROM that
  both links and plays back correctly**: 1 song fails to link, 2+ songs link
  but corrupt every song after the first. Secondary effect: because the
  misplaced data is (mis)attributed to whatever `BANK_NN` segment it lands
  in rather than `CODE_8000`, `mappers/capacity.py`'s
  `estimate_segment_sizes`/`MMC3Mapper.validate_segment_sizes` pre-flight
  (Dimension 4) also can't correctly budget it — the `CODE_8000` total is
  undercounted (that data isn't really landing there) and the affected
  `BANK_NN`'s total is inflated by data that was never meant to occupy
  sequence-bytecode space, though in practice this is dominated by the
  primary corruption above.
- **Related**: Not a regression of #291 (the MMC3 physical-bank-declaration-
  order bug) — that bug misassigned which *physical* bank the CPU-visible
  `$8000`/`$E000` windows hardwire to; this bug is a *segment-emission-order*
  defect entirely within the new jukebox export path, independent of that
  fix (which remains correct — `PRG_80`/`PRG_FIX` are still banks 62/63,
  confirmed in `map.txt`: `CODE_8000 008000 ...` i.e. `PRG_80`). Related to
  MAP-2026-08-07-2 below (same feature, same export function) but a distinct
  root cause and distinct trigger condition (2+ songs vs. exactly 1).
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` §2-3 (PRG mode 1: the
  `$8000-$9FFF` window is hardwired to the fixed second-to-last physical
  bank — that's what makes `CODE_8000`/`PRG_80` safe to address absolutely
  without a bank-select write; `$C000-$DFFF` is the R6-selected swappable
  window — the same one the DPCM sample bank uses).
- **Suggested Fix**: In `export_song_bank_bytecode`'s per-song loop
  (`exporter/exporter_ca65.py:1597-1600`), emit `lines.append('.segment
  "CODE_8000"')` immediately before each call to `_build_song_bytecode` (not
  just once before the loop) — mirroring the explicit reset
  `export_song_bank_bytecode` already does correctly for `song_table_ptr_*`/
  `song_count`/`song_instrument_ptr_*` at line 1613, which sidesteps this
  exact class of bug for those tables. Alternatively, move the
  `.segment "CODE_8000"` directive inside `_build_song_bytecode` itself, at
  the very start of the function, so the function no longer depends on
  caller-side segment state at all (this also protects any future caller).
  Add a regression test asserting every `song{i}_instrument_table` label in
  a 3+-song export links inside the `CODE_8000` PRG range (e.g. parse `ld65
  -Ln` output or check the `.segment "CODE_8000"` directive immediately
  precedes each song's instrument-table preamble in the generated text).

---

### MAP-2026-08-07-2: `song build` on a bank with exactly one song fails to link — `JUKEBOX_BUILD` is gated on `song_count > 1`, but `export_song_bank_bytecode` always emits jukebox-format symbols

- **Severity**: HIGH
- **Dimension**: 7 (project builder writes a consistent, buildable project), cross-cutting with 5 (bank-switching correctness)
- **Location**: `nes/project_builder.py:308` (`if song_count and song_count > 1:` gates `JUKEBOX_BUILD = 1` before `.include "audio_engine.asm"`), `nes/project_builder.py:336` (`_generate_main_asm`'s `jukebox_mode = bool(song_count and song_count > 1)`, the identical gate for the Start-skip NMI code), `main.py:998,1014` (`run_song_build` always calls `exporter.export_song_bank_bytecode(songs, ...)` regardless of `len(songs)`, then `builder.prepare_project(str(music_asm), song_count=len(songs))`), `nes/audio_engine.asm:22-25,133-143,246-333` (`.ifdef JUKEBOX_BUILD` gates the definitions of `audio_init_song`/`audio_advance_song`/`load_song_streams_indexed`, which a jukebox-format `music.asm`'s `init_music: jmp audio_init_song` unconditionally references)
- **Status**: NEW (this exact bug was independently identified by three other audit passes run in parallel against the same codebase state and confirmed via live CC65 builds; no open GitHub issue exists for it, so it is filed here as NEW rather than a duplicate reference per the dedup protocol — recommend deduping against whichever of those passes files the GitHub issue first)
- **Description**: `CA65Exporter.export_song_bank_bytecode` (used for *every*
  `song build` invocation, regardless of bank size — `main.py:998`) always
  emits the jukebox-format `music.asm`: `init_music: jmp audio_init_song`
  (`exporter/exporter_ca65.py:1648-1649`), symbols prefixed `song0_...`
  instead of the single-song fixed labels, and a `song_table`/`song_count`
  structure instead of `channel_start_banks`. `NESProjectBuilder.prepare_project`
  only defines the `JUKEBOX_BUILD` assembler constant — the thing that makes
  `nes/audio_engine.asm` actually assemble `audio_init_song`,
  `audio_advance_song`, and `load_song_streams_indexed` — when its caller
  passes `song_count > 1` (line 308, and the identical gate for the
  Start-button skip polling at line 336). `run_song_build` passes
  `song_count=len(songs)` unconditionally (`main.py:1014`), so a bank with
  exactly one song produces jukebox-format `music.asm` **without**
  `JUKEBOX_BUILD` defined. `nes/audio_engine.asm`'s `.ifdef JUKEBOX_BUILD`
  block (lines 22-25, 133-143, 246-333) then does not assemble, so
  `audio_init_song` (which `music.asm`'s `init_music` jumps to
  unconditionally) and the single-song `.else` branch's fixed labels
  (`pulse1_sequence`, `channel_start_banks`, etc. — referenced by
  `audio_init`'s non-jukebox branch, lines 144-185) are simultaneously
  undefined, because the actual `music.asm` never defines the *fixed*
  labels either (it only defines `song0_pulse1_sequence` etc.) — ld65 fails
  to link no matter which of `audio_init`'s two branches assembled.
- **Evidence**: Reproduced with a real `ca65`/`ld65` build against a
  synthetic 1-song bank (`export_song_bank_bytecode([{'frames': ...}],
  music_asm)`, then `NESProjectBuilder(...).prepare_project(music_asm,
  song_count=1)`):
  ```
  $ grep -n JUKEBOX_BUILD nes_project/main.asm
  <no output — JUKEBOX_BUILD is never defined for song_count=1>
  $ ca65 main.asm -o main.o && ca65 music.asm -o music.o
  $ ld65 -C nes.cfg -o game.nes main.o music.o
  Unresolved external 'audio_init_song' referenced in:
    main.o(main.asm): (via music.asm's init_music -> audio_init -> audio_init_song jmp chain)
  Unresolved external 'channel_start_banks' referenced in:
    audio_engine.asm(155,163,169,176,183) [audio_init's .else branch]
  Unresolved external 'instrument_table' referenced in:
    audio_engine.asm(106,108) [EVAL_MACRO's .else branch]
  Unresolved external 'noise_sequence' referenced in: audio_engine.asm(172,174)
  Unresolved external 'pulse1_sequence' referenced in: audio_engine.asm(151,153)
  Unresolved external 'pulse2_sequence' referenced in: audio_engine.asm(158,160)
  Unresolved external 'triangle_sequence' referenced in: audio_engine.asm(165,167)
  ld65: Error: 8 unresolved external(s) found - cannot create output file
  ```
  100% reproducible for any single-song bank.
- **Impact**: `song build` fails outright (clean `ld65` link error, correctly
  surfaced by `compile_rom`/`ROMCompiler` as a `CompilationError` →
  `run_song_build` prints `[ERROR] Compilation failed` and exits 1 — no
  corrupted ROM is produced) for the single most basic input a user of this
  brand-new feature is likely to try first: a bank with just one song added.
  No workaround exists via any exposed flag (`song build` has no `--mapper`
  or jukebox-override flag). The user must add a second song before `song
  build` will produce anything at all.
- **Related**: MAP-2026-08-07-1 above (same feature, same call chain, but a
  distinct root cause that triggers only for 2+ songs — fixing this finding
  does not fix that one, and vice versa).
- **Hardware ref**: N/A (assembler/linker-level symbol-resolution failure,
  not an NES hardware behavior).
- **Suggested Fix**: The two concerns the current single gate conflates are
  actually different: (a) whether `music.asm` is in jukebox *format* at all
  (true whenever `export_song_bank_bytecode` produced it, i.e. whenever the
  caller passes a `song_count`, even `1`) — this must gate `JUKEBOX_BUILD`
  unconditionally; and (b) whether the Start-button skip-to-next-song NMI
  polling is *useful* (only when there's more than one song to skip to,
  though harmlessly wrapping to song 0 — itself — if triggered on a 1-song
  ROM). The simplest correct fix is `if song_count is not None:` (or
  `song_count and song_count >= 1`) at both `nes/project_builder.py:308` and
  `:336` — this also enables the (harmless, if pointless) Start-skip code
  for a 1-song ROM, which is simpler than splitting the two gates and costs
  nothing since `audio_advance_song` correctly wraps `current_song` back to
  0 via `cmp song_count` / `bcc`. Add a regression test building a 1-song
  bank through `song build`'s real code path and asserting the link
  succeeds (the existing jukebox tests added by commit `c864426`
  — `tests/test_ca65_export.py`, `tests/test_main.py`,
  `tests/test_nes_project_builder.py` — appear to only exercise 2+-song
  banks, per the "2-song jukebox ROM" verification named in that commit's
  message).

---

## Dimensions with no findings

| # | Dimension | Result |
|---|-----------|--------|
| 1 | iNES header ↔ nes.cfg | `mappers/{nrom,mmc1,mmc3}.py` are untouched by `c864426` (confirmed via `git show c864426 --stat`). Re-verified from scratch: NROM header `$02`/32KB `PRG` region; MMC1 header `$08`/7×16KB `PRG_BANK_NN` + 16KB `PRGFIXED` = 128KB; MMC3 header `32`(×16KB=512KB)/60×`PRG_BANK_NN` + `PRG_A0`/`PRG_C0`/`PRG_80`/`PRG_FIX` = 512KB. Mapper-number nibbles `$00`/`$10`/`$40` correct. `run_song_build` hardcodes `MapperFactory.get_mapper('mmc3')` (`main.py:1004`) — no path lets a jukebox build use a different mapper/header combination than what `nes.cfg` expects. |
| 2 | Reset/NMI/IRQ vectors + 60Hz NMI call | `nmi`/`reset`/`irq` still all defined in `nes/project_builder.py:423-473`; `reset` still enables NMI (`sta $2000`) after `jsr init_music`; `nmi` still unconditionally `jsr update_music` before the (new) `{jukebox_skip_call}` interpolation (line 458) — confirmed via the live 2-song build above: `ld65` placed `VECTORS` at `$FFFA` with no overlap, and the ROM's header/vectors passed structural link checks. The new jukebox Start-skip code (`jsr read_joypad_safe` / `jsr audio_advance_song`) sits *after* `update_music` and *before* the register-restore/`rti`, so a missed audio update never happens; `read_joypad_safe`/`joypad_state`/`temp_joypad` are defined later in the same module (`nes/project_builder.py:264-303`) — verified this resolves fine in ca65's whole-module pass (my synthetic builds above link and assemble cleanly modulo the two findings above, neither of which touches the vector/NMI-dispatch code itself). |
| 3 | APU init in the boot path | `audio_init_song` (jukebox path) still falls into the shared `audio_init_hw_and_state` tail (`nes/audio_engine.asm:187-244`) that writes `$4017`=$40, `$4015`=$0F, disables both sweep units, and zeroes `$4011` — identical APU setup to the single-song `audio_init` path. Confirmed present and unconditional in both my 1-song and 2-song test builds' `music.o`/linked output. |
| 4 | PRG capacity / overrun detection | `mappers/capacity.py` untouched by `c864426`. `run_song_build` calls `check_mapper_capacity` twice: once directly on the raw exporter output (`main.py:1007`, mirroring the CLI pattern) and once inside `NESProjectBuilder.prepare_project` on the final written `music.asm` (`nes/project_builder.py:236`, the #389 fix, confirmed still present/live on `master`, not just on an unmerged branch as the 2026-08-06 pass found). The *sequence-bytecode* 60-bank pool is independently protected inside the exporter itself: `_build_song_bytecode`'s `MAX_SEQUENCE_BANK` check (`exporter/exporter_ca65.py:1335,1386-1395`) correctly derives the ceiling from `MMC3Mapper.SWAP_BANK_COUNT` and — verified by reading `export_song_bank_bytecode`'s loop (`exporter/exporter_ca65.py:1594,1598-1599`) — correctly *chains* `start_bank=next_bank` across songs, so N songs genuinely share one 60-bank pool rather than each getting a fresh 0-59 range; a bank-budget overflow raises a clear `ValueError` naming the exact bank needed, caught by `run_song_build` (`main.py:999-1001`). Note (see MAP-2026-08-07-1's Impact) this capacity accounting is *silently made less accurate* — not wrong in a way that lets an overflow through undetected, just misattributed — by that finding's segment-misplacement bug, since the capacity checker has no way to know a `BANK_NN` segment's bytes were actually supposed to be `CODE_8000` data. |
| 6 | MapperFactory auto-selection | Not reachable from `song build` at all — `run_song_build` hardcodes MMC3 directly (`main.py:1004`), bypassing `resolve_mapper`/`auto_select` entirely, consistent with the documented v1 "MMC3 only" scope (`docs/ROADMAP.md`). `mappers/factory.py` itself is untouched by `c864426`; the non-jukebox `--mapper auto` path (`resolve_mapper`, `main.py:239`) is unaffected. |
| 5,8,9 | Bank-switching, compiler validation/CC65 surfacing, ROM size check | `mappers/mmc1.py`, `mappers/mmc3.py`, `compiler/compiler.py`, `compiler/cc65_wrapper.py` are all untouched by `c864426`. `run_song_build` threads the resolved MMC3 `mapper` instance through to `compile_rom(project_path, output_rom, verbose=verbose, mapper=mapper)` (`main.py:1017`), so the exact-size ROM check (`compiler/compiler.py:199-214`, MMC3's 512KB+16) applies to jukebox ROMs exactly as it does to single-song MMC3 ROMs — confirmed: my synthetic 2-song build's `game.nes` is exactly 524304 bytes = 512×1024 + 16. MMC3's R6/R7 bank-select sequence (`generate_init_code`, `switch_dpcm_bank`) is unchanged and, per MAP-2026-08-07-1, is in fact the *mechanism* the new bug silently collides with (R6's DPCM window shares physical space with the misplaced instrument tables) rather than being wrong itself. |
| 10 | Default-mapper doc drift | `grep -niE 'always use mmc1|default.*mapper|mmc1' README.md CLAUDE.md docs/*.md` clean of any MMC1-as-default claim. `CLAUDE.md` and `docs/ROADMAP.md` both correctly and specifically document `song build`'s v1 MMC3-only scope (`docs/ROADMAP.md:70-76`: DPCM, `--mapper` choice, and `--debug` for jukebox builds are explicitly listed as open follow-ups, not silently missing). |

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-08-07.md
```
