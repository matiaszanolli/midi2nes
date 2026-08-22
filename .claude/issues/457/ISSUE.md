# SAFE-2026-08-21-3: Expected prepare/compile/validate RuntimeErrors (incl. missing CC65) misreported as Unexpected pipeline failure

**GitHub Issue:** #457
**Severity:** LOW
**Domain:** safety
**Source:** docs/audits/AUDIT_SAFETY_2026-08-21.md
**Status at filing:** NEW (extends sibling finding PIPE-2026-08-21-8 / #428)

## Description
#384/SAFE-2026-07-19-2 split `run_full_pipeline`'s reporting into
`except MIDI2NESError` ("expected, actionable") vs `except Exception` ("genuinely
unexpected defect"). Three raise sites don't derive from `MIDI2NESError`:
`build_and_validate_rom`'s documented failure contract is bare `RuntimeError`, so
"Failed to prepare NES project", "ROM compilation failed", and "ROM validation
failed" print as `[ERROR] Unexpected pipeline failure: ...`. The most common
real-world trigger is CC65 not installed: `check_toolchain()` raises
`ToolchainError` inside `compile_rom`, which doesn't catch that type in a typed
clause, so the pipeline banners a routine missing-toolchain condition as an
unexpected defect. Backup restore, exit code, and underlying messages are all
still correct — this is labeling/contract only.

This extends sibling finding PIPE-2026-08-21-8 (#428,
`docs/audits/AUDIT_PIPELINE_2026-08-21.md`), which documents the same #384
intent-regression but lists only the `ValueError` raisers
(`check_mapper_capacity`/`resolve_mapper`). A fix scoped to that finding's raiser
list would miss the three `RuntimeError` sites and the `ToolchainError` routing
documented here.

## Location
`main.py:1281`, `:1285`, `:1290` (`build_and_validate_rom` raises bare
`RuntimeError` for prepare/compile/validate failure); `main.py:1446-1454` (the
`except Exception` branch that prints "Unexpected pipeline failure");
`compiler/compiler.py:286-303` (`compile_rom` catches
`CompilationError`/`ValidationError` but not `ToolchainError`); `core/exceptions.py:158`
(`ToolchainError(MIDI2NESError)` — a sibling of, not a subclass of,
`CompilationError`)

## Evidence
`build_and_validate_rom` docstring (`main.py:1266-1269`) declares
"Raises ValueError (capacity) or RuntimeError (prepare/compile/validate)";
`RuntimeError` and `ToolchainError` sit outside the typed clause lists that
classify them at each site.

## Impact
Cosmetic misreporting on the default path; also makes `except MIDI2NESError`
unreliable for tests/callers wanting "any expected pipeline failure".

## Related
PIPE-2026-08-21-8 (#428), #384/SAFE-2026-07-19-2, #406/TD-11-FOLLOWUP

## Suggested Fix
Raise typed errors from the helpers (`CompilationError` / `ValidationError` / a
small `PipelineError(MIDI2NESError)`) instead of `RuntimeError`, and add
`ToolchainError` to `compile_rom`'s typed clauses; do it together with
PIPE-2026-08-21-8's (#428) `ValueError` sites so one fix closes both.

## Dedup check
`gh issue list --repo matiaszanolli/midi2nes --state open` (32 open issues, fresh
pull at publish time) — closest match is #428 (PIPE-2026-08-21-8), which covers
only the `ValueError` raiser subset; this finding's `RuntimeError`/`ToolchainError`
scope is not covered there, so filed separately per the report's own NEW status
and stated rationale.
