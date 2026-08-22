# EXP-2026-08-21-8: fetch_sequence_byte comment claims $8000-$9FFF window; code maps sequence bank via R7 into $A000-$BFFF

GitHub: https://github.com/matiaszanolli/midi2nes/issues/443

**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-08-21.md

## Description
The routine's header comment describes the wrong 8KB window. The code is correct (and the audit's `--dbgfile` verification confirms sequence labels link at `$C000`-based `BANK_NN` addresses that the `& $1F | $A0` translation maps into `$A000-$BFFF`), but the comment invites exactly the kind of misread that produced past bank-window bugs (#388-class), and contradicts the correct "fixed `$8000` bank" comments 40 lines away in the same generated file.

## Location
`nes/project_builder.py:171` ("Swaps the sequence bank into $8000-$9FFF, reads 1 byte") vs `:176-187` (`lda #$47` selects R7; pointer high byte `and #$1F / ora #$A0` — the `$A000` window)

## Spec ref
`docs/MAPPER_MMC3_REFERENCE.md` (R7 maps `$A000-$BFFF` in both PRG modes)

## Impact
None at runtime; maintainer-facing only.

## Suggested Fix
s/$8000-$9FFF/$A000-$BFFF (R7)/ in the template comment.

## Completeness Checks
- [ ] **DOC**: Comment corrected to match the actual R7/$A000-$BFFF window, consistent with the other "fixed $8000 bank" comments in the same generated file
