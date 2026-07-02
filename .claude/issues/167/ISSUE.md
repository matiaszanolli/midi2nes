# NH-25: Direct-path pulse control bytes omit the length-counter halt flag the docs mandate

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

## Description
The documented engine strategy is "Halt Flags Always Set … when writing to `$4000`,
`$4004`, `$4008`, and `$400C`", so the hardware length counter can never cut a note the
60Hz engine is holding. The bytecode engine complies (`ora #$30`), but
`get_envelope_control_byte` builds `duty<<6 | 0x10 | vol` — constant volume yes, halt **no**
— and that byte is what direct-export mode writes to `$4000`/`$4004`. Masked today because
every new note reloads the length counter with index 1 (~2.1s via `ora #$08` on `$4003`)
and NH-20 caps notes at 4 frames. If durations are ever honored (NH-20's fix), any
direct-mode pulse note held past ~2.1s goes silent mid-note.

## Location
`nes/envelope_processor.py:123-126` (`envelope_bits = 0x10` — bit 5 never set), consumed as
the direct-export `$4000`/`$4004` byte (`exporter/exporter_ca65.py:198,463-464,534-535`).

## Evidence
Bitfield `DDlc.vvvv`: emitted byte has `l = 0`. Direct-mode sustain never rewrites `$4003`
(correctly, see NH-18), so the counter is not re-armed during a hold.

## Impact
None at HEAD; a time-bomb coupled to the NH-20 fix. Triangle and noise paths already set their halt bits (`0x80 |`, `$30 |`).

## Related
NH-20, NH-18, #107.

## Hardware ref
`docs/APU_LENGTH_COUNTER_REFERENCE.md` §2 (halt = bit 5 of `$4000`/`$4004`), §3 (halt =>
no decrement), §5 "Halt Flags Always Set"; `docs/APU_PULSE_REFERENCE.md` §2 (`DDlc.vvvv`).

## Suggested Fix
Set `0x30` (halt + constant volume) in `get_envelope_control_byte`, matching the bytecode engine and the doc strategy.

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
