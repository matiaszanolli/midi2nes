# MAP-2026-08-05-3: estimate_segment_sizes undercounts .byte string-literal lines by counting comma tokens instead of string length

**Severity:** LOW · **Domain:** mappers · **Source:** docs/audits/AUDIT_MAPPERS_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/390

## Description
`estimate_segment_sizes` counts `.byte` line bytes by splitting on `,` — correct for
numeric literals, wrong for `.byte "some string", $00`, which counts as one token instead
of its real character length. Undercounts the debug overlay's 7 string lines by ~140 bytes
combined (currently latent since #389/MAP-2026-08-05-2 means those lines aren't even seen
by the check yet); also undercounts mapper header `.byte "NES", $1A` lines.

## Location
`mappers/capacity.py:58-59`

## Impact
Heuristic-accuracy gap only; `ld65` remains the exact backstop. Severity should be
revisited once #389 is fixed (the debug overlay content becomes visible to this estimator).

## Suggested Fix
Quote-aware split: count actual string character length for quoted tokens instead of
treating each string literal as one token (and don't split on commas inside quotes).
