# #300 — DP-05: DMC layering emits duplicate primary sample; misleading 'note dropped' warning

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-06.md · **Status:** NEW

## Description
For a note in `ADVANCED_MIDI_DRUM_MAPPING` whose entry has a `layers` list (only 36/kick and 38/snare), `map_drums` appends the primary DPCM event and then calls `_handle_layered_samples` (`dpcm_sampler/enhanced_drum_mapper.py:304-311`, `:435-451`), which appends a **second** event on the same frame for every layer name present in the index. The layer lists are `["kick", "kick_sub"]` and `["snare", "snare_rattle"]` — the first element is the *primary itself* (guaranteeing a duplicate), the second (`kick_sub`/`snare_rattle`) is absent from the shipped index (skipped). Net effect on the shipped catalog: a kick/snare hit always emits two identical DPCM events on one frame.

Downstream, `_collapse_same_frame_events` (`nes/emulator_core.py:212`) collapses them to one and prints `"Warning: N note(s) on dpcm dropped — multiple notes quantized to the same 60Hz frame …"` — a false alarm, since nothing musical was lost. Layering is physically impossible on the DMC anyway: it is a single monophonic channel (`docs/APU_DMC_REFERENCE.md` §1).

## Evidence
```python
events = {'drums':[{'frame':0,'note':36,'velocity':100}]}   # kick
dpcm, noise = EnhancedDrumMapper('dpcm_index.json').map_drums(events)
# dpcm == [{'frame':0,'sample_id':1318,...}, {'frame':0,'sample_id':1318,...}]
#   -> two identical events; process_all_tracks collapses to one and warns "1 note(s) on dpcm dropped".
```

## Impact
No audible corruption (the collapse keeps one correct sample), but: (a) a spurious "note dropped" warning misleads users into thinking polyphony was lost; (b) wasted allocation/accounting work in the sample manager; (c) the layering feature is inert — it can only duplicate the primary or reference nonexistent samples, and the DMC cannot layer regardless.

## Suggested Fix
Remove `_handle_layered_samples` and the `layers` lists (the DMC can't layer), or — if a "layer" is meant as an alternate/fallback sample — dedupe against the primary and never emit two DPCM events on one frame so the collapse warning stays truthful.

## Completeness Checks
- [ ] **SIBLING**: same-frame collapse warning (`nes/emulator_core.py:43-45`) no longer fires on self-inflicted duplicates
- [ ] **TESTS**: a test asserts a single kick/snare hit yields exactly one DPCM event
- [ ] **DOC**: `docs/APU_DMC_REFERENCE.md` §1 (DMC is monophonic — no layering)
