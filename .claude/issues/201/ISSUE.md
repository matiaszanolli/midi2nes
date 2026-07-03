# D-15: DEFAULT_MIDI_DRUM_MAPPING's GM-wide coverage (#73) is code-complete but the shipped dpcm_index.json backs only 8 of 40 role names

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-03.md

## Description
`DEFAULT_MIDI_DRUM_MAPPING` now defines 47 generic role names across the full GM
percussion range (35–81), and `_resolve_dpcm_sample_name`'s fallback chain correctly
reaches it (re-verified: cascade order velocity-split → primary → default role name, each
gated by `if name in self.sample_index`). However the *shipped* `dpcm_index.json` — the
only index that ships with the repo — only contains 8 of the 40 distinct role names the
table can produce (`kick`, `snare`, `clap`, `ride`, `cowbell`, `cabasa`, `maracas`,
`claves`); the other 32 (`tom_low`, `tom_mid`, `tom_high`, `hihat_closed`, `hihat_open`,
`crash`, `china`, `ride_bell`, `tambourine`, `splash`, `vibraslap`, `bongo_hi/lo`,
`conga_mute/open/lo`, `timbale_hi/lo`, `agogo_hi/lo`, `whistle_short/long`,
`guiro_short/long`, `woodblock_hi/lo`, `cuica_mute/open`, `triangle_mute/open`,
`side_stick`, `hihat_pedal`) are absent, so those GM notes still resolve to `None` and
fall through to the noise channel.

This is not a logic bug (the code fix for #73/D-10 is confirmed correct) — it's a
residual data/asset gap the code fix cannot address on its own.

**Location:** `dpcm_sampler/drum_engine.py:8-56` (`DEFAULT_MIDI_DRUM_MAPPING`);
`dpcm_index.json` (shipped data)

## Evidence
```
$ python3 -c "
import json; d = json.load(open('dpcm_index.json')); names = set(d)
roles = [...40 DEFAULT_MIDI_DRUM_MAPPING values...]
print(sum(1 for r in roles if r in names), 'of', len(roles), 'present')
"
8 of 40 present
```

## Impact
On the shipped catalog, 80% of GM percussion notes still degrade to the noise fallback
rather than DPCM, even though the code path fix for #73 is verified correct. Not a logic
bug (the noise fallback is the documented, sane behavior for an unresolvable name), but it
limits the practical benefit of the GM-wide coverage fix to asset naming, not code.
Toms/hi-hats/cymbals/crash — the most audible non-kick/snare percussion — are all in the
missing set.

## Suggested Fix
Either rename/alias a subset of the shipped `.dmc` files to the
`DEFAULT_MIDI_DRUM_MAPPING` role names, or add an index-generation step that maps role
names to nearest-available samples by filename heuristics.

## Related
#200 (D-14) — the DPCM samples that *do* resolve are further broken by the id-ceiling
collision.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
