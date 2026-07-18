# REG-16: test_famistudio_export.py never exercises a frames dict carrying dpcm_sample_map

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-07-18.md
**Filed as:** #322

## Description
No fixture in tests/test_famistudio_export.py includes a dpcm_sample_map key, so the suite never exercised EXP-11's crash (FamiStudio export raises ValueError on any DPCM-bearing song).

## Location
`tests/test_famistudio_export.py`; root cause `exporter/exporter_famistudio.py:90`

## Suggested Fix
Add a fixture with dpcm_sample_map alongside a dpcm channel; assert no raise and no spurious pattern block. Add alongside EXP-11 fix.

## Related
EXP-11 (#313)
