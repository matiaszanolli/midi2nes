# ARR-12: _analyze_drum_track writes a dead analysis.notes attribute with a stale description

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/207
**Source finding:** NEW-3 in `docs/audits/AUDIT_ARRANGER_2026-07-03.md`
**Filed:** 2026-07-03

**Severity:** LOW · **Domain:** arranger

## Description
`_analyze_drum_track` (`arranger/role_analyzer.py:186-193`) sets
`analysis.notes = "Uses DPCM for kicks/snares"` when `n.pitch in [35, 36]` (kicks) or
`n.pitch in [38, 40]` (snares) is present. `TrackAnalysis` declares no `notes` field (only 19
fields, none named `notes`), so this creates an ad-hoc instance attribute nothing reads (only
`ArrangementPlan.notes`, a distinct field, is ever read). The string is also stale:
`GM_DRUM_MAP[40]` ("Electric Snare") routes to `NESChannel.NOISE`, not DPCM (per #87's allocator
fix), so grouping 40 with DPCM-routed 35/36/38 is wrong even if read.

## Evidence
`arranger/role_analyzer.py:186-193`; `dataclasses.fields(TrackAnalysis)` has no `notes` entry;
only reader of any `.notes` attribute in `arranger/` is `plan.notes`.

## Impact
None at runtime (dead write). Misleading to a maintainer expecting it to surface in
`print_analysis` (it does not).

## Related
#87 (the allocator-side fix this comment/logic never caught up with).

## Suggested Fix
Remove the dead assignment, or add a proper `notes: str = ""` field to `TrackAnalysis` and have
`print_analysis` surface it, using `get_drum_mapping` per-note.

## Dedup check
Searched open issues in `/tmp/audit/issues_arranger.json` — no match found. Filed as NEW.
