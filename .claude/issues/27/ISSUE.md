# NH-06: Pulse/Triangle timer not clamped to t >= 8; low notes silently mute

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #27

## Description
All timer clamps in pitch_table.py clamp only the upper 11-bit bound and the lower bound to 0. The pulse channel is silenced whenever `t < 8`. High MIDI notes produce timers below 8 and silently mute. The exporter masks (`pitch & 0xFF` / `(pitch>>8)&0x07`) but never enforces `>= 8`.

## Evidence
`timer = max(0, min(timer, 0x07FF))` at pitch_table.py:30 and :88. Exporter masks at exporter_ca65.py:165-166. `docs/APU_PULSE_REFERENCE.md` §7 requires clamping to >= 8.

## Impact
High notes on pulse/triangle go silent; wrong output on high-register melodies.

## Hardware ref
`docs/APU_PULSE_REFERENCE.md` §3, §5, §7; `docs/NES_APU_REFERENCE.md` §2.1.

## Related
NH-02, NH-03.

## Suggested Fix
Clamp note timers to `max(8, min(timer, 0x7FF))` in the table generators and re-assert at the exporter.
