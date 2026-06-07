# midi2nes Macro Engine Usage Guide

The `midi2nes` compiler now features a powerful 6502 Macro-Driven Synthesizer! This allows for incredibly small ROM sizes while supporting rich, authentic NES audio features like volume envelopes, pitch bends, and arpeggios.

Here is how you can take full advantage of these features using standard MIDI files.

## 1. Pitch Bends (Vibrato & Slides)

The engine supports fine-pitch tuning via the Pitch Bend wheel in your DAW or MIDI editor.

**How to use it:**
*   Simply use the **Pitch Bend** automation lane in your MIDI editor.
*   **Vibrato:** Draw rapid, shallow sine-wave pitch bend automation over a sustained note.
*   **Portamento (Slides):** Draw a smooth pitch bend curve between two notes. *(Note: The engine supports bending up to +/- 127 APU timer units from the base note. Extremely wide slides might require re-triggering the base note).*
*   **Kick Drum Drops:** For classic NES "pew" kicks, use a short, sharp downward pitch bend at the start of a Triangle or Pulse note.

*Under the hood:* The compiler automatically detects pitch variations on a single note, deduplicates them, and exports them as `.byte` arrays in a `macro_pitch` sequence, which the 6502 engine adds to the base APU timer every frame!

## 2. Arpeggios (Hardware Chords)

Because the NES only has 3 melodic channels, composers often use rapid arpeggios to simulate chords.

**How to use it:**
*   You can manually draw 60Hz (1/64th or 1/32nd note) arpeggios in your MIDI editor (e.g., C -> E -> G -> C rapidly).
*   *Alternatively*, if you use the `--arranger` flag (`python main.py --arranger song.mid`), the compiler's intelligent arranger will automatically detect overlapping polyphonic chords on a single channel and convert them into NES-compatible arpeggios!

*Under the hood:* The compiler calculates the semitone difference from the base note and exports it as a `macro_arp` sequence. The 6502 engine dynamically shifts the base note index before looking up the pitch, meaning the same Major triad arpeggio macro can be reused across different base notes, saving massive amounts of ROM space!

## 3. Volume Envelopes & Duty Cycle Sweeps

The engine completely bypasses the restrictive NES hardware envelopes in favor of custom software envelopes.

**How to use it:**
*   **Volume:** Use the MIDI **Velocity** or **Volume CC (CC7)** automation in your DAW. Drawing volume fades or sharp percussive decays will be perfectly translated.
*   **Duty Cycle (Timbre):** The exporter interprets the instrument/control parameters to adjust the Pulse width. 

*Under the hood:* The compiler optimizes these into `macro_vol` and `macro_duty` arrays. If you use the exact same fade-out shape on 50 different notes, the compiler only stores that shape in ROM exactly once!

## 4. DPCM Drum Samples

The DMC channel is now fully wired into the Macro Engine!

**How to use it:**
*   Ensure your drum samples are defined in `dpcm_index.json`.
*   Place MIDI notes corresponding to the sample IDs on your percussion track.
*   The compiler automatically bundles the `.dmc` files into the ROM (`.segment "DPCM"` mapped to `$C000`) and generates the address/length lookup tables.
*   You don't need to manually configure `$4012` offsets—the `CA65` assembler calculates the exact hardware requirements automatically.

---

## Command Line Examples

Compile your MIDI file directly to an MMC3 NES ROM, utilizing all macros automatically:
```bash
python main.py song.mid
```
Compile and enable the smart Arranger to auto-generate arpeggios from MIDI chords:
```bash
python main.py --arranger song.mid
```
Compile a Debug ROM to see the APU channels reacting to your macros in real-time on-screen:
```bash
python main.py --debug song.mid
```