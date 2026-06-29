# D-13: DrumMapperConfig.from_file raises TypeError on a stray key; only some errors are caught

Issue: #76 — https://github.com/matiaszanolli/midi2nes/issues/76
Labels: bug, low, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`from_file` does `DrumPatternConfig(**config_data.get('pattern_detection', {}))` and `SampleManagerConfig(**config_data.get('sample_management', {}))`. A hand-edited config with a renamed/extra key raises an uncaught `TypeError` (dataclass got an unexpected keyword); only `FileNotFoundError` and `json.JSONDecodeError` are handled. The returned config is also not `validate()`-d inside `from_file` (validation only happens if the result is passed to `EnhancedDrumMapper.__init__`, which the default `map_drums_to_dpcm` never does — it constructs the default config).

## Location
`dpcm_sampler/enhanced_drum_mapper.py:163-191`

## Evidence
`enhanced_drum_mapper.py:169-174` (`**` splat), `:188-191` (only `FileNotFoundError` and `json.JSONDecodeError` excepts).

## Impact
A stray config key crashes with a raw `TypeError` traceback instead of a clear message. Low reach (no default-path caller uses `from_file`).

## Suggested Fix
Filter to known fields (or catch `TypeError`) and call `result.validate()` before returning.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (stray key → clear error)
