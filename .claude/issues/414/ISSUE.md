# REG-26: TestCA65CompilationIntegration lacks @pytest.mark.requires_cc65, hard-fails instead of skipping when CC65 is absent

**Severity:** MEDIUM · **Domain:** regression · **Source:** docs/audits/AUDIT_REGRESSION_2026-08-06.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/414

## Description
Unlike 3 other CC65-shelling test files, `TestCA65CompilationIntegration`
(`tests/test_ca65_export.py`) has no `@pytest.mark.requires_cc65` gate. Its
`_compile_and_link` helper catches `FileNotFoundError` (missing `ca65`/`ld65`) and returns
`(False, ...)`, which every test then feeds into `assertTrue`, producing a loud test
FAILURE indistinguishable from a genuine ROM-compile regression. Reproduced live by
stripping `ca65`/`ld65` from `PATH`.

## Location
- `tests/test_ca65_export.py:706-975` (`TestCA65CompilationIntegration`)
- `tests/conftest.py:19-43` (the shared `CC65_AVAILABLE` gate to reuse)

## Impact
Any contributor without CC65 installed sees 9 false-failure regressions when scoping
pytest to this file (the project's own documented practice). No production/ROM impact
when CC65 is present.

## Suggested Fix
Add `@pytest.mark.requires_cc65` at the class level, matching the 3 existing usages.
