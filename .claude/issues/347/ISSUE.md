# TD-27
**Filed as:** #347

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-07-18.md

## Description
The `src/` directory holds hand-written NSF-oriented player assembly (`src/music_driver.s` header: "NSF-compatible music player logic"), `src/nsf_main_driver.s`, plus a shared `src/nes.inc`. Nothing in the codebase references them: no Python module, no `.cfg`/`.sh` build script, and `NESProjectBuilder` emits its own inline templates (`audio_engine.asm`, `mmc3_init.asm`) via `nes/project_builder.py` rather than copying from `src/`. The NSF export path these files target is itself unimplemented — `exporter/exporter_nsf.py` raises `NotImplementedError` (#81). Last touched 2025-08-10; effectively orphaned scaffolding.

## Evidence
```
$ git ls-files src/
src/music_driver.s
src/nes.inc
src/nsf_main_driver.s
$ grep -rn "music_driver\|nsf_main_driver" --include='*.py' .   # no hits
```

## Impact
Dead weight that reads as if it were part of the build. A newcomer editing the audio engine may waste time in `src/*.s` believing it is live. No runtime risk. Blast radius: developer confusion only.

## Related
#81 (NSF export not implemented), NH-28/#203 (`nes/mmc3_init.asm` dead ASM — same "orphaned assembly file" category).

## Suggested Fix
Either delete `src/` (git history preserves it), or if it is intended as the seed for the future real NSF engine, move it under a clearly-marked location (e.g. `docs/` or a `scaffolding/` prefix) and reference it from the #81 tracking issue so its purpose is discoverable.

## Completeness Checks
- [ ] **SIBLING**: NH-28/#203 (`nes/mmc3_init.asm`) considered together as the same orphaned-ASM cleanup
- [ ] **DOC**: if kept, `src/` purpose documented and linked from #81