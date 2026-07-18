# TEMPO-14: EnhancedTempoMap.__init__ divides by initial_tempo before any zero/negative guard

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-18.md
**Filed as:** #317

## Description
`initial_bpm = 60_000_000 / initial_tempo` at tracker/tempo_map.py:235 runs before any guard, so initial_tempo=0 raises raw ZeroDivisionError instead of TempoValidationError. Same failure class as fixed #208/#209 but a distinct, unguarded code path (constructor vs add_tempo_change).

## Location
`tracker/tempo_map.py:228-245`

## Suggested Fix
Add `if initial_tempo <= 0: raise TempoValidationError(...)` before computing initial_bpm.

## Related
#208, #209 (closed, same class, different code path)
