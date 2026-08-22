# TD-45: Two dead locals — results in run_benchmarks.py, e in profiling.py

- **Issue**: #465

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** NEW

## Description
The only two non-cosmetic pyflakes hits in non-test source (the repo-wide unused-import cleanup #264/TD-20 otherwise holds). Both are harmless: `run_batch_benchmarks` is called for its side effects; the `except` re-raises.

- `benchmarks/run_benchmarks.py:210` — `results = benchmark.run_batch_benchmarks(valid_files)` — never read
- `utils/profiling.py:337` — `except Exception as e:` — body is `success = False; raise`, `e` unused

## Evidence
```
$ python3 -m pyflakes $(git ls-files '*.py' | grep -v tests/) | grep -Ei "never used|imported but unused|redefinition"
benchmarks/run_benchmarks.py:210:5: local variable 'results' is assigned to but never used
utils/profiling.py:337:9: local variable 'e' is assigned to but never used
```

## Impact
None at runtime; lint noise only.

## Suggested Fix
Drop `results =` and the `as e`. One-line changes; suitable to fold into any nearby commit rather than a dedicated issue.

## Related
#264/TD-20, #320/TD-24, #321/TD-25 (prior instances of the same class).
