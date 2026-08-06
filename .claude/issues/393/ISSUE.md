# REG-23: test_no_unused_imports.py::test_no_f401_in_tracked_source is currently FAILING on master

**Severity:** MEDIUM · **Domain:** regression · **Source:** docs/audits/AUDIT_REGRESSION_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/393

## Description
`main.py:148`'s backward-compat re-export of `mappers.capacity.estimate_segment_sizes`
(added by `36348ce`/#361-#363) is flagged as an unused import by pyflakes since it's only
referenced externally (`tests/test_main_pipeline.py`), never within `main.py` itself. The
existing `# noqa: E402` comment doesn't suppress this — pyflakes doesn't honor `# noqa` at
all (verified by direct experiment).

## Location
`main.py:148-152`; gate at `tests/test_no_unused_imports.py:27-41`

## Impact
`tests/test_no_unused_imports.py` currently fails on master. Lint-level only, no
runtime/ROM impact, but a broken guard rail invites being ignored.

## Suggested Fix
Add `estimate_segment_sizes` (and the other two re-exported names) to an explicit
`__all__` in `main.py` — confirmed this suppresses pyflakes' F401 report.
