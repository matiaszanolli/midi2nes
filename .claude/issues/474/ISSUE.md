# 474: REG-35: No test exercises the split CLI prepare/compile route on a jukebox music.asm

URL: https://github.com/matiaszanolli/midi2nes/issues/474
Labels: bug, medium, regression

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-08-21.md

## Description
`run_song_build` works because it passes `song_count=len(songs)` in-process, but the documented step-by-step route (`main.py prepare` on a jukebox music.asm, then `main.py compile`) fails at ld65 with 8 unresolved externals — the same failure signature REG-27 had — because the CLI path has no way to learn the file is a jukebox export. No test exercises `prepare`/`compile` (the CLI subcommands or `prepare_project` without `song_count`) on `export_song_bank_bytecode` output, so the suite proves nothing about the split flow the jukebox docs/CLI still offer.

This is the third distinct jukebox linking/placement defect to ship in this feature; each lived in a path combination no test covered (1-song bank → REG-27; 2+-song segment placement → REG-28; split CLI flow → this).

## Evidence
- Underlying defect **MAP-2026-08-21-1** (#453, live ld65 repro in today's mappers audit): `nes/project_builder.py`'s `prepare_project` never reads the jukebox marker `export_song_bank_bytecode` embeds in music.asm; only the explicit `song_count=` parameter (which the CLI `prepare` subcommand never passes) triggers `JUKEBOX_BUILD`.
- Test inventory confirmed by direct read of `tests/test_main.py`: `TestJukeboxCompilationIntegration` (3 tests) always calls `prepare_project(..., song_count=N)` directly; `TestRunPrepare` (class at line 440) / `TestRunCompile` (class at line 785) never use jukebox asm — `grep -n "export_song_bank_bytecode"` in the file matches only inside `TestRunSongBuild` (line 1621-1623), not the prepare/compile classes.

## Impact
The split debugging flow — the one a user reaches for precisely when the one-shot build misbehaves — hard-fails on every jukebox project with a cryptic linker error, and any fix (marker-sniffing in `prepare_project`) will land untested unless this test exists first.

## Related
#453 (MAP-2026-08-21-1), REG-27/REG-28 (pattern: jukebox path-combination gaps, fixed by `8ea7ac3`), #362

## Suggested Fix
Add a `requires_cc65`-gated test: `export_song_bank_bytecode` a 2-song bank to music.asm, run `run_prepare` (or `prepare_project` with **no** `song_count`), then `compile_rom`, asserting link success — red until MAP-2026-08-21-1's marker-consumption fix lands. A cheaper non-CC65 companion: assert `prepare_project` on marker-bearing asm emits `JUKEBOX_BUILD = 1` in main.asm.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **TESTS**: A regression test pins this specific fix
