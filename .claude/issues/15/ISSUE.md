# F-06: Step-by-step path has no prepare/compile/validate parity and run_prepare exits 0 on failure

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #15

## Description
(a) run_prepare prints success only inside if builder.prepare_project(...), no else (main.py:58); prepare_project returns True on success (project_builder.py:500) and raises on error caught nowhere, so a path/permission failure raises an uncaught traceback, and a falsy-but-non-raising return exits 0 silently. (b) No step-by-step compile/validate subcommand; manual chain ends at prepare and user runs build.sh by hand, so the validation gate (F-02) never runs.

## Evidence
main.py:58 has no else; no compile/validate in subcommands list. compile+validate exist only in run_full_pipeline:432-477.

## Impact
Step-by-step ROMs get zero post-build validation; prepare failures not surfaced as clean nonzero exit.

## Related
F-02, F-08

## Suggested Fix
Add else: sys.exit(1) to run_prepare, wrap in try/except, add compile/validate subcommand (or document that step-by-step stops at prepare).

**Location:** `main.py:55-63`; compile+validate only in `run_full_pipeline:432-477`
