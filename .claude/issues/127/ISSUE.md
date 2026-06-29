# MAP-2: Bytecode export has no cap on bank count — a song needing >60 banks emits .segment BANK_60+ that MMC3 nes.cfg never defines

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-29.md

## Description
The macro-bytecode serializer rolls to a new bank whenever `bytes_in_current_bank + event_bytes + 4 > BANK_SIZE_LIMIT` (8192−256), emitting `.segment "BANK_{current_bank:02d}"` for the incremented `current_bank` (`exporter/exporter_ca65.py:1099-1108`). There is **no upper bound** on `current_bank`.

The MMC3 linker config defines `BANK_00`…`BANK_59` only (`mappers/mmc3.py:75-77`, `range(60)`). A song whose total sequence bytecode exceeds ~60×8 KB ≈ 480 KB produces `.segment "BANK_60"` (and beyond), which `ld65` rejects as an undefined segment. The MAP-1 capacity gate does not catch this either (it counts total bytes, not bank index). Likewise the per-instrument `CODE_8000` block and the `instrument_table`/macros can overflow the 8 KB `PRG_80` window independently of the 510 KB total.

## Evidence
```
exporter_ca65.py:1100-1107
    next_bank = current_bank + 1
    ... '.byte $FE, ${next_bank:02X}, ...'      # CMD_BANK_JUMP, unbounded
    lines.append(f'.segment "BANK_{current_bank:02d}"')
mmc3.py:75   for i in range(60):                # only BANK_00..BANK_59 defined
```

## Impact
Very large songs (or large DPCM-heavy projects) fail to link with a raw `ld65` "undefined segment BANK_60" rather than a clear "song too large for MMC3" message. Edge case (requires ~480 KB of sequence bytecode), hence MEDIUM, not CRITICAL — and the error is surfaced, not silent.

## Hardware ref
`docs/MAPPER_MMC3_REFERENCE.md` §1 (512 KB max PRG = 64×8 KB banks; the cfg reserves the top 4 for fixed windows, leaving 60 swappable).

## Suggested Fix
When `current_bank` would exceed 59, raise a clear exporter-level error ("sequence data exceeds MMC3 60-bank budget"); plumb the same bank/region check into `check_mapper_capacity` so it fails pre-link with a budget message.

## Related
MAP-1 (#sibling).

## Completeness Checks
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (CODE_8000 / PRG_80 instrument-table overflow, MAP-1 capacity gate)
- [ ] **TESTS**: A regression test pins this specific fix (>60-bank bytecode → clear exporter error)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected