# MAP-2026-07-05B-4: docs/MAPPER_MMC1_REFERENCE.md documents a Mode-2 DPCM-streaming design that was never implemented

GitHub: https://github.com/matiaszanolli/midi2nes/issues/284

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-05.md (MAP-2026-07-05B-4)

## Description
`docs/MAPPER_MMC1_REFERENCE.md` §4 ("Bank Layout Strategy (Mode 2 is Mandatory)") states `midi2nes` "**must** initialize the MMC1 to Mode 2" (engine fixed at `$8000-$BFFF`, DPCM samples bank-switched into `$C000-$FFFF`) specifically because DMC hardware can only fetch samples from `$C000-$FFFF`, and warns that using Mode 3 instead "would be strictly limited to a maximum of 16KB of DPCM samples... because that window could never be switched."

The shipped `MMC1Mapper.generate_init_code()` (`mappers/mmc1.py:108-133`) configures exactly the opposite: Mode 3 (`$0C`, fixed last bank at `$C000-$FFFF` holding engine/vectors, switchable `$8000-$BFFF` for note-table data). Per the two sibling findings filed alongside this one, the implementation doesn't even deliver the doc's stated fallback (a 16KB-capped DPCM budget) — it delivers zero working DPCM support for MMC1.

This is either aspirational documentation for a design superseded by the #255 bank-switching work (which solved a *different* problem — general frame-table capacity, not DPCM) without updating the doc, or the doc is the intended target architecture and the implementation is incomplete against it. Either way, a reader relying on this doc to verify MMC1's bank-switch correctness (as this audit's own protocol instructs) would be checking the implementation against a description that doesn't match.

## Impact
Doc-rot only — doesn't itself change ROM output — but actively misleading for future maintainers deciding how to fix the sibling DPCM findings, and for anyone auditing MMC1's bank-switching against "the reference doc."

## Related
Directly relevant to the two sibling MMC1 DPCM findings filed alongside this one — this doc's prescribed design would have prevented both, had it been implemented.

## Suggested Fix
Once the sibling DPCM findings are fixed (whichever direction is chosen), update this doc to describe the actual shipped design. If Mode 2 + `$C000` DPCM streaming is still the intended end state, mark the current Mode-3-only implementation as a known interim limitation in the doc rather than describing Mode 2 as already "mandatory" and implemented.

## Completeness Checks
- [ ] **DOC**: Doc updated to match whichever implementation direction is chosen for the sibling findings
