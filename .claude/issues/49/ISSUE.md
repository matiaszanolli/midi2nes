# REG-09: cc65_wrapper.py (70%) — missing-tool detection and nonzero-exit/stderr handling untested

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

GitHub: https://github.com/matiaszanolli/midi2nes/issues/49
Labels: medium, regression, enhancement

## Description
cc65 subprocess error branches (nonzero ca65/ld65 exit, missing-binary handling) uncovered. No test forces ca65 to fail and asserts the wrapper raises rather than reporting success — HIGH-rated "CC65 nonzero exit ignored" mode unguarded.

## Evidence
compiler/cc65_wrapper.py ~70% cov; error-handling lines (~86-99, 229-241) uncovered. No tests/test_cc65_wrapper.py.

## Impact
A future change swallowing a compile error keeps the suite green while emitting broken ROMs.

## Suggested Fix
Add tests/test_cc65_wrapper.py: (a) monkeypatch subprocess.run → rc=1 + stderr, assert CompilationError with stderr surfaced; (b) nonexistent ca65 → clear missing-tool error.
