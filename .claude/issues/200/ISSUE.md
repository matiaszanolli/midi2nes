# D-14: sample_id byte ceiling (255) is far below the shipped index's real id range (0–1922) — all named drums alias to one sample

**Severity:** CRITICAL · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-03.md

## Description
`EnhancedDrumMapper.map_drums`/`_handle_pattern_event`/`_handle_layered_samples` all emit
`dpcm_events[...]["sample_id"] = sample_data['id']` — the *raw* `dpcm_index.json` id,
unbounded (0–1922 in the shipped index). `nes/emulator_core.py:209` then encodes this into
the single-byte frame `note` field as `min(255, sample_id + 1)`. Any `sample_id >= 254`
collapses to `note = 255`; the trigger routine's `sample_id = note - 1` therefore recovers
`sample_id = 254` for **every** original id ≥ 254, not just the true id-254 sample.
Downstream, `get_dpcm_sample_ids_from_frames` (`dpcm_sampler/generate_dpcm_index.py:105-117`)
reads frame `note` (already collapsed) to decide which samples to pack — so a song using
`kick` and `snare` (ids 1318, 1620) resolves `sample_ids = {254}`: the packer loads and
includes exactly **one** physical `.dmc` file, and both the kick and snare hits trigger
that same file at runtime. No stage detects or warns about the collision; the pack step
reports success (`loaded_samples > 0`) because a sample *did* load — just not the one
requested.

Root cause is distinct from, but a direct consequence of, the fix for the closed D-04/#67
— that fix correctly removed the old 0–95 MIDI-note ceiling and replaced it with a
"byte format" ceiling of 255, but never checked that ceiling against the real shipped
index's actual id range.

**Location:** `nes/emulator_core.py:209`; `exporter/exporter_ca65.py:984-986`;
`dpcm_sampler/enhanced_drum_mapper.py:294,362,434`; `dpcm_sampler/generate_dpcm_index.py:105-117`

## Evidence
```
$ python3 -c "
import json; d = json.load(open('dpcm_index.json'))
for name in ['kick','snare','ride','cowbell','clap','cabasa','maracas','claves']:
    print(name, d[name]['id'])
"
kick 1318
snare 1620
ride 1526
cowbell 1119
clap 1096
cabasa 1083
maracas 1437
claves 1102
# 1668 of 1923 shipped samples (87%) have id > 254.

$ python3 -c "
from nes.emulator_core import NESEmulatorCore
core = NESEmulatorCore()
tracks = {'dpcm': [{'frame': 0, 'sample_id': 1318, 'velocity': 100},   # kick
                    {'frame': 10, 'sample_id': 1620, 'velocity': 100}]} # snare
print(core.process_all_tracks(tracks)['dpcm'])
"
{0: {'note': 255, 'volume': 15}, 10: {'note': 255, 'volume': 15}}
```
`id 254` in the shipped `dpcm_index.json` is `{"id": 254, "filename": "22.dmc"}` — unrelated
to either kick or snare. `tests/test_audio_fixes.py:147-157` documents `sample_id=9999 →
note=255` as expected, but no test exercises two high ids colliding to the same decoded
sample.

## Impact
On the shipped `dpcm_index.json`, every song using more than one DPCM-mapped drum voice
(kick + snare minimum) has all distinct percussion silently replaced by a single arbitrary
sample, with the pipeline reporting success at every stage. Silent, total loss of intended
percussion content. Blast radius: every ROM built through the default pipeline (or
`export`) whose drums route to DPCM via the default/advanced mapping tables and the
shipped 1923-sample index.

## Suggested Fix
Either (a) widen the wire format so `sample_id` is not squeezed into a single byte shared
with the rest sentinel, or (b) remap referenced index ids to a dense 0..N range at pack
time (using the `sample_ids` set already computed by `get_dpcm_sample_ids_from_frames`).
At minimum, add a loud warning/error when `sample_id + 1 > 255` instead of silently
aliasing.

## Related
Regression-adjacent to closed D-04/#67; compounds with #201 (D-15).

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
