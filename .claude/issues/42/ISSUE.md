# REG-03: Four obsolete tests in test_audio_fixes.py are @unittest.skip'd with no replacement and no tracking issue

**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

GitHub: https://github.com/matiaszanolli/midi2nes/issues/42
Labels: low, regression, bug

## Description
Four test classes in `tests/test_audio_fixes.py` skipped with `@unittest.skip("Obsolete: Assembly generation changed to MMC3 Macro Bytecode")` at lines 21, 119, 250, 386. ~122 of 209 lines dead. Disabled, not ported, no tracking issue.

## Evidence
`grep '@unittest.skip' tests/test_audio_fixes.py` → 4 hits.

## Impact
Audio-fix invariants now untested; skipped-without-issue tests rot silently.

## Suggested Fix
Delete dead classes and re-assert invariants in a macro-bytecode-aware test, or file a tracking issue referenced in the skip reason. Prefer porting value assertions.
