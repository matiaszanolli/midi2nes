# REG-24: nes/debug_overlay.py has no dedicated test module; create_debug_rom_variant + CLI entry unexercised

**Issue:** #358
**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-07-19.md
**Labels:** low, regression, enhancement

## Description
`nes/debug_overlay.py` sits at 52% coverage with no dedicated `test_*.py`. The actually-used `--debug` path (`generate_full_debug_system`, injected via `NESProjectBuilder`) IS smoke-tested for compile by `tests/test_rom_validation_integration.py::TestDebugModeROMGeneration::test_debug_mode_rom_generation`. The uncovered block is the **standalone** `create_debug_rom_variant(music_asm_path, output_path)` helper (`nes/debug_overlay.py:627`) — it reads a `music.asm`, appends the debug system under a `DEBUG OVERLAY INJECTED BELOW` marker, and writes a combined `.asm` — plus the `if __name__ == "__main__"` CLI entry. Nothing exercises it, so a regression in its file-combination logic is silent.

## Evidence
`grep -rl create_debug_rom_variant tests/` → no match. `create_debug_rom_variant` defined at `nes/debug_overlay.py:627`, invoked by `__main__` at line 672; no `tests/test_debug_overlay.py` exists.

## Impact
LOW — dev-only overlay helper off the main `--debug` pipeline; a break here does not affect a normally-generated ROM.

## Related
`nes/project_builder.py` (the live `--debug` path).

## Suggested Fix
Add `tests/test_debug_overlay.py` feeding a small `minimal_music_asm` fixture through `create_debug_rom_variant`, asserting (a) original music body verbatim, (b) `DEBUG OVERLAY INJECTED BELOW` marker + `generate_full_debug_system()` output, (c) assembles under `ca65` (gate `@pytest.mark.requires_cc65`).

## Provenance
Filed NEW, CONFIRMED against code. Dedup: no matching open issue.
