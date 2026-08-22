# MAP-2026-08-21-2: CC65Wrapper.assemble/link invoke bare ca65/ld65 instead of resolved paths, and omit FileNotFoundError

**Issue:** #454
**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-08-21.md

## Description
The #14 hardening's stated rationale — probe the exact binary `which()` found so the check and the use can't diverge — is undercut one call later: `assemble()` and `link()` re-resolve `"ca65"`/`"ld65"` through PATH at spawn time instead of using the stored `_ca65_path`/`_ld65_path`. A binary that vanishes or is PATH-shadowed between `check_toolchain()` and the real run raises a raw `FileNotFoundError` (their `except` clause covers only `TimeoutExpired`), which escapes as a generic `[ERROR] Compilation failed: [Errno 2] ...` via `compile_rom`'s broad `except Exception` rather than the typed `ToolchainError` every other missing-tool path produces.

## Location
- `compiler/cc65_wrapper.py:141` (`cmd = ["ca65", ...]`)
- `compiler/cc65_wrapper.py:199` (`cmd = ["ld65", ...]`)
- vs `compiler/cc65_wrapper.py:45-79` (`check_toolchain` resolves via `shutil.which()` and deliberately probes the **resolved** `self._ca65_path`/`self._ld65_path` "so we exercise the exact binary shutil.which found, avoiding a TOCTOU/PATH divergence (#14)")
- `compiler/cc65_wrapper.py:147-160`/`:210-223` (only `subprocess.TimeoutExpired` is caught around the real assemble/link runs — unlike the probes, which also catch `FileNotFoundError`)

## Evidence
`check_toolchain` stores `self._ca65_path = shutil.which("ca65")` (`:45`) and probes `[self._ca65_path, "--version"]` (`:59`) with `except (FileNotFoundError, subprocess.TimeoutExpired)` (`:66`); `assemble` then builds `cmd = ["ca65", str(source_file), ...]` (`:141`) and guards only `except subprocess.TimeoutExpired` (`:155`). Same asymmetry in `link`.

## Impact
Cosmetic/hardening only — the window is a race between two subprocess calls, and the failure still surfaces as a nonzero exit with a message (never a false "success"), so no severity floor applies. Consistency with the module's own #14 invariant is the point.

## Related
#14 (commit `48da1ea`).

## Suggested Fix
Use `self._ca65_path or "ca65"` / `self._ld65_path or "ld65"` in the `cmd` lists, and add `FileNotFoundError` to the two `except` clauses, mapping it to `ToolchainError`.

## Completeness Checks
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
