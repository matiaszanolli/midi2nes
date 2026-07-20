# MAP-2026-07-19-3: Capacity pre-flight and ROM-size check live only in main.py CLI layer

Issue: #363
Labels: medium, mappers, enhancement

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-19.md

## Description
Both correctness gates for this subsystem are wired in `main.py`, not in the reusable classes. `NESProjectBuilder.prepare_project()` writes `nes.cfg`/`main.asm`/`music.asm` with no capacity check, and `ROMCompiler.compile()`/`compile_rom()` enforce the exact per-mapper size only when a `mapper` is passed — otherwise just the flat 32768-byte floor. A consumer that uses these classes as a library directly (bypassing `main.py`, e.g. building `NESProjectBuilder(...).prepare_project(...)` then `compile_rom(dir, out)` with no `mapper` arg) therefore gets: (a) no pre-link overflow message — relies entirely on `ld65` erroring; and (b) only the 32768 floor, which a truncated MMC3 (512 KB) or MMC1 (128 KB) image ≥ 32768 bytes would slip past.

## Location
`main.py:373-391` (`check_mapper_capacity`, called from `run_prepare` `main.py:534`, `run_full_pipeline` `main.py:1113` — the CLI layer only); `nes/project_builder.py:82-279` (`prepare_project` does **not** call `validate_segment_sizes`/`check_mapper_capacity`); `compiler/compiler.py:113-118,206-221` (`compile(mapper=None)` falls back to the flat `MIN_ROM_SIZE = 32768` floor).

## Evidence
`prepare_project` (`nes/project_builder.py:82`) contains no `validate_segment_sizes` call — verified by reading the full method. `compile()` size check (`compiler/compiler.py:207`) is guarded `if mapper is not None:` with an `elif rom_size < self.MIN_ROM_SIZE:` fallback. Both CLI callers (`run_compile` `main.py:509`, full pipeline `main.py:1127`) *do* pass the resolved mapper, so the CLI is fully covered; only non-CLI library use is exposed.

## Impact
Defense-in-depth only. `ld65` still errors on a genuine region overflow, so this is not a silent-overrun path; the gap is a missing clean pre-flight message and a weaker (flat-floor) size check for library consumers. No current in-tree caller is affected.

## Related
#11/#126/#127 (capacity pre-flight); #28/M-8 (exact ROM-size check). Prior 2026-06-28 audit noted `prepare_project` has no capacity check as part of the (now-resolved) auto-select-wiring finding.

## Hardware ref
`docs/MAPPER_MMC3_REFERENCE.md` §2 (per-window budgets `validate_segment_sizes` enforces); n/a for the flat-floor size check.

## Suggested Fix
Move (or mirror) the capacity pre-flight into `NESProjectBuilder.prepare_project()` and make the mapper argument effectively required for the size check (e.g. recover it from the `nes.cfg` marker inside `compile()` when `mapper is None`, the same way `run_compile` already does via `_prepared_mapper_name_from_cfg`).

## Completeness Checks
- [ ] **CONTRACT**: `prepare_project`/`compile_rom` library entry points gate the same way the CLI layer does
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface (ld65 remains the overflow backstop)
- [ ] **SIBLING**: Size check recovers mapper from nes.cfg marker the same way `run_compile` does
- [ ] **TESTS**: A regression test pins a library-path prepare/compile rejecting an oversized/mismatched image
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
