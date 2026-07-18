# TD-25: Shadowed re-import of tempfile in benchmarks/performance_suite.py

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-07-18.md
**Filed as:** #321

## Description
Redundant `import tempfile` at line 472 inside __main__ guard, already imported at module scope line 11. pyflakes: "redefinition of unused 'tempfile' from line 11".

## Location
`benchmarks/performance_suite.py:11,472`

## Suggested Fix
Delete the redundant import at line 472.

## Related
TD-20/#231
