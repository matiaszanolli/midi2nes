# #92 — ARR-09: docs/arpeggio.md documents down_up and random patterns that the code does not implement

**Severity:** LOW · **Domain:** documentation · **Source:** AUDIT_ARRANGER_2026-06-29.md

## Description
`docs/arpeggio.md` describes five patterns: `up`, `down`, `up_down`, `down_up`, `random`. The `ArpStyle` enum has only `UP`/`DOWN`/`UP_DOWN`/`RANDOM`, and `_order_arp_notes` implements only UP/DOWN/UP_DOWN — `RANDOM` has no branch (falls through the `else` to plain sorted order) and `down_up` has no enum member at all. Additionally, `arrange_for_nes` never exposes `arp_style` (default `ArpStyle.UP`), so on the live path only the UP pattern is reachable regardless of the doc.

## Location
- `docs/arpeggio.md` (`down_up`, `random` sections)
- `arranger/voice_allocator.py:43-48` (`ArpStyle`) and `:213-225` (`_order_arp_notes`)

## Evidence
`voice_allocator.py:215-225` (`else: return pitches` covers RANDOM); `docs/arpeggio.md` "#### down_up Pattern" / "#### random Pattern".

## Impact
Doc-rot; a reader expecting `random`/`down_up` gets plain UP order. No runtime break. LOW (`docs/*.md` contradicts code).

## Related
ARR-06.

## Suggested Fix
Either implement `down_up`/`random` (a `random` branch would need a seeded RNG to preserve determinism — see Dimension 8) or trim `docs/arpeggio.md` to the three implemented patterns and note that the live path only uses UP.

## Completeness Checks
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
- [ ] **TESTS**: A regression test pins this specific fix
