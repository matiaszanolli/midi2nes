# Issue #42: REG-03: Four obsolete tests in test_audio_fixes.py are @unittest.skip'd with no replacement and no tracking issue

**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

## Description
Four test classes in `tests/test_audio_fixes.py` are skipped with `@unittest.skip("Obsolete: Assembly generation changed to MMC3 Macro Bytecode")` (lines 21, 119, 250, 386). They account for the module's 42% coverage (122 of 209 lines dead). The behaviors they used to verify (audio register/format fixes) are now unverified — they were disabled, not ported to the new format, and there is no GitHub issue tracking the gap.

## Evidence
`grep '@unittest.skip' tests/test_audio_fixes.py` → 4 hits at lines 21, 119, 250, 386, all "Obsolete: ... MMC3 Macro Bytecode".

## Impact
Whatever audio-fix invariants these guarded are now untested. Skipped-without-issue tests rot silently.

## Related
REG-02.

## Suggested Fix
Either delete the dead classes (and re-assert their invariants in a macro-bytecode-aware test) or file a tracking issue and reference it in the skip reason. Prefer porting the value assertions to the new format rather than deleting.

## Completeness Checks
- [ ] **SIBLING**: All 4 skipped classes resolved consistently (ported or removed)
- [ ] **TESTS**: Ported assertions verify the current MMC3 Macro Bytecode audio invariants
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# Issue #45: REG-05: NES-output / exporter tests assert shape, not bytes — would pass on wrong music

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

## Description
Per `_audit-severity.md`, the NES-register/exporter path is the high-blast-radius boundary where Python values become APU writes; tests there must assert exact bytes. Several exporter tests assert only file existence and presence of a header magic / substring (`assertIn("PATTERNS", content)`, `header[:5] == b'NESM\x1a'`, `assertIn(section, content)`). They would pass even if every note/timer/volume byte were wrong. The CA65 macro-bytecode (`pulse1_sequence` `.byte` stream, `ntsc_period_low/high` tables) is never byte-compared against a golden expectation for a known input.

## Evidence
- `tests/test_exporter_integration.py:106` asserts only `header[:5] == b'NESM\x1a'`.
- `tests/test_exporter_integration.py:120` asserts only `assertIn("PATTERNS", content)`.
- `tests/test_midi_parser_integration.py:77,84,89` assert only that named sections exist.

## Impact
A regression that emits correct *structure* but wrong *values* (e.g. a pitch-table off-by-one, a wrong length nibble, a swapped duty) ships green. This is precisely the failure class the severity doc rates HIGH at the register boundary.

## Related
REG-02.

## Suggested Fix
Add a golden-bytes test: parse `test_midi/simple_loop.mid` → frames → export CA65, and `assertEqual` the `pulse1_sequence` `.byte` lines and the first 32 `ntsc_period_low` bytes against a checked-in expected fragment. Same for NSF: assert the bytecode region, not just the header magic.

## Completeness Checks
- [ ] **RANGE**: Golden bytes confirm emitted NES values are within hardware range (byte / 11-bit timer)
- [ ] **CHANNEL**: Golden `ntsc_period_low` is the correct per-channel pitch table
- [ ] **SIBLING**: Byte-level assertions added for CA65 and NSF exporters
- [ ] **TESTS**: Golden-bytes test fails on any value drift for a known input
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
