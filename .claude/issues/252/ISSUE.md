ARR-NEW-2: Arpeggio never starts on the chord root — index advanced before first read (off-by-one)

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-05.md

## Description
In `_allocate_pulse`, the arp index is advanced *before* the current note is read: `if self.frame_count % self.arp_speed == 0: state.arp_index = (state.arp_index + 1) % len(...)`, then `current_note = state.arp_notes[state.arp_index]`. `frame_count` starts at 0 and is incremented at the **end** of `allocate_frame` (`:161`), so on the very first frame of an arpeggiated chord `0 % arp_speed == 0` is true and `arp_index` steps from 0 to 1 before the first read. The chord's root (index 0, the lowest sorted pitch) is therefore never the first note played and only appears after a full cycle wraps.

## Location
`arranger/voice_allocator.py:200-208`

## Evidence
Reproduced — chord `[60,64,67]` at `arp_speed=3`:
```
ARP first 7 notes on pulse1: [64, 64, 64, 67, 67, 67, 60]
```
The root (60) first sounds at frame 6, not frame 0; the arp runs 2nd→3rd→1st every cycle. `tests/test_arranger.py::test_chord_becomes_alternating_single_notes` asserts only that the *set* of tones is `{60,64,67}`, and `test_arpeggio_step_is_frame_aligned_at_arp_speed` checks only the step *cadence*, so neither catches the wrong starting phase.

## Impact
Every polyphonic chord routed to a pulse channel plays its arpeggio phase-shifted by one step, de-emphasizing the root on the attack. All pitches still cycle at the correct rate, so it is a musical-correctness defect, not data loss — MEDIUM.

## Suggested Fix
Read the current note before advancing, or gate the advance on `self.frame_count > 0` (so the root plays for the first step), or initialize `arp_index = -1`. Add a test asserting the first emitted arp note equals the lowest chord tone.

## Related
#91 (ARR-08, same `frame_count % arp_speed` expression), `docs/arpeggio.md`.

## Completeness Checks
- [ ] **TESTS**: A regression test asserts the first emitted arp note equals the lowest chord tone
- [ ] **DOC**: If behavior contradicted `docs/arpeggio.md`, the doc was corrected
