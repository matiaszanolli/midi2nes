# M-2: APU frame counter $4017 never initialized; $4015 not enabled at init

**Severity:** CRITICAL · **Domain:** nes-hardware/mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

audio_init wrote only $4011; $4017/$4015 never initialized on the patterns path.

## Status
Already fixed and closed by an earlier commit: audio_init now writes $4017=$40 and
$4015=$0F, and the no-patterns init_music does too.
