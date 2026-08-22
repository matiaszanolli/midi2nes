# NH-HW-2026-08-21-6: Jukebox auto-advance still starts some/all channels one NMI frame late at a song transition

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/433
**Severity:** MEDIUM
**Domain:** nes-hardware
**Source report:** docs/audits/AUDIT_NES_HARDWARE_2026-08-21.md
**Filed:** 2026-08-21

## Location
`nes/audio_engine.asm:733-762` (`@end_of_stream` `.ifdef JUKEBOX_BUILD` block)

## Description
Carry-over of `AUDIT_NES_HARDWARE_2026-08-07` finding NH-HW-2026-08-07-2, never filed as an
issue; code is byte-identical at HEAD. When the last-finishing channel `k` triggers the
all-5-`channel_ended` scan mid-loop, `audio_advance_song` reloads stream pointers but execution
falls through to `@silence` for channel `k`, never re-visiting channels ≤ `k` this frame. Channels
with index > `k` fetch the new song's first byte the same frame; channels ≤ `k` start one 60Hz
tick late.

## Impact
Multi-song jukebox ROMs only; a bounded, non-accumulating one-frame stagger/silence at each song
transition.

## Suggested Fix
After a successful advance, re-enter the frame's dispatch for the triggering channel (`jmp
@fetch_byte`), or restart `audio_update`'s channel loop from `x = 0` once when an advance occurred.

## Related
#30/F-13; originating report AUDIT_NES_HARDWARE_2026-08-07 NH-HW-2026-08-07-2.

## Dedup check
Searched fresh `gh issue list --state open` snapshot (6 open issues at filing time) and audit
history — no matching open issue (this specific finding was never filed despite being identified
2026-08-07).
