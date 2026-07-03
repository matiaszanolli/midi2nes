# D-16: _handle_pattern_event ignores the caller's use_advanced flag

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-03.md

## Description
`map_drums(midi_events, use_advanced)` threads `use_advanced` into the non-pattern path's
`_resolve_dpcm_sample_name(midi_note, velocity, use_advanced)` (line 279), but the
pattern-matched path's `_handle_pattern_event` calls
`self._resolve_dpcm_sample_name(template_note, velocity)` (line 352) with no third
argument, so it always uses the default `use_advanced=True` regardless of what the caller
passed to `map_drums`.

**Location:** `dpcm_sampler/enhanced_drum_mapper.py:352`

## Evidence
`enhanced_drum_mapper.py:279` (`use_advanced` passed) vs. `:352` (omitted, defaults `True`).

## Impact
A caller that explicitly asks for `use_advanced=False` still gets advanced velocity-split
resolution for any event that happens to land inside a detected drum pattern. Low reach —
`map_drums_to_dpcm`'s only production call site (`tracker/track_mapper.py`) always uses
the default `use_advanced=True`, so this is latent/API-surface only today.

## Suggested Fix
Pass `use_advanced` through:
`self._resolve_dpcm_sample_name(template_note, velocity, use_advanced)`.

## Related
None.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
