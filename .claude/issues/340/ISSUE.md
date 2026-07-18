# DP-DPCM-01
**Filed as:** #340

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-18.md

## Description
After the #315 alias fix, four `DEFAULT_MIDI_DRUM_MAPPING` roles still have no identically-named catalog entry and no alias: `splash` (note 55), `vibraslap` (58), `triangle_mute` (80), `triangle_open` (81). Verified against the live `dpcm_index.json` (1941 entries) — none of those four names, nor an obvious alias, exists. `_resolve_dpcm_sample_name` returns `None` for these, so they route to the noise fallback rather than DPCM.

## Evidence
Catalog probe — `splash`, `vibraslap`, `triangle_mute`, `triangle_open` all MISSING; the `drum_engine.py:57-61` comment explicitly documents them as a deliberate asset gap. Confirmed live: `_resolve_dpcm_sample_name(note, 100, use_advanced=False)` returns `None` for notes 55/58/80/81.

## Impact
Songs using a splash cymbal, vibraslap, or MIDI triangle get a noise burst instead of a sample. Audible content is preserved (noise is a reasonable NES substitute), so not a data-loss case — a coverage/asset gap. Blast radius: any drummed song touching those four GM keys.

## Related
#315/DP-07 (alias table), DP-DPCM-02.

## Suggested Fix
Either add `.dmc` assets + index entries for these four, or extend `DPCM_ROLE_ALIASES` to the nearest existing catalog sound (e.g. `splash`→a crash variant). No code change needed once assets/aliases exist.

## Completeness Checks
- [ ] **SIBLING**: any other GM roles checked for the same missing-asset gap
- [ ] **TESTS**: the regression test for the alias table updated if any of the four gain an alias
- [ ] **DOC**: the deliberate asset gap documented where users would look