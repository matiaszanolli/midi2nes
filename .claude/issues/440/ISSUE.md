# EXP-2026-08-21-2: FamiStudio pattern keys mix a global and a per-channel counter — SEQUENCE references undefined patterns

GitHub: https://github.com/matiaszanolli/midi2nes/issues/440

**Severity:** MEDIUM · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-08-21.md

## Description
The first channel happens to work because the global and per-channel counts coincide. For every subsequent channel, full 64-row patterns get globally-numbered names while the final partial pattern gets a per-channel-numbered name, and the `SONG` section references per-channel 0-based names throughout. Verified by direct execution (2 channels × 130 frames):
```
defined patterns: ['pulse1_0', 'pulse1_1', 'pulse1_2', 'pulse2_3', 'pulse2_4', 'pulse2_2']
sequences:        ['"pulse1_0" "pulse1_1" "pulse1_2"', '"pulse2_0" "pulse2_1" "pulse2_2"']
SEQUENCE refs with no matching PATTERN: ['pulse2_0', 'pulse2_1']
```
`pulse2`'s sequence references two undefined patterns, and the one name that *does* resolve (`pulse2_2`) is the 2-row remainder placed where the first full pattern should play — so even a lenient importer plays the channel scrambled. Related cosmetic defect in the same emitter: the remainder pattern is declared `LENGTH 64` (`:145`) regardless of its actual row count.

## Location
`exporter/exporter_famistudio.py:129` (full patterns: `pattern_key = f"{channel}_{len(patterns)}"` — `len(patterns)` counts **all** channels' patterns emitted so far), `:135` (remainder pattern: keyed by the **per-channel** count), `:167` (`SEQUENCE` emits `"{channel}_{i}" for i in range(pattern_count)` — per-channel 0-based)

## Spec ref
FamiStudio text format (self-consistency of `PATTERN "name"` definitions vs `SEQUENCE "name"` references within the emitted file)

## Impact
The FamiStudio text export is structurally self-inconsistent for any frames input with ≥2 non-empty channels spanning ≥64 frames — i.e. essentially every real song. Blast radius is contained: `generate_famistudio_txt` is not wired to any CLI path (`--format` offers only `ca65`), so only library/test consumers hit it — which is what keeps this MEDIUM rather than HIGH.

## Related
#339/REG-20 (the weak structural tests that mask this — only asserts `"PATTERNS" in output`); EXP-2026-08-21-3 (companion FamiStudio-export finding, filed separately).

## Suggested Fix
Key full patterns with the per-channel count (the same `len([k for k in patterns if k.startswith(channel)])` expression the remainder branch already uses, or a simple per-channel counter), and emit the remainder's real `LENGTH`. Strengthen `tests/test_famistudio_export.py` to assert every `SEQUENCE` reference resolves to a defined `PATTERN`.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (CA65 exporter's own pattern/reference naming does not share this global/per-channel mismatch — confirmed distinct code path)
- [ ] **TESTS**: A regression test pins this specific fix — every `SEQUENCE` reference resolves to a defined `PATTERN`, for ≥2 channels and ≥64 frames
