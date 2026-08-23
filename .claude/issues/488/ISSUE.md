# PIPE-2026-08-22-4: metadata['order'] collides after song remove + song add

**Filed:** https://github.com/matiaszanolli/midi2nes/issues/488
**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-22.md

## Description
`metadata['order']` can collide after a `song remove` + `song add` sequence: both add sites compute `order=len(self.songs)`, and `run_song_remove` deletes an entry without renumbering the rest.

## Location
`nes/song_bank.py` (`order=len(self.songs)` at both add sites), `main.py` (`run_song_remove` — no renumbering; `run_song_build`'s sort consumes `order`).

## Related
#30/F-13 (the song-bank feature this belongs to).

## Suggested Fix
Renumber remaining songs' `order` on `song remove`, or use a never-reused monotonic counter instead of `len(self.songs)`.
