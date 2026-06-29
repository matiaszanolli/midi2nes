# REG-11: e2e anchor test_full_pipeline_midi_to_validated_rom masks pipeline failures (try/except→skip + conditional assertions + skip_validation)

**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-29.md

## Description
`tests/test_e2e_pipeline.py::test_full_pipeline_midi_to_validated_rom` is "the anchor" for the parse→…→ROM round trip. It currently:
(a) runs the whole pipeline inside a bare `try: … except Exception as e: pytest.skip(...)` (`tests/test_e2e_pipeline.py:171,187-188`),
(b) sets `args.skip_validation = True` (`:169`) so the post-build ROM gate is disabled, and
(c) wraps every assertion in `if rom_path.exists():` (`:177`).

The real default pipeline works today — confirmed it generates a 524,304-byte MMC3 ROM and the assertions pass — so this is a **latent** weakness, not an active false-green. But structurally: if the pipeline ever raised (the common regression mode), the test would SKIP; if it ran but produced no ROM, the assertions would be silently bypassed and the test would PASS vacuously. None of the three failure modes (raise / no-ROM / bad-ROM-with-validation-off) produce a red test.

## Evidence
- `tests/test_e2e_pipeline.py:171` `try:` … `:187` `except Exception as e:` → `:188` `pytest.skip(...)`
- `:177` `if rom_path.exists():` guards the asserts
- `:169` `args.skip_validation = True`
- Confirmed the happy path produces a real ROM (`run_full_pipeline` → `✅ SUCCESS! ROM created … 524,304 bytes`).

## Impact
The single anchor e2e test cannot fail on a broken pipeline for valid input — it can only pass or skip. It does not exercise arranger mode or `--no-patterns` either (the skill calls out both). Blast radius is coverage-confidence: a real end-to-end regression ships green.

## Related
REG-10 / #128 (identical skip-masking pattern); REG-04 / #44 (arranger e2e still uncovered).

## Suggested Fix
Drop the broad `try/except → skip`; gate only on `@pytest.mark.requires_cc65` / a `shutil.which` skip. Assert `rom_path.exists()` unconditionally (don't make it a precondition for the asserts). Add sibling cases that run the anchor with `--arranger` and with `no_patterns=True` and `skip_validation=False`.

## Completeness Checks
- [ ] **CC65**: ROM-compile gate guarded by a real `shutil.which`/`requires_cc65` skip, not a broad except
- [ ] **SIBLING**: Same masking pattern checked in related tests (test_rom_validation_integration.py / REG-10)
- [ ] **TESTS**: Anchor asserts `rom_path.exists()` unconditionally; arranger + `--no-patterns` e2e cases added
