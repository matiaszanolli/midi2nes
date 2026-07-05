# PL-08: compile --mapper has no 'auto', so a prepare --mapper auto project has no matching compile invocation

**Issue:** #269
**Severity:** LOW · **Domain:** pipeline · **Dimension:** 2 (full vs step-by-step parity)
**Source:** AUDIT_PIPELINE_2026-07-05.md
**Labels:** low, pipeline, enhancement

## Description
`prepare` accepts `--mapper auto` (resolves at prepare-time via `MapperFactory.auto_select()` and bakes the mapper's `nes.cfg`/header into the project). `compile` cannot recover that choice from the project dir and offers no `auto` value. Accepting `compile`'s default `mmc3` against an auto-resolved `nrom`/`mmc1` project makes `compile_rom`'s exact PRG-size check raise a `CompilationError` (distinct 32K/128K/512K sizes → no false pass). Step-by-step only; default pipeline unaffected.

## Location
- `main.py:1034` — `prepare --mapper` choices include `auto`
- `main.py:1044` — `compile --mapper` choices are `nrom`/`mmc1`/`mmc3` only
- Exact-size check in `compiler/compiler.py`.

## Evidence
```python
# main.py:1034
p_prepare.add_argument('--mapper', choices=['auto','nrom','mmc1','mmc3'], default='mmc3', ...)
# main.py:1044
p_compile.add_argument('--mapper', choices=['nrom','mmc1','mmc3'], default='mmc3', ...)  # no 'auto'
```

## Impact
Usability/parity only — loud, recoverable failure with clear size-mismatch message; no bad ROM left behind. Not the HIGH header-vs-nes.cfg floor.

## Suggested Fix
Add `auto` to `compile --mapper` (re-run `auto_select` against the project's own `music.asm`, as `resolve_mapper` already does), or have `prepare` record the resolved mapper into the project dir so `compile` defaults to it.
