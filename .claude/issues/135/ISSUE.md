# TD-10: Bare except: idiom in utils/profiling.py swallows all errors (incl. KeyboardInterrupt)

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-06-29.md

## Description
`utils/profiling.py` uses three bare `except:` clauses that silently `break` or fall back (memory-sampling loop at `:89`, `tracemalloc.get_traced_memory()` at `:196` and `:300`). Bare `except:` also catches `KeyboardInterrupt`/`SystemExit`. None of these are on the MIDI→ROM pipeline (profiling/benchmark/debug tooling only), so the blast radius is limited to benchmark accuracy — hence LOW.

**Location:** `utils/profiling.py:89`, `:196`, `:300`

## Evidence
`grep -nE 'except\s*:' utils/profiling.py` → lines 89, 196, 300. The core pipeline (`compiler/`, `tracker/parser_fast.py`) already uses typed/`except Exception` guards, so this debt is confined to tooling.

## Impact
Profiling/benchmark numbers can be silently wrong; a `KeyboardInterrupt` inside the sampler loop is swallowed. No effect on generated ROMs.

## Suggested Fix
Replace bare `except:` with `except Exception:` (or the specific exception) and log at debug level rather than silently discarding.

## Related
Overlaps `/audit-safety`; M-9 / #32 (broad `except` in `compile_rom`).

## Completeness Checks
- [ ] **SIBLING**: Same bare-except pattern checked in related tooling (`debug/rom_tester.py:71`, `benchmarks/performance_suite.py:103`)
- [ ] **TESTS**: A regression test pins this specific fix
