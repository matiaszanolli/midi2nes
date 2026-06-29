**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-06-29.md

## Description
None of the `subprocess.run` invocations in the CC65 wrapper pass a `timeout=`. The return-code and stderr handling is correct (`assemble`/`link` check `result.returncode != 0` and raise `CompilationError` with stderr — the nonzero-exit requirement is satisfied, no `shell=True`, command is a list). The only gap is that a hung or wedged assembler/linker blocks the calling process indefinitely, hanging `run_full_pipeline` / `run_compile` with no timeout backstop. The parallel pattern detector, by contrast, uses `future.result(timeout=...)`.

## Location
- `compiler/cc65_wrapper.py:143` (`assemble`), `:198` (`link`)
- `:58`, `:69` (version probes in `check_toolchain`)
- `:94`, `:102` (`get_version`)

## Evidence
`cc65_wrapper.py:143`: `result = subprocess.run(cmd, cwd=working_dir, capture_output=True, text=True)` — no `timeout`. Same shape at `:198`, `:58`, `:69`, `:94`, `:102` (all six confirmed by grep — no `timeout=` on any).

## Impact
A misbehaving toolchain build (rare) hangs the CLI with no recovery. Low likelihood; clear hardening win.

## Related
- #49 (REG-09) asks for *tests* of cc65 missing-tool/nonzero-exit handling; this is a distinct code gap (no `timeout`), not test coverage.

## Suggested Fix
Add `timeout=` (e.g. 120 s for assemble/link, 10 s for `--version`) and catch `subprocess.TimeoutExpired` → `CompilationError`/`ToolchainError`.

## Completeness Checks
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: `timeout=` added to all six `subprocess.run` call sites in the wrapper
- [ ] **TESTS**: A regression test pins the timeout path (`TimeoutExpired` → typed error, no hang)
