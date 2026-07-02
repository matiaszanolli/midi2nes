# PL-04: `validate_rom` silently passes when the diagnostics engine itself fails — and says nothing without `--verbose`

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
The post-build gate wraps `from debug.rom_diagnostics import ROMDiagnostics` +
`diagnose_rom(...)` in `except Exception:` and returns True (ROM accepted), printing a
warning only if verbose. `diagnose_rom` handles unreadable ROMs internally
(`_create_error_result` -> "ERROR" -> fatal), so this outer except fires on genuine
infrastructure failures (import error in the `debug` package, an unexpected bug in
diagnostics) — exactly the cases where the boot-fatal vector/APU gate (#6) silently stops
existing. In a default (non-verbose) run there is zero indication that validation was
skipped.

## Location
`main.py:157-163`.

## Evidence
`main.py:157-163` — `except Exception as e: if verbose: print(...); return True`. The
docstring itself flags it: "treated as non-blocking, matching prior behavior."

## Impact
Defense-in-depth gap on the one gate that keeps unbootable ROMs (bad $FFFA-$FFFF vectors,
missing APU init) from shipping as "✅ SUCCESS". Requires a second failure (broken
diagnostics) to bite, hence MEDIUM rather than HIGH, but the swallow is fully silent by
default.

## Related
Closed #6 (the gate this bypasses), #15 (gate shared with `compile`); open #130 (TD-02, duplicate validators).

## Suggested Fix
Always print the "ROM validation could not run: {e} — ROM NOT validated" warning (not just
under verbose); consider exiting nonzero unless `--skip-validation` was passed, since the
user explicitly has that escape hatch.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
