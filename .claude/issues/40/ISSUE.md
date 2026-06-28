# REG-02: Stale e2e assertions check the old CA65 output format (.segment HEADER) the exporter no longer emits

Labels: bug, medium, regression

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

## Description
2 of the 9 failures assert that exported `.asm` contains `.segment "HEADER"`. The CA65 exporter switched to "MMC3 Macro Bytecode" mode and now emits `.segment "DPCM"`, `.segment "CODE_8000"`, `.segment "BANK_00"` with macro/sequence tables — **no `HEADER` segment**. The assertions test a format that no longer exists, so they fail on correct output and would never catch a real regression in the *current* format.

## Evidence
```
AssertionError: '.segment "HEADER"' not found in '; CA65 Assembly Export (MMC3 Macro Bytecode) ...'
```
- `tests/test_midi_parser_integration.py:71` (`verify_ca65_assembly` required-section list) still lists `.segment "HEADER"`.
- `tests/test_e2e_pipeline.py:234` still asserts `'.segment "HEADER"' in content`.
Actual output begins `.segment "DPCM"` / `.segment "CODE_8000"` / `.segment "BANK_00"` and contains `pulse1_sequence`, `ntsc_period_low`, `instrument_table`, `macro_vol_0`.

## Impact
False failures; the e2e/parser-integration tests no longer validate the real artifact. They cannot catch a genuine break in the macro-bytecode format.

## Related
REG-01, REG-03, REG-05.

## Suggested Fix
Update `verify_ca65_assembly`'s required-section list (and the e2e assertion) to the current segments (`DPCM`, `CODE_8000`, `BANK_00`) and assert presence of `pulse1_sequence`/`ntsc_period_low`/`instrument_table`. Better: assert exact bytecode bytes for a known input (see REG-05).

## Completeness Checks
- [ ] **CONTRACT**: The assertion list matches the exporter's current segment output
- [ ] **SIBLING**: Both `test_midi_parser_integration.py` and `test_e2e_pipeline.py` updated in lockstep
- [ ] **TESTS**: Updated assertions still fail if the macro-bytecode format genuinely regresses
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
