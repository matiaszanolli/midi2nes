# TD-16: Unused typing/dataclass imports scattered across debug/ tooling

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-07-03.md

## Description
`pyflakes` over `debug/` (excluding `tests/` and the local `venv/`) reports four unused-import sites, all in developer tooling rather than the pipeline:
- `debug/rom_diagnostics.py:23` — `Optional`, `Any` imported from `typing`, neither used.
- `debug/nes_devtools.py:10` — `List`, `Tuple`, `Optional` imported from `typing`, none used.
- `debug/pipeline_integration_example.py:16` — `pathlib.Path` imported and never referenced.
- `debug/__init__.py:32` — `ROMDiagnosticResult` imported into the public surface but nothing re-exports or uses it internally.

**Location:** `debug/rom_diagnostics.py:23`, `debug/nes_devtools.py:10`, `debug/pipeline_integration_example.py:16`, `debug/__init__.py:32`

## Evidence
`python -m pyflakes debug/` (filtered to non-test, non-venv paths) reproduces all four:
```
debug/pipeline_integration_example.py:16:1: 'pathlib.Path' imported but unused
debug/rom_diagnostics.py:23:1: 'typing.Optional' imported but unused
debug/rom_diagnostics.py:23:1: 'typing.Any' imported but unused
debug/nes_devtools.py:10:1: 'typing.List' imported but unused
debug/nes_devtools.py:10:1: 'typing.Tuple' imported but unused
debug/nes_devtools.py:10:1: 'typing.Optional' imported but unused
debug/__init__.py:32:5: '.rom_diagnostics.ROMDiagnosticResult' imported but unused
```

## Impact
LOW — confined to `debug/` diagnostic tooling, no pipeline/ROM effect. Purely a lint/navigation cost.

## Suggested Fix
Remove the unused names from each import line. If `debug/__init__.py`'s `ROMDiagnosticResult` re-export is intentional public API, add `__all__` so linters (and readers) recognize it as deliberate rather than dead.

## Related
TD-15 (#227, same pattern, pipeline side (`main.py`) instead of tooling side).

## Completeness Checks
- [ ] **SIBLING**: Same unused-import pattern checked in related files (see TD-15 for `main.py`)
- [ ] **TESTS**: A lint gate (e.g. `pyflakes` in CI) pins this so it doesn't regress
