# TD-24: Two dead local variables in dpcm_sampler/enhanced_drum_mapper.py

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-07-18.md
**Filed as:** #320

## Description
pyflakes flags pattern_instances (line 247) and velocity_ratio (line 359) as assigned but never used.

## Location
`dpcm_sampler/enhanced_drum_mapper.py:247,359`

## Suggested Fix
Delete both dead assignments, or finish the intended functionality.

## Related
Distinct from EXP-12 (#314)/DP-06
