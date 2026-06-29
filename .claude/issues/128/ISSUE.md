# REG-10: Four ROM-compile integration tests silently SKIP on a real compile failure — stale music.asm fixture, misleading "CC65 may not be installed" skip

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-29.md

## Description
`tests/test_rom_validation_integration.py` is the designated "compile a real ROM and validate its bytes" gate — its docstring calls step 6 "THE CRITICAL STEP … the test that will catch if ROMs are being generated without proper validation." With `ca65`/`ld65` present at `/usr/bin`, **4 of its 9 tests SKIP at runtime**.

Root cause: the hand-written `music.asm` fixture (`tests/test_rom_validation_integration.py:64-85`) defines the music entry points as bare labels `init_music:` / `update_music:` with **no `.global`/`.export`**, so `ld65` fails with `Unresolved external 'init_music' referenced in main.asm`, and `compile_rom` returns `False`. The test then runs `pytest.skip("CC65 compilation failed - CC65 may not be installed")`, blaming a missing toolchain that is in fact installed.

The real CA65 exporter emits `.export init_music, update_music` (`exporter/exporter_ca65.py:1138`), so the *real* pipeline links fine — only the stale fixture is broken.

## Evidence
- Fixture (`tests/test_rom_validation_integration.py:70-84`) has `init_music:` / `update_music:` with no export directive.
- `main.asm` template declares `.global init_music` / `jsr init_music` (`nes/project_builder.py`), so the link is unresolved.
- The `except Exception → pytest.skip(...)` mask repeats at lines `98-100, 151-153, 203-205, 257-259, 333-335`.
- Confirmed: `exporter/exporter_ca65.py:1138` emits `.export init_music, update_music` — the real pipeline links.

```
$ python -m pytest tests/test_rom_validation_integration.py -v
... 4 passed, 5 skipped       # ca65/ld65 both at /usr/bin
[ERROR] Failed to link ROM: Unresolved external 'init_music' referenced in main.asm(60)
ld65: Error: 2 unresolved external(s) found
compile_rom returned: False
```

## Impact
Four e2e ROM-byte assertions (valid iNES header, `reset_vectors_valid`, `apu_pattern_count > 0`, `zero_byte_percent < 85`) provide **zero coverage on every run** while the suite reports green. The `except Exception → pytest.skip("…CC65 may not be installed")` cannot distinguish "tool absent" from "engine emits unlinkable asm" — so a REG-01-class failure (a ROM that won't compile/boot, CRITICAL blast radius) would be **masked as a skip**, not a failure. The gate self-disables on the failure it exists to catch.

## Related
Prior REG-01 (now-fixed compile regression these tests should have guarded); REG-11 (same masking shape).

## Suggested Fix
1. Fix the fixture: add `.export init_music, update_music` (or `.global`) to the hand-written `music.asm` so it links like the real exporter output.
2. Replace `except Exception → pytest.skip(...)` with a real `cc65`-presence check at module/fixture scope (`shutil.which("ca65")`) and let an actual compile failure **FAIL**, not skip. Only skip when the toolchain is genuinely absent.

## Completeness Checks
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same skip-masking pattern checked in related tests (e.g. test_e2e_pipeline.py / REG-11)
- [ ] **TESTS**: A regression test pins this specific fix (fixture links; real compile failure FAILs)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
