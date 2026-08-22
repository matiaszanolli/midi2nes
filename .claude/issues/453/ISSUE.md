# MAP-2026-08-21-1: Split prepare/compile on a jukebox music.asm always fails at ld65 with 8 unresolved externals

**Issue:** #453
**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-08-21.md

## Description
The repo's established pattern for the split `prepare`/`compile` flow is that everything needed to build correctly is recoverable from the artifacts themselves: the bytecode-engine marker forces MMC3 (`_requires_mmc3_bytecode_engine`), the bank-pack and DPCM markers force/reject mappers (#283, #362), and the nes.cfg mapper stamp makes `compile` self-sufficient (#297, #269). The jukebox attribute breaks this pattern: `export_song_bank_bytecode` stamps its own distinguishing marker into music.asm line 1 (`-- multi-song jukebox build`), but `prepare_project` decides `JUKEBOX_BUILD` purely from the `song_count` parameter, which only `run_song_build` passes.

Running the documented `python main.py prepare <music.asm> <dir>` on a jukebox music.asm (or calling `prepare_project` as a library without `song_count`) therefore succeeds — capacity pre-flight passes, all files written, "Ready for CC65 compilation!" — and the resulting project can never link: the engine's single-song branch references `pulse1_sequence`/`channel_start_banks`/`instrument_table`/`audio_init`-side labels the jukebox music.asm doesn't define.

## Location
- `nes/project_builder.py:83-98` (`prepare_project` — jukebox mode decided solely by the caller-supplied `song_count` parameter)
- `nes/project_builder.py:107,122` (music.asm content is read and scanned for the `"MMC3 Macro Bytecode"` engine marker, but the jukebox variant of that same first line — `"MMC3 Macro Bytecode -- multi-song jukebox build"`, `exporter/exporter_ca65.py:1577` — is never distinguished)
- `main.py:608-640` (`run_prepare` calls `builder.prepare_project(args.input)` with no `song_count`)

## Evidence
Live reproduction at HEAD:
```
$ python3 main.py prepare /tmp/audit/.../jb1/music.asm jb1_prep
  ✓ Music data 2,993 bytes fits the MMC3 PRG regions
 Prepared NES project -> jb1_prep      ← succeeds
$ python3 main.py compile jb1_prep jb1_prep.nes
Unresolved external 'pulse1_sequence' referenced in: ...audio_engine.asm(151,153)
Unresolved external 'pulse2_sequence' ... 'triangle_sequence' ...
ld65: Error: 8 unresolved external(s) found - cannot create output file
[ERROR] ROM compilation failed
```
(jb1/music.asm produced by `export_song_bank_bytecode` — first line: `; CA65 Assembly Export (MMC3 Macro Bytecode -- multi-song jukebox build)`.)

## Impact
No corrupt ROM is ever produced (ld65 fails hard), so this is a UX/defense-in-depth gap, not a correctness break — but the failure arrives two steps late, as a cryptic linker dump instead of a clean message, from a `prepare` step that explicitly reported success. Blast radius: the split prepare/compile debugging flow and any library consumer of `NESProjectBuilder` handed a jukebox music.asm; the normal `song build` route is unaffected.

## Related
Same "split flow loses build metadata → raw ld65 error" class as #297/MAP-2026-07-06-1, #362/MAP-2026-07-19-2, #283/MAP-2026-07-05B-3 (all fixed via markers). Complements the fixed MAP-2026-08-07-2.

## Suggested Fix
In `prepare_project`, detect the jukebox variant from `music_content` (e.g. `"multi-song jukebox build" in music_content`) and either (a) treat it as jukebox mode when `song_count` is None — the Start-skip code and `JUKEBOX_BUILD` don't need the exact count, only `audio_advance_song`'s runtime `song_count` byte does, which music.asm itself exports — or (b) at minimum raise a clean `ExportError` telling the caller to pass `song_count`/use `song build`. Add a regression test running `run_prepare`-style `prepare_project(jukebox_music_asm)` with no `song_count`.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
