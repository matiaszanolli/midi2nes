# NH-HW-2026-08-06-2: Misleading "Length counter halt" comment on a $4003/$4007/$400B length-load write

**Severity:** LOW · **Domain:** nes-hardware · **Source:** docs/audits/AUDIT_NES_HARDWARE_2026-08-06.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/407

## Description
`nes/audio_engine.asm:411`'s `ora #$08      ; Length counter halt` mislabels a $4003
length-*load* write (bit 3 of the 5-bit length-load field) as a halt-bit write. The real
halt bit lives in $4000/$4004/$4008/$400C, a different register entirely. Five structurally
identical `ora #$08` sites exist in the same file; only this one carries the wrong comment.
No functional effect — comment-only.

## Location
- `nes/audio_engine.asm:411`

## Impact
Maintainer confusion risk only; no behavior change.

## Suggested Fix
Reword to match the other 5 sites and `exporter/exporter_ca65.py`'s correct wording,
e.g. "length counter load (harmless: halted via $4000/$08=0x30 control byte)".
