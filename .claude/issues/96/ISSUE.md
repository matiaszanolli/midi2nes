# TEMPO-04: Two notes that round to the same frame collapse — the first is lost

Issue: #96

**Severity:** MEDIUM · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-06-29.md

## Description
At very fast tempo (or fine sequencing), two distinct note-on ticks can `round()` to the **same** 60Hz frame. In `compile_channel_to_frames` the truncation guard requires `next_event['frame'] > start_frame` (`nes/emulator_core.py:39`), so a same-frame successor does not shorten the prior note; instead both notes write the same `frames[f]` key (`:54`, last write wins) and the **second silently overwrites the first** for every shared frame. The first note is dropped entirely.

## Location
`nes/emulator_core.py:32-41` (`end_frame = start_frame + sustain_frames`; truncation only when `next_event['frame'] > start_frame`) and `:54`/`:48-60`; root quantization at `tracker/tempo_map.py:144-147`.

## Evidence
```
compile_channel_to_frames([{'frame':10,'note':60,'volume':100},
                           {'frame':10,'note':67,'volume':100}], 'pulse')
-> {10:67, 11:67, 12:67, 13:67}   # note 60 gone
```

## Impact
At high tempo / dense passages a note is silently lost on a channel (data loss, but bounded — inherent to 60Hz quantization, workaround via slower tempo / arranger arpeggiation). MEDIUM. The same overwrite happens for any two same-frame events regardless of tempo; tempo just makes it reachable from legal MIDI.

## Related
Inherent to the 60 FPS model (`docs/APU_FRAME_COUNTER_REFERENCE.md`); NH-08 (#34) is a different emulator_core issue (pulse volume), not this collapse.

## Suggested Fix
When two note-ons land on the same frame on one channel, either keep the higher-priority/last note deliberately (documented) or nudge the second to `start_frame+1`; at minimum count collapsed notes so the loss is visible.

## Completeness Checks
- [ ] **CHANNEL**: Same collapse handling applies across pulse/triangle/noise branches in `compile_channel_to_frames`
- [ ] **SIBLING**: Same overwrite checked in the arranger / other frame-build paths
- [ ] **TESTS**: A regression test pins same-frame note retention/visibility
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
