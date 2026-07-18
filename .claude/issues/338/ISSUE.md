# REG-19
**Filed as:** #338

**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-07-18.md

## Description
`generate_dpcm_index.py` is imported by the live pipeline (`main.py:597`, `main.py:989`) but only its `get_dpcm_sample_ids_from_frames` / `load_dpcm_index_into_packer` halves are tested (66% total). The `os.walk`-based `generate_dpcm_index()` builder (`:100-120`) and the "DPCM sample not found → `skipped += 1`" branch inside `load_dpcm_index_into_packer` (`:85-88`) have no coverage. The skip branch is on the live packer path — a regression that swallows a genuinely-missing sample would drop a drum without a test noticing.

## Evidence
Coverage `dpcm_sampler/generate_dpcm_index.py 64 22 66% 85-88, 101-120, 157-162`.

## Impact
LOW — the walk function is offline asset prep; the skip branch is a recoverable warn-and-continue. No ROM breakage, but a silent drum drop is possible.

## Related
REG-18, `dpcm_index.json`.

## Suggested Fix
In `tests/test_dpcm_index_resolution.py`, add (a) a `tmp_path` tree of `.dmc` files → call `generate_dpcm_index(folder, out)` → assert the emitted JSON has one entry per file with sequential `id` and relative `filename`; (b) an index referencing a non-existent filename → assert `load_dpcm_index_into_packer` returns `skipped == 1, loaded == 0` and does not raise.

## Completeness Checks
- [ ] **TESTS**: the missing-sample skip branch is exercised and asserts `(loaded, skipped)` counts
- [ ] **SIBLING**: the `os.walk` builder tested alongside the resolution path it feeds