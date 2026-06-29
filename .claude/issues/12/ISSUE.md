# NH-02: Triangle channel uses the pulse timer formula → every triangle note an octave low

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

get_channel_pitch(note,'triangle') returns note_table[note] built with the pulse formula
fCPU/(16*freq)-1. Triangle hardware uses f=fCPU/(32*(t+1)), so the same timer sounds an
octave lower. A4 pulse timer=253 → triangle plays ~220Hz (A3). Correct triangle A4 timer=126.

## Suggested Fix
Generate a distinct triangle table using /32 and select by channel in get_channel_pitch.
Reconcile exporter base timer + runtime engine so bytecode mode is also correct.
