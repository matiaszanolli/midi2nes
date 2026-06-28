# M-4: CC65 --version probes use bare command name not resolved path; get_version subprocess unguarded

**Severity:** HIGH · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
`check_toolchain` uses `shutil.which` and raises `ToolchainError` correctly, but the `--version` probes invoke the bare command name rather than the resolved `self._ca65_path`/`self._ld65_path` — a TOCTOU/PATH divergence. `get_version()` runs its subprocess unguarded. The HIGH-floor concern (ignored exit/stderr) is covered positively: `assemble`/`link` do check returncode and raise `CompilationError` with stderr — verified, not a finding.

## Evidence
```
cc65_wrapper.py:45-46    self._ca65_path = shutil.which("ca65")   # resolved...
cc65_wrapper.py:56-60    subprocess.run(["ca65","--version"], ...) # ...probe uses bare name
cc65_wrapper.py:88-97    get_version: subprocess.run unguarded
cc65_wrapper.py:139-145  raise CompilationError(... result.stderr ...)  # GOOD
```

## Impact
Low real-world blast radius. Robustness/hardening note on the CC65 error path, not a swallowed-failure bug.

## Related
M-9.

## Suggested Fix
Use `self._ca65_path`/`self._ld65_path` for the probes; wrap `get_version` subprocess in try/except.
