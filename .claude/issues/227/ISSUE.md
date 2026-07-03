# TD-15: main.py imports two names it never uses (typing.Dict, EnhancedDrumMapper)

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-07-03.md

## Description
`main.py` imports two names it never uses:
- `main.py:6` — `from typing import Dict, Optional` — only `Optional` is ever referenced (`grep -n "Dict\[" main.py` → no hits).
- `main.py:24` — `from dpcm_sampler.enhanced_drum_mapper import EnhancedDrumMapper, DrumMapperConfig` — only `DrumMapperConfig` is used (`load_config` at `main.py:462-466`); `EnhancedDrumMapper` has zero references anywhere else in the file.

Confirmed via `pyflakes main.py`:
```
main.py:6:1: 'typing.Dict' imported but unused
main.py:24:1: 'dpcm_sampler.enhanced_drum_mapper.EnhancedDrumMapper' imported but unused
```

**Location:** `main.py:6`, `main.py:24`

## Evidence
- `python -m pyflakes main.py` — reproduces both warnings at the exact lines above.
- `grep -n "EnhancedDrumMapper" main.py` → only the import line.

## Impact
Misleading (implies `main.py` instantiates a drum mapper directly; it doesn't) and pulls the class into the CLI's import graph for nothing. Same category as the already-fixed #112 (P-04, "unused top-level import" in `main.py`), different symbols.

## Suggested Fix
Drop `Dict` from the typing import and drop `EnhancedDrumMapper` from the `enhanced_drum_mapper` import, keeping only `DrumMapperConfig`.

## Related
Existing #112 (P-04, closed — same "unused top-level import" pattern in `main.py`, different names). TD-16 (#228, same pattern, `debug/` tooling side).

## Completeness Checks
- [ ] **SIBLING**: Same unused-import pattern checked in related files (see TD-16 for `debug/` tooling)
- [ ] **TESTS**: A lint gate (e.g. `pyflakes` in CI) pins this so it doesn't regress
