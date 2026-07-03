# SAFE-12: Bare except: in debug/benchmark tooling swallows all exceptions

- **GitHub Issue**: https://github.com/matiaszanolli/midi2nes/issues/223
- **Severity**: LOW
- **Domain**: safety
- **Source**: docs/audits/AUDIT_SAFETY_2026-07-03.md
- **Dimension**: 1 — Swallowed-Error Handling
- **Location**: `debug/rom_tester.py:71`, `benchmarks/performance_suite.py:103`
- **Status**: NEW (filed)

## Description
Both sites use the bare `except:` idiom (no exception class), which catches everything including `KeyboardInterrupt`/`SystemExit`, not just `Exception` subclasses. `rom_tester.py:68`-72 wraps a 4-byte ROM header read for a cosmetic test-summary line (`header_ok` just stays `False` on any failure — benign). `performance_suite.py:99`-104 wraps `tracemalloc.get_traced_memory()`/`tracemalloc.stop()` in the benchmark harness and falls back to `current_memory` on failure — also benign in effect, but the bare form is unnecessarily broad and would also swallow a Ctrl-C during a benchmark run. Existing issue #135 (TD-10) already flags the identical idiom in `utils/profiling.py`, but that issue does not cover these two additional sites.

## Evidence
`rom_tester.py:68`-72: `try: header = rom_file.read_bytes()[:4]; header_ok = header == b'NES\x1a' \n except: pass`. `performance_suite.py:99`-104: `try: ... tracemalloc.stop() \n except: peak_memory_traced = current_memory`.

## Impact
Neither site is on the ROM-build pipeline (both are debug/benchmark tooling); failure in either degrades gracefully to a sensible default today. Risk is purely hardening: a bare `except:` here would also eat a user's Ctrl-C or a `SystemExit` during a long benchmark/test run, which is surprising but not data-corrupting.

## Related
Same idiom as #135 (TD-10), different files — not a duplicate (that issue's scope is `utils/profiling.py` specifically), but the same fix should probably be applied to all three at once.

## Suggested Fix
Change both to `except Exception:` at minimum (matches the rest of the codebase's convention); consider narrowing further if the specific failure mode is known.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
