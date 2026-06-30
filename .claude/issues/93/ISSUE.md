# TEMPO-01: SMPTE / negative ticks_per_beat produces negative frame indices
Severity: HIGH · Domain: tempo · Source: AUDIT_TEMPO_2026-06-29.md

parse_midi_to_frames passes ticks_per_beat=mid.ticks_per_beat to EnhancedTempoMap with
no validation (parser_fast.py:24-29). SMPTE-division MIDI (division bit 15 set) -> mido
returns ticks_per_beat NEGATIVE. calculate_time_ms (tempo_map.py:129) us_per_tick<0 ->
negative time -> get_frame_for_tick (:144-147) negative frame indices -> events at
negative keys, corrupt song. No error.
Fix: check mid.ticks_per_beat > 0 after open (raise clear error or convert SMPTE to PPQ);
assert ticks_per_beat >= 1 in TempoMap.__init__. SIBLING parser.py.
