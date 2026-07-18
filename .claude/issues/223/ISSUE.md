# SAFE-12: Bare except: in debug/benchmark tooling swallows all exceptions

**Severity:** LOW · **Domain:** safety

## Description
`rom_tester.py:71` and `performance_suite.py:103` use bare `except:` (catches KeyboardInterrupt/SystemExit too). Both degrade gracefully today but should be narrowed. Same idiom as #135 (TD-10) in `utils/profiling.py`, different files.

## Location
`debug/rom_tester.py:71`, `benchmarks/performance_suite.py:103`

## Suggested Fix
Change both to `except Exception:` at minimum.

## Completeness Checks
- [ ] TESTS: regression test pins this fix
- [ ] DOC: doc corrected if contradicted
