# TEMPO-04: Two notes that round to the same frame collapse — the first is lost
Severity: MEDIUM · Domain: tempo · Source: AUDIT_TEMPO_2026-06-29.md
compile_channel_to_frames: truncation guard requires next_event['frame']>start_frame, so a
same-frame successor doesn't shorten prior note; both write same frames[f] (last wins),
second silently overwrites first. First note dropped.
Location: nes/emulator_core.py:32-41, :54, :48-60; root quant tempo_map.py:144-147.
Fix: nudge second to start_frame+1, OR keep-last deliberately + COUNT collapsed notes for
visibility. CHANNEL across pulse/triangle/noise; SIBLING arranger frame-build.
