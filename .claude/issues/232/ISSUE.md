# REG-14: FamiStudio export tests are still shape-only (assertIn("PATTERNS", ...)) — the golden-bytes fix for #45/REG-05 only covers the CA65 path

- **Issue**: #232
- **Severity**: MEDIUM
- **Dimension**: Weak assertions (Dim 2)
- **Location**: `tests/test_famistudio_export.py:49-70` (`test_generate_famistudio_txt`), `tests/test_exporter_integration.py:108-121` (`test_famistudio_export_with_compression`)
- **Status**: Regression of #45 (partial fix — the closed issue's own evidence explicitly named this exact
  test/assertion, `test_famistudio_export_with_compression` asserting only `assertIn("PATTERNS", content)`,
  and it is still true verbatim today; only the CA65/`test_midi_parser_integration.py` half of the original
  finding was addressed)
- **Source**: `docs/audits/AUDIT_REGRESSION_2026-07-03.md`

## Description
`TestCA65GoldenBytes` (added for #45) pins exact `.byte` streams for the CA65
macro-bytecode path, but the FamiStudio exporter — a separate, real export format
(`exporter/exporter_famistudio.py`) — still has no equivalent. `test_generate_famistudio_txt` checks
section-presence strings (`"PROJECT"`, `"INSTRUMENTS"`, `"PATTERNS"`) plus a few `assertIn("C-4 15", ...)`
style substring checks; `test_famistudio_export_with_compression`
(`tests/test_exporter_integration.py:119-121`) checks only `assertIn("PATTERNS", content)` and one note
string. Neither test would catch a wrong note-name/octave conversion for any note not explicitly checked,
a pattern emitted under the wrong track/frame, or note data silently dropped from the output — the tests
would still pass on a FamiStudio export that describes different music than the input.

## Evidence
```
$ grep -n 'assertIn(.PATTERNS.' tests/test_famistudio_export.py tests/test_exporter_integration.py
tests/test_famistudio_export.py:61:        self.assertIn("PATTERNS", output)
tests/test_exporter_integration.py:121:            self.assertIn("PATTERNS", content)
$ grep -n "class Test" tests/test_famistudio_export.py tests/test_exporter_integration.py
tests/test_famistudio_export.py:8:class TestFamiStudioExport(unittest.TestCase):
tests/test_exporter_integration.py:16:class TestExporterIntegration(unittest.TestCase):
tests/test_exporter_integration.py:125:class TestCA65GoldenBytes(unittest.TestCase):   # CA65 only
```
No `TestFamiStudioGoldenBytes`-equivalent class exists.

## Impact
FamiStudio export is a secondary/external-tracker format (not wired into the default ROM
pipeline), so blast radius is contained to users who explicitly export to FamiStudio — same contained
scope the 2026-06-29 EXP audit assigned FamiTracker/FamiStudio bugs. Still, this is the same failure
class the closed #45 exists to prevent, left open on a sibling path (the closed issue's own cited
evidence line named this exact assertion verbatim).

## Related
#45 (REG-05, closed — partial fix); `docs/audits/AUDIT_EXPORTERS_2026-06-29.md`'s
FamiStudio/FamiTracker octave findings (same file, different bug class).

## Suggested Fix
Add a `TestFamiStudioGoldenBytes`-style case: run a small crafted `frames` dict (or
`test_midi/simple_loop.mid` through the real pipeline) through `generate_famistudio_txt`, and assert the
exact emitted pattern-row text for every note (not a subset), not just structural markers.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
