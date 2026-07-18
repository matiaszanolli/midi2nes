# REG-17: No test calls compile_rom/ROMCompiler.compile() with a relative project_dir

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-07-18.md
**Filed as:** #323

## Description
TestRunCompile mocks main.compile_rom entirely; every other caller uses absolute tmp_path/temp_dir fixtures. No test exercises MAP-2026-07-18-1's relative-path-doubling bug.

## Location
`tests/test_main.py:760-799`; `tests/conftest.py:50-54`; root cause `compiler/compiler.py:141-180`

## Suggested Fix
Add a relative-project_dir test that fails red against current compiler.py, passes once MAP-2026-07-18-1's .resolve() fix lands.

## Related
MAP-2026-07-18-1 (#316)
