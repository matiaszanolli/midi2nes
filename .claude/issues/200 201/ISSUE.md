# D-14: sample_id byte ceiling (255) is far below the shipped index's real id range (0–1922) — all named drums alias to one sample

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/200
**Severity:** CRITICAL
**Domain:** dpcm
**Source:** docs/audits/AUDIT_DPCM_2026-07-03.md
**Labels:** critical, dpcm, bug

## Description
`EnhancedDrumMapper.map_drums`/`_handle_pattern_event`/`_handle_layered_samples` all emit
`dpcm_events[...]["sample_id"] = sample_data['id']` — the *raw* `dpcm_index.json` id,
unbounded (0–1922 in the shipped index). `nes/emulator_core.py:209` then encodes this into
the single-byte frame `note` field as `min(255, sample_id + 1)`. Any `sample_id >= 254`
collapses to `note = 255`; the trigger routine's `sample_id = note - 1` therefore recovers
`sample_id = 254` for **every** original id ≥ 254, not just the true id-254 sample.
Downstream, `get_dpcm_sample_ids_from_frames` reads frame `note` (already collapsed) to
decide which samples to pack — so a song using `kick` and `snare` (ids 1318, 1620) resolves
`sample_ids = {254}`: the packer loads exactly **one** physical `.dmc` file, and both the
kick and snare hits trigger that same file at runtime. No stage detects or warns about the
collision.

Root cause is a direct consequence of the fix for the closed D-04/#67 — that fix correctly
removed the old 0–95 MIDI-note ceiling and replaced it with a "byte format" ceiling of 255,
but never checked that ceiling against the real shipped index's actual id range.

## Location
- `nes/emulator_core.py:209` (`"note": min(255, sample_id + 1)`)
- `exporter/exporter_ca65.py:984-986` (same clamp, direct/bytecode note-stream path)
- `dpcm_sampler/enhanced_drum_mapper.py:294,362,434` (`"sample_id": sample_data['id']`, the raw, unbounded index id)
- `dpcm_sampler/generate_dpcm_index.py:105-117` (`get_dpcm_sample_ids_from_frames`, sees only
  the already-collided `note` field)

## Evidence
```
kick 1318
snare 1620
# 1668 of 1923 shipped samples (87%) have id > 254.
```
Both kick (1318) and snare (1620) collapse to `note=255`, decoding back to `sample_id=254`
(an unrelated sample, "22.dmc") for both.

## Impact
Every song using more than one DPCM-mapped drum voice (kick + snare minimum) has all of its
distinct percussion silently replaced by a single arbitrary sample, with the pipeline
reporting success at every stage. Silent, total loss of intended percussion content.

## Related
Regression-adjacent to closed D-04/#67. Compounds with D-15 (filed alongside this issue).

## Suggested Fix
Either (a) widen the wire format so `sample_id` isn't squeezed into a single byte shared
with the rest sentinel, or (b) remap referenced index ids to a dense 0..N range at pack
time (the `sample_ids` set already computed by `get_dpcm_sample_ids_from_frames` — assign
each *referenced* sample a fresh 0-based id before this clamp is applied, so real catalogs
larger than 255 entries still work as long as a single song references ≤ 255 distinct
samples). At minimum, add a loud warning/error when `sample_id + 1 > 255` instead of
silently aliasing.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# D-15: DEFAULT_MIDI_DRUM_MAPPING's GM-wide coverage (#73) is code-complete but the shipped dpcm_index.json backs only 8 of 40 role names

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/201
**Severity:** MEDIUM
**Domain:** dpcm
**Source:** docs/audits/AUDIT_DPCM_2026-07-03.md
**Labels:** medium, dpcm, bug

## Description
`DEFAULT_MIDI_DRUM_MAPPING` now defines 47 generic role names across the full GM
percussion range (35–81), and `_resolve_dpcm_sample_name`'s fallback chain correctly
reaches it. However the *shipped* `dpcm_index.json` only contains 8 of the 40 distinct
role names the table can produce (`kick`, `snare`, `clap`, `ride`, `cowbell`, `cabasa`,
`maracas`, `claves`); the other 32 (toms, hi-hats, crash, china, tambourine, splash,
vibraslap, bongos, congas, timbales, agogos, whistles, guiros, woodblocks, cuica,
triangle, side_stick, hihat_pedal) are absent, so those GM notes resolve to `None` and
fall through to the noise channel.

This is not a logic bug (the code fix for #73/D-10 is confirmed correct) — it's a residual
data/asset gap the code fix cannot address on its own.

## Location
- `dpcm_sampler/drum_engine.py:8-56` (`DEFAULT_MIDI_DRUM_MAPPING`)
- `dpcm_index.json` (shipped data)

## Evidence
8 of 40 role names present in the shipped index.

## Impact
80% of GM percussion notes still degrade to the noise fallback rather than DPCM. Not a
logic bug — the noise fallback is the documented, sane behavior for an unresolvable name —
but the practical benefit of the GM-wide coverage fix is limited by asset naming.

## Related
D-14 (filed alongside this issue) — the DPCM samples that *do* resolve are further broken
by the id-ceiling collision.

## Suggested Fix
Either rename/alias a subset of the shipped `.dmc` files to the `DEFAULT_MIDI_DRUM_MAPPING`
role names, or add an index-generation step that maps role names to nearest-available
samples by filename heuristics.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
