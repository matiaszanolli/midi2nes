# MAP-6: MapperFactory.auto_select()/can_fit_data() are reachable only from unit tests, never from any real pipeline path

- **Issue:** https://github.com/matiaszanolli/midi2nes/issues/217
- **Labels:** low, mappers, bug
- **Source report:** `docs/audits/AUDIT_MAPPERS_2026-07-03.md`
- **Finding ID:** MAP-6
- **Severity:** LOW

## Body filed

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
