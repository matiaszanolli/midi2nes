# MAP-2026-07-18-1: compile subcommand fails on relative project_dir

**Severity:** HIGH · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-18.md
**Filed as:** #316

## Description
ROMCompiler.compile() never resolves project_dir to absolute. Passing it both as a path prefix and as subprocess cwd doubles the directory component, breaking `python main.py compile nes_project/ output.nes` exactly as documented in CLAUDE.md.

## Location
`compiler/compiler.py:141-180`; `compiler/cc65_wrapper.py:141,150,199-217`; `main.py:445,472`

## Suggested Fix
`project_dir = Path(project_dir).resolve()` and `output_path = Path(output_path).resolve()` at top of `ROMCompiler.compile()`.

## Related
Not a duplicate of #297 (MAP-2026-07-06-1, mapper mis-resolution).
