# NH-29: noise_mode has no producer anywhere in the pipeline — noise mode-bit plumbing is dead-but-correct

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/204
**Severity:** LOW
**Domain:** nes-hardware
**Source:** docs/audits/AUDIT_NES-HARDWARE_2026-07-03.md
**Labels:** low, nes-hardware, bug

## Description
The engine and both exporter paths correctly thread a `noise_mode` bit from event → frame `control` (bit 6) → `$400E` bit 7 — the consumer side is fully wired and correct. But no writer exists anywhere in `tracker/`, `arranger/`, or `dpcm_sampler/`. Every noise hit in the current pipeline plays NES noise Mode 0; Mode 1 (metallic/short — more snare/hat-appropriate) is unreachable.

Adjacent to but distinct from NH-24 (#166, envelope_type/effects/arp) — this dimension specifically asked whether `noise_mode` is reachable end-to-end, and confirmed it is not.

## Location
`nes/emulator_core.py:166` (`mode = e.get('noise_mode', 0) & 1`, always defaults to 0); no producer found in `tracker/`, `arranger/`, or `dpcm_sampler/`.

## Impact
None wrong today — defaults to a valid, in-range mode bit (0). Missed opportunity for percussion timbre variety.

## Related
NH-24 (#166 — same "consumer ready, no producer" shape).

## Suggested Fix
Low priority — have the drum mapper set `noise_mode: 1` for metallic-appropriate GM percussion, or leave as documented future work alongside NH-24.

## Dedup
Checked against `/tmp/audit/issues_nes-hardware.json` (47 open issues) via `gh search issues` for "noise_mode" — no open match (one closed hit, #9/NH-01, unrelated to the missing producer).
