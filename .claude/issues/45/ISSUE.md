# REG-05: NES-output / exporter tests assert shape, not bytes — would pass on wrong music

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

GitHub: https://github.com/matiaszanolli/midi2nes/issues/45
Labels: medium, regression, enhancement

## Description
Exporter tests assert only file existence / header magic / substrings. They'd pass even if every note/timer/volume byte were wrong. CA65 macro-bytecode (pulse1_sequence .byte stream, ntsc_period_low/high) never byte-compared against a golden.

## Evidence
- test_exporter_integration.py:106 (NESM magic), :120 (assertIn PATTERNS).
- test_midi_parser_integration.py:77,84,89 (section presence only).

## Impact
Wrong values with correct structure (pitch off-by-one, wrong length nibble, swapped duty) ship green at the HIGH-rated register boundary.

## Suggested Fix
Golden-bytes test over test_midi/simple_loop.mid: assertEqual pulse1_sequence .byte lines + first 32 ntsc_period_low bytes against a checked-in fragment. Same for NSF bytecode region.
