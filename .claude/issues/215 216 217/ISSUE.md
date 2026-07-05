# #215 — MAP-4: MMC3 nes.cfg declares an unused OAM memory region and segment — harmless ld65 warning on every build

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-03.md

## Description
The MMC3 linker config reserves a `$0200-$02FF` `OAM` (sprite Object Attribute Memory)
region and declares a matching `.segment "OAM"`, but neither `nes/project_builder.py`'s
generated `main.asm` nor `exporter/exporter_ca65.py`'s `music.asm` nor
`nes/debug_overlay.py` ever emit anything into `.segment "OAM"` — this is a music-only
ROM generator with no sprite/graphics engine. `ld65` warns on every default build.

## Evidence
Reproduced on the same real build as MAP-1 (same report):
```
ld65: Warning: .../nes.cfg(203): Segment 'OAM' does not exist
$ grep -rn '"OAM"' nes/project_builder.py exporter/exporter_ca65.py nes/debug_overlay.py
(no matches)
```
Confirmed against current code (2026-07-03): `mappers/mmc3.py:54` declares the `OAM`
memory region and `mappers/mmc3.py:78` declares the `OAM` segment; no producer file
references `.segment "OAM"`.

## Impact
Cosmetic — an extra warning line in every MMC3 build's `ld65` output (which also now
includes the real MAP-1 overflow warnings, making it harder to spot the actionable ones
among noise). No effect on the produced ROM's correctness.

## Suggested Fix
Either remove the unused `OAM` `MEMORY`/`SEGMENTS` entries from `mappers/mmc3.py:54,78`,
or wire up an actual OAM shadow-buffer segment usage if sprite support is planned (see
`docs/ROADMAP.md`).

## Completeness Checks
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix

---

# #216 — MAP-5: Stale comment in exporter_ca65.py claims MMC3 embeds its own .segment HEADER — no longer true since #22

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-03.md

## Description
`export_direct_frames(..., standalone=True)`'s header emission still guards with
`if '.segment "HEADER"' not in header_asm: lines.append('.segment "HEADER"')` and a
comment explaining "MMC3 embeds its own `.segment \"HEADER\"`; NROM/MMC1 don't." That was
true before #22 (fixed in commit `007f5c4`); `MMC3Mapper.generate_header_asm()`
(`mappers/mmc3.py:38-48`) now returns bare `.byte` lines identically to NROM/MMC1
(`mappers/nrom.py:39-44`, `mappers/mmc1.py:40-45`). The guard branch is harmless (it
still emits `.segment "HEADER"` correctly for every mapper today, since none of them
embed it anymore), but the comment misdescribes current mapper behavior.

## Evidence
```
exporter/exporter_ca65.py:109  # MMC3 embeds its own `.segment "HEADER"`; NROM/MMC1 don't.
exporter/exporter_ca65.py:110  if '.segment "HEADER"' not in header_asm:
mappers/mmc3.py:43             .byte "NES", $1A                          # no .segment here anymore
```
Confirmed against current code (2026-07-03): the stale comment is still present verbatim
in `exporter/exporter_ca65.py:109-111`, and `MMC3Mapper.generate_header_asm()` returns
only bare `.byte` lines (no `.segment` directive).

## Impact
None on behavior; misleads a future reader into thinking the branch is still load-bearing
for MMC3 specifically.

## Suggested Fix
Update the comment to state all three mappers return bare header bytes today, or simplify
by removing the now-always-true guard and unconditionally appending `.segment "HEADER"`.

**Related:** #22.

## Completeness Checks
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)

---

# #217 — MAP-6: MapperFactory.auto_select()/can_fit_data() are reachable only from unit tests, never from any real pipeline path

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-03.md

## Description
`main.py` has no `--mapper` CLI flag; both places that build a real project
(`run_prepare`, `run_full_pipeline`) explicitly instantiate `MMC3Mapper()` and pass it
in, bypassing `NESProjectBuilder`'s own `mapper_name="auto"` default and never calling
`auto_select_mapper(data_size)`. `MapperFactory.auto_select()`'s smallest-fits-first logic
(verified correct: `nrom`→`mmc1`→`mmc3` order, `can_fit_data()` checked, "nothing fits"
raises against the largest mapper's capacity) is therefore exercised only by
`tests/test_mappers.py`, never by a live CLI invocation.

## Evidence
```
$ grep -n -- '--mapper' main.py
(no matches)
main.py:243-244   from mappers.mmc3 import MMC3Mapper; mapper = MMC3Mapper()   # run_prepare
main.py:684-685   from mappers.mmc3 import MMC3Mapper; mapper = MMC3Mapper()   # run_full_pipeline
```
Confirmed against current code (2026-07-03): both call sites still hardcode
`MMC3Mapper()`; `mappers/factory.py:83-114`'s `auto_select` remains unreferenced outside
`mappers/factory.py` and `tests/test_mappers.py`.

## Impact
Not a correctness bug — the size-based auto-selection machinery is simply
unreachable-from-the-CLI code today, and its test coverage (closed via #47/REG-07) only
proves the algorithm works in isolation, not that it is wired to anything. If a song is
small enough to fit NROM/MMC1, the pipeline still always builds the full 512 KB MMC3 ROM.

## Suggested Fix
Either add a `--mapper auto|nrom|mmc1|mmc3` CLI flag that threads through to
`run_prepare`/`run_full_pipeline` and calls `auto_select_mapper(data_size)` when `auto` is
chosen, or remove the auto-selection machinery if smallest-mapper selection is not a
near-term goal (see `docs/ROADMAP.md`: "Mapper coverage and auto-selection tuning").

**Related:** #25 (closed — resolved a conflict in this same area), #47/REG-07 (closed —
added the unit tests that are this code's only caller).

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
