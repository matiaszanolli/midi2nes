# REG-02: Stale e2e assertions check the old CA65 output format (.segment HEADER) the exporter no longer emits

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

GitHub: https://github.com/matiaszanolli/midi2nes/issues/40
Labels: medium, regression, bug

## Description
2 of 9 failures assert exported `.asm` contains `.segment "HEADER"`. The CA65 exporter switched to MMC3 Macro Bytecode mode emitting `.segment "DPCM"`, `.segment "CODE_8000"`, `.segment "BANK_00"` — no HEADER segment. Assertions test a defunct format.

## Evidence
- `tests/test_midi_parser_integration.py:71` (`verify_ca65_assembly`) lists `.segment "HEADER"`.
- `tests/test_e2e_pipeline.py:234` asserts `'.segment "HEADER"' in content`.

## Impact
False failures; e2e/parser-integration tests no longer validate the real artifact.

## Related
REG-01, REG-03, REG-05.

## Suggested Fix
Update required-section list to current segments (DPCM, CODE_8000, BANK_00) and assert pulse1_sequence/ntsc_period_low/instrument_table. Better: golden bytes (REG-05).
