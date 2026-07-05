# F-10: export appends DPCM block in 'a' mode — re-running clobbers/doubles on a reused output

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/23
**Severity:** MEDIUM
**Domain:** pipeline
**Source:** AUDIT_PIPELINE_2026-06-28.md
**Labels:** medium, pipeline, bug

## Description
`run_export` writes the CA65 tables (overwrite via `export_tables_with_patterns`) then
**appends** the packed DPCM assembly with `open(args.output, 'a')` (`main.py:118-119`). The
default path appends to the fresh temp `music.asm` so it is safe (file new each run). In the
step-by-step path `args.output` is a user file: re-running `export` onto a path that already
contains a DPCM block from a prior tool step produces duplicate `dpcm_*` symbols → assembler
error.

## Location
`main.py:118-119` (`run_export`); default path `main.py:403`

## Impact
Step-by-step `export` re-runs onto a path that already contains a DPCM section yield
duplicate-symbol assembly failures. Recoverable (delete and re-run) → MEDIUM.

## Suggested Fix
Have `export_tables_with_patterns` include the DPCM block itself (single write), or guard the
append against an existing DPCM marker.

## Completeness Checks
- [ ] **CONTRACT**: music.asm has exactly one DPCM block regardless of re-runs
- [ ] **SIBLING**: Default-path append at `main.py:403` checked for the same hazard
- [ ] **TESTS**: A regression test pins re-run export → no duplicate symbols

---

# M-8: MIN_ROM_SIZE is a flat 32768 that can false-pass a truncated MMC3/MMC1 image far smaller than its declared PRG

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/28
**Severity:** MEDIUM
**Domain:** mappers
**Source:** AUDIT_MAPPERS_2026-06-28.md
**Labels:** medium, mappers, bug

## Description
`compile()` rejects a linked ROM `< 32768` bytes. NROM links to 32KB PRG + 16-byte header =
32784, so a valid NROM is `> 32768` (no false-positive). But MMC3 declares 512KB PRG and MMC1
128KB; the check would pass any image `>= 32768`, including a truncated MMC3 image that is a
fraction of its declared 512KB. The check should compare against
`self.mapper.prg_rom_size + 16`, not a flat constant. (In practice `ld65` with `fill = yes`
pads regions to full size, so a successful link produces the full declared size — making a
truncated-but-large image unlikely; hence MEDIUM, a defense gap.)

## Evidence
```
compiler.py:27   MIN_ROM_SIZE = 32768
compiler.py:134  if rom_size < self.MIN_ROM_SIZE: raise CompilationError(...)
```
`ROMCompiler` has no reference to the mapper, so it cannot compute the expected size today.

## Impact
A truncated/under-filled ROM ≥32KB passes validation. MEDIUM.

## Related
M-3.

## Suggested Fix
Plumb the mapper (or expected PRG size) into `ROMCompiler` and validate
`rom_size == mapper.prg_rom_size + 16` (or `>=`), not a flat 32768.

## Completeness Checks
- [ ] **CONTRACT**: ROMCompiler receives the mapper / expected PRG size
- [ ] **SIBLING**: Size check correct for NROM/MMC1/MMC3
- [ ] **TESTS**: A regression test feeds a truncated large-mapper ROM and expects rejection

---

# M-9: compile_rom broad except Exception prints then returns False — masks tracebacks without verbose

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/32
**Severity:** LOW
**Domain:** mappers
**Source:** AUDIT_MAPPERS_2026-06-28.md
**Labels:** low, mappers, enhancement

## Description
`compile_rom` wraps the whole compile in `try/except`, catching `CompilationError`,
`ValidationError`, and a catch-all `except Exception`, printing `[ERROR] …` and returning
`False`. This does surface the message (not a silent success), but the catch-all swallows the
stack trace with no `verbose`/`-v` traceback option at this layer (the pipeline's own `-v`
traceback is in `main.py`, not here). A genuinely unexpected exception loses its origin.

## Evidence
```
compiler.py:173-175  except Exception as e: print(f"[ERROR] Compilation failed: {e}"); return False
```

## Impact
Harder debugging of unexpected compiler failures; not a correctness bug.

## Related
M-4.

## Suggested Fix
In the catch-all, print `traceback.format_exc()` when `verbose`.

## Completeness Checks
- [ ] **CC65**: Error path still surfaces message; traceback shown under verbose
- [ ] **TESTS**: A regression test pins verbose traceback emission
