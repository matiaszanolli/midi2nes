# REG-01: CA65 compilation integration tests are RED — generated audio_engine.asm fails to assemble (branch out of range)

**Severity:** HIGH · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

GitHub: https://github.com/matiaszanolli/midi2nes/issues/39
Labels: high, regression, bug

## Description
7 of the 9 suite failures are the CA65 compilation integration tests (`TestCA65CompilationIntegration`, all 7 methods in `tests/test_ca65_export.py`). They fail not because the toolchain is missing (`ca65`/`ld65` are present at `/usr/bin`) but because the shipped engine produces an assembler error: `audio_engine.asm(178): Error: Range error (130 not in [-128..127])`. Line 178 is `bcc @is_note`, a relative branch whose target is 130 bytes away — exceeds the 6502 ±127 branch range. Every project the builder emits currently fails to compile.

## Evidence
```
audio_engine.asm(178): Error: Range error (130 not in [-128..127])
```
`nes/audio_engine.asm` (~line 177-180): `cmp #$60 / bcc @is_note / cmp #$80 / bcc @is_length`

## Impact
Suite is red on every run; masks future regressions. Generated ROMs do not compile — blast radius is every game.

## Related
REG-02.

## Suggested Fix
Fix the engine branch (replace `bcc @is_note` with `bcs :+ / jmp @is_note / :+` or restructure so the branch target is in range), then keep these 7 tests as the compile gate.
