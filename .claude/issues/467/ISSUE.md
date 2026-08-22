# TD-32: run_song_build re-implements the capacity→prepare→compile→validate sequence instead of reusing build_and_validate_rom

- **Issue**: #467

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** Carried from 2026-08-07 (TD-32) — unfixed, never filed as a GitHub issue — filing now.

## Description
The #406 extraction gave `run_full_pipeline` a tested, raise-based `build_and_validate_rom` helper covering exactly the steps `run_song_build` inlines with its own `sys.exit`-per-step copies (`check_mapper_capacity` → `NESProjectBuilder` → `compile_rom` → `validate_rom`). Verified still duplicated this cycle (the jukebox path was untouched by any commit since the prior report except `8ea7ac3`'s `song_count` gate, which widened the drift surface).

## Evidence
`main.py:1003-1025` (`run_song_build`) inlines the capacity/prepare/compile/validate sequence with per-step `sys.exit(1)` calls, vs `main.py:1261-1293` (`build_and_validate_rom`) which does the same sequence raising `ValueError`/`RuntimeError` for the caller to handle. `run_song_build` also inline-imports `MapperFactory` at `:1003` instead of using the module-level import path.

## Impact
Fixes to the build sequence (capacity messaging, validation policy) land in one path only. This duplication is also *why* the jukebox path lacks the single-recovery-point error contract — the HIGH-severity consequence is PIPE-2026-08-21-4's finding; this entry tracks the duplication root cause.

## Suggested Fix
Parameterize `build_and_validate_rom` (it already takes mapper, music_asm, project path, output, flags; add `song_count`/`debug_mode` pass-through) and call it from `run_song_build` inside a try/except that owns error reporting.

## Related
PIPE-2026-08-21-4 (HIGH, error-contract angle of the same code, if/when filed); #406.

## Completeness Checks
- [ ] **CONTRACT**: `run_song_build`'s error reporting (currently per-step `sys.exit`) is preserved or intentionally upgraded when it switches to the raise-based helper
- [ ] **TESTS**: A regression test covers `run_song_build` going through the shared helper (capacity failure, prepare failure, compile failure, validate failure)
