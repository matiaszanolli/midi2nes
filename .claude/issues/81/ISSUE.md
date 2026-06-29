**Severity:** HIGH · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-06-29.md

NSF exporter emits JSON-as-data and a hand-assembled play routine with wrong branch offsets — not a playable NSF.

## Description
Two independent defects make the NSF output non-functional:
1. Channel "data" is serialized as a UTF-8 **JSON string** embedded in the NSF binary (`json.dumps(compressed_data)`), which is not 6502-executable or APU-loadable; the `NSFMacroPacker` docstring admits this is draft and "will eventually replace the JSON-based serialization".
2. The hand-assembled `_generate_play_routine` branch offsets are wrong. `BEQ done` (`$F0,$0A`) targets routine offset 30, but `RTS` is at offset 28 — the branch lands one byte past the routine, into frame data executed as code. `BNE loop` (`$D0,$E7`) targets offset 3 (mid-instruction), not the `LDA ($00),Y` load loop at offset 14.

## Location
`exporter/exporter_nsf.py:124-132` (`_serialize_compressed_data` → `json.dumps(...).encode('utf-8')`), `:134-153` (`_generate_play_routine`).

## Spec ref
A valid NSF must contain 6502 code at `play_address`; `docs/NES_APU_REFERENCE.md` for the `$4000–$400F` register window the loop claims to fill.

## Evidence
Offset arithmetic over the `:137-152` byte list: `BEQ` operand `$0A` from next-PC 20 → 30 (past `RTS@28`); `BNE` operand `$E7` (−25) from next-PC 28 → 3 (not the loop label at 14). `:129` `json_str = json.dumps(compressed_data)`.

## Impact
Any NSF produced is not a playable NSF (would crash or play garbage in an NSF player). Practical blast radius is currently limited because EXP-03 makes the NSF branch unreachable from the CLI, but `NSFExporter.export()` is public and called directly by tests/other tools.

## Related
EXP-03 (unreachable dispatch).

## Suggested Fix
Either replace the JSON serializer with the `NSFMacroPacker` binary path and a correctly-assembled (or `ca65`-assembled) play routine, or mark NSF export explicitly unsupported and remove it from the CLI until implemented.

## Completeness Checks
- [ ] **CONTRACT**: If the serialized data shape changes, the consumer/player was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related exporters (CA65 serialization)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
