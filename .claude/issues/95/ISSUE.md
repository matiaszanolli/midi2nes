# TEMPO-03: ticks_per_beat == 0 produces inf time instead of failing fast
Severity: MEDIUM · Domain: tempo · Source: AUDIT_TEMPO_2026-06-29.md
No guard against ticks_per_beat==0; calculate_time_ms divides by it -> inf. Fix: raise
ValueError in TempoMap.__init__ for ticks_per_beat<1 (covers 0 and negative). Related
TEMPO-01 (#93) — same boundary, fix together. NOTE: #93 already added this guard + test.
