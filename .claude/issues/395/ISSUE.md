# REG-25: test_drum_engine.py::test_main_execution_success never executes drum_engine.py's actual __main__ block

**Severity:** LOW · **Domain:** regression · **Source:** docs/audits/AUDIT_REGRESSION_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/395

## Description
`test_main_execution_success` reimplements the `__main__` block's logic inline against
mocks rather than invoking the module, and wraps everything in a blanket
`except Exception: pass` — so it passes regardless of whether the real `__main__` block
works. Companion test `test_main_execution_insufficient_args` has the same shape.

## Location
`tests/test_drum_engine.py:497-546`; target is `dpcm_sampler/drum_engine.py:168-179`

## Impact
Zero regression protection on `drum_engine.py`'s CLI entry point. Low impact — standalone
debug script, not on the `main.py` pipeline path.

## Suggested Fix
Use `runpy.run_path(..., run_name="__main__")` or a real subprocess invocation against a
temp-dir JSON fixture, and narrow/remove the blanket `except`.
