# EXP-11: FamiStudio exporter crashes on any frames dict carrying the dpcm_sample_map side table

**Severity:** HIGH · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-18.md
**Filed as:** #313

## Description
`generate_famistudio_txt` iterates every top-level key of `frames`, including the `dpcm_sample_map` side table `nes/emulator_core.py` attaches for any DPCM-using song. This produces a malformed pattern key `dpcm_sample_map_N` that crashes `channel, index = pattern_key.split('_')` with `ValueError: too many values to unpack`.

## Location
`exporter/exporter_famistudio.py:84-123` (root cause `:90`); crash at `:128`.

## Suggested Fix
Skip `dpcm_sample_map` at the top of the loop, mirroring `exporter_ca65.py:252-253`.

## Related
#82 (EXP-06), #200/D-14
