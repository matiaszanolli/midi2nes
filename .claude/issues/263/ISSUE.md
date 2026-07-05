**Severity:** MEDIUM · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-05.md

## Description
The mapper post-link fixup step introduced by #214/MAP-3 runs its command snippet with `subprocess.run(commands, shell=True, ...)` in `ROMCompiler._run_post_process`. This is the first and only `shell=True` in the repo — both prior safety audits (`AUDIT_SAFETY_2026-06-29.md` §D4, `AUDIT_SAFETY_2026-07-03.md` §D3/D4) explicitly certified "no `shell=True` anywhere," and `AUDIT_MAPPERS_2026-07-05.md` verified MAP-3 only from the correctness angle, not as a subprocess-safety surface.

Today the call is benign: `commands` comes from `mapper.generate_post_process_commands(is_windows)`, whose base implementation returns `""` and which no shipped mapper (NROM/MMC1/MMC3) overrides with non-empty content, so the guarded `if post_process:` block at `compiler.py:189` never executes a non-empty string; `working_dir` is passed as `cwd=`, never interpolated into the command text. So there is no user input on this path right now. The return-code/stderr/timeout handling on the path is already correct.

## Location
- `compiler/compiler.py:82-89` (the `shell=True` call)
- `compiler/compiler.py:185-189` (call site)
- `mappers/base.py:129-138` (source of `commands` — base returns `""`)

## Evidence
```python
# compiler/compiler.py:82-89
result = subprocess.run(
    commands,
    shell=True,
    cwd=working_dir,
    capture_output=True,
    text=True,
    timeout=60,
)
```
```python
# mappers/base.py:129-138 — base returns "", no shipped mapper overrides with content
def generate_post_process_commands(self, is_windows: bool = False) -> str:
    return ""
```

## Impact
No live exploit. The concern is latent and forward-looking: a maintainer adding a mapper that builds a post-process command by interpolating a user-influenced value — a project path, output ROM name, or song title — would create a silent shell-injection vector with no guard, on a code path no test currently exercises (no mapper returns non-empty commands, so `_run_post_process` is effectively dead but present). Blast radius: the `compile`/full-pipeline build step on whatever mapper adds such a command.

## Related
- #214/MAP-3 (introduced the path)
- `AUDIT_MAPPERS_2026-07-05.md` MAP-3 (verified correctness only)
- Prior "no `shell=True`" certifications in `AUDIT_SAFETY_2026-06-29.md` §D4 and `AUDIT_SAFETY_2026-07-03.md` §D3/D4

## Suggested Fix
Since the return-code/stderr/timeout handling is already correct, the minimal hardening is to (a) document the invariant that `generate_post_process_commands` must only ever return static, non-user-derived text, and (b) prefer running the snippet as an argument list (or via `shlex.split` for single-line cases) rather than `shell=True`. If genuine multi-line shell scripting is required for a future mapper, keep `shell=True` but add an explicit assertion/comment that `commands` is a compile-time constant, and add a test that fails if any mapper's post-process output contains an interpolated runtime value.

## Completeness Checks
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (build.sh/build.bat generation in `mappers/base.py`)
- [ ] **TESTS**: A regression test pins this specific fix (asserts no mapper post-process output contains an interpolated runtime value)
- [ ] **DOC**: The invariant that `generate_post_process_commands` returns static text is documented
