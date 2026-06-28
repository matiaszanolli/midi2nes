# M-8: MIN_ROM_SIZE is a flat 32768 that can false-pass a truncated MMC3/MMC1 image far smaller than its declared PRG

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
`compile()` rejects a linked ROM `< 32768` bytes. Valid NROM is 32784 (>32768, no false-positive). But MMC3 declares 512KB and MMC1 128KB; the check passes any image ≥32768, including a truncated MMC3 fraction. Should compare against `self.mapper.prg_rom_size + 16`. In practice `ld65` fill pads to full size, so MEDIUM defense gap.

## Evidence
```
compiler.py:27   MIN_ROM_SIZE = 32768
compiler.py:134  if rom_size < self.MIN_ROM_SIZE: raise CompilationError(...)
```
`ROMCompiler` has no mapper reference, so cannot compute expected size today.

## Impact
A truncated/under-filled ROM ≥32KB passes validation. MEDIUM.

## Related
M-3.

## Suggested Fix
Plumb the mapper (or expected PRG size) into `ROMCompiler` and validate `rom_size == mapper.prg_rom_size + 16`.
