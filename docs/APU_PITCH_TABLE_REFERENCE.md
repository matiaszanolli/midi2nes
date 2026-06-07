# NES APU Pitch & Period Table Reference

This document provides the standard lookup tables and mathematical formulas used to convert musical pitches (notes) into the 11-bit timer periods required by the NES APU Pulse and Triangle channels.

## 1. Overview

The NES APU uses "period" values (timer dividers) to set the pitch of a note. The timer value is inversely proportional to the frequency.

*   **Triangle vs. Pulse:** For a given 11-bit period value, the Pulse waves will sound **one octave higher** than the Triangle wave. The tables below assume the lowest note (Index 0) corresponds to the lowest key on a standard piano (A-1, 55.0 Hz) for the Triangle channel.

---

## 2. Full MIDI to Period Lookup Table (ca65 Assembly)

To save CPU cycles, the 6502 audio engine uses pre-calculated lookup tables rather than computing divisions at runtime. The 11-bit period is split into two parallel 8-bit tables (Low byte and High byte) for efficient indexed addressing.

These updated 128-byte tables map 1:1 with standard MIDI note indices (0-127). 
*Note: The first ~31 entries represent frequencies too low for the NES's 11-bit timer to reproduce (they would require a period > `$7FF`). These are safely padded with `$FF`/`$07` to allow for direct MIDI index lookups without offset math.*

```ca65
; NTSC period table mapping MIDI notes (0-127) to APU timer values
.export ntsc_period_low, ntsc_period_high
.segment "RODATA"

ntsc_period_low:
  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff
  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff
  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff
  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff
  .byte $ff, $f1, $7f, $13, $ad, $4d, $f3, $9d
  .byte $4c, $00, $b8, $74, $34, $f8, $bf, $89
  .byte $56, $26, $f9, $ce, $a6, $80, $5c, $3a
  .byte $1a, $fb, $df, $c4, $ab, $93, $7c, $67
  .byte $52, $3f, $2d, $1c, $0c, $fd, $ef, $e1
  .byte $d5, $c9, $bd, $b3, $a9, $9f, $96, $8e
  .byte $86, $7e, $77, $70, $6a, $64, $5e, $59
  .byte $54, $4f, $4b, $46, $42, $3f, $3b, $38
  .byte $34, $31, $2f, $2c, $29, $27, $25, $23
  .byte $21, $1f, $1d, $1b, $1a, $18, $17, $15
  .byte $14, $13, $12, $11, $10, $0f, $0e, $0d
  .byte $0c, $0c, $0b, $0a, $0a, $09, $08, $08

ntsc_period_high:
  .byte $07, $07, $07, $07, $07, $07, $07, $07
  .byte $07, $07, $07, $07, $07, $07, $07, $07
  .byte $07, $07, $07, $07, $07, $07, $07, $07
  .byte $07, $07, $07, $07, $07, $07, $07, $07
  .byte $07, $07, $07, $07, $06, $06, $05, $05
  .byte $05, $05, $04, $04, $04, $03, $03, $03
  .byte $03, $03, $02, $02, $02, $02, $02, $02
  .byte $02, $01, $01, $01, $01, $01, $01, $01
  .byte $01, $01, $01, $01, $01, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00

; PAL period table mapping MIDI notes (0-127) to APU timer values
.export pal_period_low, pal_period_high

pal_period_low:
  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff
  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff
  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff
  .byte $ff, $ff, $ff, $ff, $ff, $ff, $ff, $ff
  .byte $d1, $60, $f6, $92, $34, $db, $86, $37
  .byte $ec, $a5, $62, $23, $e8, $b0, $7b, $49
  .byte $19, $ed, $c3, $9b, $75, $52, $31, $11
  .byte $f3, $d7, $bd, $a4, $8c, $76, $61, $4d
  .byte $3a, $29, $18, $08, $f9, $eb, $de, $d1
  .byte $c6, $ba, $b0, $a6, $9d, $94, $8b, $84
  .byte $7c, $75, $6e, $68, $62, $5d, $57, $52
  .byte $4e, $49, $45, $41, $3e, $3a, $37, $34
  .byte $31, $2e, $2b, $29, $26, $24, $22, $20
  .byte $1e, $1d, $1b, $19, $18, $16, $15, $14
  .byte $13, $12, $11, $10, $0f, $0e, $0d, $0c
  .byte $0b, $0b, $0a, $09, $09, $08, $08, $07

pal_period_high:
  .byte $07, $07, $07, $07, $07, $07, $07, $07
  .byte $07, $07, $07, $07, $07, $07, $07, $07
  .byte $07, $07, $07, $07, $07, $07, $07, $07
  .byte $07, $07, $07, $07, $07, $07, $07, $07
  .byte $07, $07, $06, $06, $06, $05, $05, $05
  .byte $04, $04, $04, $04, $03, $03, $03, $03
  .byte $03, $02, $02, $02, $02, $02, $02, $02
  .byte $01, $01, $01, $01, $01, $01, $01, $01
  .byte $01, $01, $01, $01, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
  .byte $00, $00, $00, $00, $00, $00, $00, $00
```

---

## 3. Table Generation Mathematics

If dynamic generation of these tables is needed (e.g., for PAL compatibility or custom tuning systems), the mathematical bases are as follows:

*   **NTSC Base:** `39375000.0 / (22 * 16 * lowestFreq)` (Derived from the NTSC CPU Clock: ~1.789773 MHz)
*   **PAL Base:** `266017125.0 / (10 * 16 * 16 * lowestFreq)` (Derived from the PAL CPU Clock: ~1.662607 MHz)

### Python Generator Implementation
```python
lowestFreq = 55.0  # A-1
ntscOctaveBase = 39375000.0 / (22 * 16 * lowestFreq)
palOctaveBase = 266017125.0 / (10 * 16 * 16 * lowestFreq)
maxNote = 80

def calculate_periods(pal=False):
    semitone = 2.0 ** (1.0 / 12.0)
    octaveBase = palOctaveBase if pal else ntscOctaveBase
    
    # Calculate relative frequencies for 80 notes
    relFreqs = [(1 << (i // 12)) * semitone**(i % 12) for i in range(maxNote)]
    
    # Invert and subtract 1 for the 11-bit APU timer value
    periods = [int(round(octaveBase / freq)) - 1 for freq in relFreqs]
    return periods
```

---

## 4. Engine Implementation Notes (midi2nes)

*   **Transition from Python to 6502:** Currently, `nes/pitch_table.py` handles pitch conversion during the compilation phase, outputting exact register writes to the frames. In our new Macro-Driven Engine, we will embed these lookup tables directly into the NES ROM (`music.asm`).
*   **Bytecode Impact:** By embedding the table, the Python compiler only needs to export simple 1-byte Note Identifiers (e.g., $00-$5F). This dramatically shrinks the ROM footprint of the bytecode sequences.
*   **Macro Modulation:** During the NMI, the 6502 Sequencer will read the Note Identifier, look up the base 11-bit timer value using `periodTableLo` and `periodTableHi`, and *then* the Synthesizer module will apply Pitch Macros (vibrato, portamento) to that base value before writing to the Shadow APU registers.
*   **ROM Size:** The tables cost a negligible 160 bytes of PRG-ROM (80 bytes Lo, 80 bytes Hi).