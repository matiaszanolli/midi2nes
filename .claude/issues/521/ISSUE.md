**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-08-24.md

## Description
#481's same-pitch-retrigger fix (`nes/emulator_core.py:125-128`) intentionally borrows one frame from the front of a genuine same-pitch retrigger to force an explicit rest (`note=0`) between the two attacks, by shifting the render loop's start (`render_start_frame = start_frame + 1`). But the `frame_offset` used inside that loop to drive envelope curves is still computed against the un-borrowed `start_frame`:

```python
# nes/emulator_core.py:131-148
pitch = self.midi_to_nes_pitch(event['note'], channel_type)
envelope_type = event.get('envelope_type', 'default')
for f in range(render_start_frame, end_frame):
    frame_offset = f - start_frame   # starts at 1, not 0, when render_start_frame == start_frame + 1
```

So `frame_offset` starts at `1`, never `0`, for exactly the notes this fix targets — the envelope curve begins one frame into its own attack ramp instead of at the ramp's actual start.

## Impact
None under current production behavior: `envelope_type` is always `"default"` (flat `attack=0, decay=0, sustain=15, release=0`, #166) — no envelope curve currently reads `frame_offset` in a way that produces audible output differences. The moment any future envelope producer sets a real `envelope_type` (the "piano"/"pad"/"pluck"/"percussion" catalog `nes/envelope_processor.py` already defines but nothing wires up), every retriggered note that borrowed a frame under #481 would silently skip the first frame of its attack transient — small, silent truncation specifically correlated with the repeated-note material #481 was written to fix.

## Related
#481/NH-HW-2026-08-22-1 (the fix this narrows), #166/NH-24 (why this is inert today).

## Suggested Fix
When `render_start_frame != start_frame`, either compute `frame_offset = f - render_start_frame` (re-basing the envelope clock to the note's actually-rendered first frame) or explicitly pass a synthetic `frame_offset` of `0` for the loop's first iteration. Cheapest fix: rebase to `render_start_frame` — one line, no change to #481's rest-boundary behavior.

## Completeness Checks
- [ ] **CHANNEL**: Confirm the rebase applies correctly to both pulse channels (the only ones currently reading `envelope_type`/`frame_offset` via `get_envelope_control_byte`)
- [ ] **TESTS**: A regression test should pin `frame_offset == 0` on the first rendered frame of a retriggered note once a non-default `envelope_type` producer exists (or as a unit test directly on the loop's frame_offset computation)
- [ ] **DOC**: None needed — this is inert scaffolding per #166, no doc currently describes the shipped behavior
