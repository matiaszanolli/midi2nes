# EXP-05: NSF exporter emits JSON-as-data and a play routine with wrong branch offsets
Severity: HIGH · Domain: exporters · Source: AUDIT_EXPORTERS_2026-06-29.md

(1) Channel data serialized as UTF-8 JSON string in the NSF binary (json.dumps) - not
6502/APU loadable. (2) _generate_play_routine branch offsets wrong (BEQ done -> offset 30
but RTS at 28; BNE loop -> offset 3 mid-instruction not loop at 14).
Location: exporter/exporter_nsf.py:124-132, :134-153.
NSF already removed from CLI (#79). Fix: implement real binary player OR mark NSF
explicitly unsupported (raise) and remove broken output. SIBLING CA65 serialization.
