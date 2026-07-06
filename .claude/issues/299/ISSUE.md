# #299 — REG-15: compile_rom error-handling tests are toothless; re-mask exceptions as 'CC65 not installed'

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-07-06.md · **Status:** NEW

## Description
The REG-10/#128 fix removed the `except → pytest.skip("CC65 may not be installed")` masking from the five compile-*success* tests in `tests/test_rom_validation_integration.py`, but the same shape survives on the two compile-*failure* (negative-path) tests, where it is compounded by toothless assertions:

- `test_compilation_with_invalid_assembly` (`:216-237`) is under `@pytest.mark.requires_cc65` (class `TestROMCompilationErrorHandling`, `:199`), so the conftest gate guarantees `ca65`/`ld65` are present whenever it runs. Its body is `if result: pass  else: assert result == False` — it passes for **any** return value of `compile_rom` (truthy → `pass`; falsy → `assert result == False` is trivially true). It cannot catch a regression where invalid assembly wrongly "compiles", and any exception from `compile_rom` is swallowed as `pytest.skip("CC65 not installed")` — a false reason, since cc65 is provably present under the marker.
- `test_compilation_failure_without_rom_output` (`:305-322`, `TestPipelineFailureRecovery`, not cc65-gated) has the same `if result: assert rom_output.exists()  else: pass` toothless shape plus the same `except → skip`.

## Evidence
```python
# :228-237, inside a @pytest.mark.requires_cc65 class -> cc65 guaranteed present
try:
    result = compile_rom(project_dir, rom_output)
    if result:
        # CC65 might be lenient, but this should fail
        pass                       # <-- no assertion
    else:
        assert result == False     # <-- trivially true
except Exception:
    pytest.skip("CC65 not installed")   # <-- masks a real exception; cc65 IS installed
```

## Impact
These two tests appear to guard the compiler's failure path (bad/missing asm → no broken ROM) but assert nothing that can fail, and convert a genuine `compile_rom` crash into a green-ish skip under a false "CC65 not installed" reason — the exact failure shape this audit exists to catch, left in the file the REG-10 fix cleaned up. Blast radius: the `compiler/` negative path (silent broken-ROM detection) has no real regression net.

## Suggested Fix
Drop the `try/except → pytest.skip` from both (the `@requires_cc65` gate already handles cc65 absence for the first; add the marker to the second). Replace the pass-either-way bodies with real assertions: `assert compile_rom(project_dir, rom_output) is False` for invalid/missing asm, and `assert not rom_output.exists()` to pin that a failed compile leaves no partial ROM.

## Completeness Checks
- [ ] **CC65**: both tests run under `@requires_cc65` and no longer swallow exceptions as a skip
- [ ] **TESTS**: each asserts `compile_rom(...) is False` on invalid/missing asm and that no partial ROM is left behind
- [ ] **SIBLING**: no other test in the file retains the `except → pytest.skip("CC65 not installed")` idiom
