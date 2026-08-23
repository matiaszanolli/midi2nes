# EXP-2026-08-23-5: export_song_bank_bytecode's song_count guard misses a lazy iterable yielding more songs than declared

**Severity:** LOW · **Domain:** exporters
**Source:** AUDIT_EXPORTERS_2026-08-23.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/512

## Description
`zip(song_labels, songs)` stops at the shorter iterable. The `songs_consumed !=
song_count` check (added by `#505`/`#506`) catches a generator yielding fewer songs
than declared, but not more — extra songs are silently dropped with no error.

## Evidence
`exporter/exporter_ca65.py:1811-1830`: `songs_consumed` can equal `song_count` even
when `songs` had more items available, since `zip` stopped it there.

## Impact
No live caller triggers this (`main.py`'s sole call site always passes a matching
count). Latent API-contract gap only.

## Related
#505/#506 (introduced this asymmetry); #508, #509, #510, #511 (same audit).

## Suggested Fix
Iterate `songs` manually via `iter(songs)` instead of relying on `zip`'s early stop,
so a leftover (N+1)th item can be detected and raise the same mismatch error.
