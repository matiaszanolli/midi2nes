# NH-HW-2026-08-21-8: Arranger emits a hardcoded pseudo-linear-counter control: 0x81 on triangle frames that no consumer reads — dead data / latent trap

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/434
**Severity:** LOW
**Domain:** nes-hardware
**Source report:** docs/audits/AUDIT_NES_HARDWARE_2026-08-21.md
**Filed:** 2026-08-21

## Location
`arranger/pipeline_integration.py:319` (`'control': 0x81,  # Triangle linear counter`)

## Description
Both sinks ignore a triangle frame's `control` key: `export_direct_frames` derives `$4008` solely
from `volume`; `_build_song_bytecode` extracts duty bits from it, which the engine discards for
channel 2. So `0x81` is inert today — but looks like a meaningful linear-counter reload (same
latent-trap shape as the `volume * 7` reload retired under #364/NH-HW-04); a future consumer
honoring it would nearly silence every arranger triangle note.

## Impact
None at runtime today; maintainability/latent-trap only.

## Suggested Fix
Drop the `control` key from arranger triangle frames (match `process_all_tracks`' contract), or
set it to the engine's real on-value constant with a comment that consumers must ignore it.

## Related
#364/NH-HW-04.

## Dedup check
Searched fresh `gh issue list --state open` snapshot (6 open issues at filing time) and audit
history — no match found.
