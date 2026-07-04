# MAP-3: ROMCompiler.compile() never calls generate_post_process_commands() — build.sh and compiler.compile_rom() can diverge

- **Issue:** https://github.com/matiaszanolli/midi2nes/issues/214
- **Labels:** medium, mappers, bug
- **Source report:** `docs/audits/AUDIT_MAPPERS_2026-07-03.md`
- **Finding ID:** MAP-3
- **Severity:** MEDIUM

## Body filed

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-03.md

## Description
`nes/project_builder.py`'s `_create_build_script()` (line 648) delegates to
`self.mapper.generate_build_script(is_windows)`, which (via
`BaseMapper.generate_build_script`, `mappers/base.py:97-127`) appends
`generate_post_process_commands()` after linking — this is how `build.sh`/`build.bat`
picks up a mapper's post-link fixup. `compiler/compiler.py`'s `ROMCompiler.compile()` is a
separate, parallel implementation of "assemble, link, verify" used by `main.py compile` /
`compiler.compile_rom()` — it never calls `generate_post_process_commands()` at all, and
has no mapper reference to call it with. A project prepared with a mapper that needs a
post-link step and then compiled via `compiler.compile_rom()` instead of running
`build.sh` silently skips that step.

## Evidence
```
$ grep -rn "generate_post_process_commands" compiler/
(no matches)
```
Confirmed against current code (2026-07-03): `compiler/compiler.py` still has zero
references to `generate_post_process_commands` or a mapper instance.

## Impact
Given MAP-2 (companion CRITICAL finding, same report), this gap is currently
**accidentally protective** for MMC1 — a ROM compiled via `compiler.compile_rom()`
(skipping the fixup) has *correct* vectors, while one built via `build.sh` (running the
fixup) has *corrupted* ones. That is itself evidence of the inconsistency this finding
flags: the same prepared project produces a working ROM through one public entry point
and a bricked one through another, which is a real API hazard independent of which
specific mapper is buggy today. Fixing MAP-2 (removing/fixing the MMC1 fixup) would make
the two paths agree by removing the need for this call entirely for MMC1; if a future
mapper legitimately needs a post-link step, this gap would then cause the same
build.sh-vs-compiler.compile() divergence MAP-2 exposed. Rated MEDIUM (not HIGH) because
it is unreachable from the CLI today (no `--mapper` flag; `prepare`/the full pipeline
hardcode MMC3, which needs no post-process step) and because acting on it without first
fixing MAP-2 would propagate MAP-2's corruption into the `compiler.compile()` path too.

## Suggested Fix
Fix MAP-2 first. Then thread a mapper reference into `ROMCompiler` (constructor or
`compile()` parameter) and call `self.mapper.generate_post_process_commands()` after a
successful link, so `build.sh` and `compiler.compile_rom()` stay behaviorally identical
for every mapper.

**Related:** MAP-2 (fix that one first), #18.

## Completeness Checks
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix

---

## Note on #245

This round was invoked as `/fix-issue 214 245`. `gh issue view 245` returns "Could not
resolve to an issue or pull request with the number of 245" — the repo's highest issue
number is #232. Per user decision, #245 was skipped; only #214 is addressed here.
