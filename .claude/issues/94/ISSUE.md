# TEMPO-02: Valid out-of-range and large-jump tempo changes silently dropped in fast parser
Severity: HIGH · Domain: tempo · Source: AUDIT_TEMPO_2026-06-29.md

Fast parser overrides tempo range to 40-250 BPM and swallows TempoValidationError with bare
continue (parser_fast.py:39-48). Drops (a) tempos <40 or >250 BPM, (b) any change ratio>3.0
(tempo_map.py:344-353 max_tempo_change_ratio=3.0). Dropped -> previous/default tempo persists
-> wrong tempo silently. Fix: widen fast-parser TempoValidationConfig to full musical range,
relax/remove max_tempo_change_ratio for parsing (authoring heuristic, not hw limit), or at
minimum count+warn on drops. SIBLING parser.py.
