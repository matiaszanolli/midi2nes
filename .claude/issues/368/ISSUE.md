# DP-DPCM-06: drum_engine.py ships production-dead helpers, one with a latent noise-contract bug

**Issue:** #368
**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-19.md
**Labels:** low, dpcm, tech-debt, enhancement

**Dimension:** 1 (drum mapping) / tech-debt

**Location:**
- `dpcm_sampler/drum_engine.py:109-143` (`optimize_dpcm_samples`)
- `dpcm_sampler/drum_engine.py:146-166` (`DrumPatternAnalyzer`)

## Description
Both `optimize_dpcm_samples` and `DrumPatternAnalyzer` are imported only by tests (`tests/test_drum_mapping.py`; no production caller). `DrumPatternAnalyzer`'s `detect_patterns`/`detect_groove`/`optimize_mapping` are empty bodies (implicit `return None`), and `analyze_drum_track` feeds those `None`s forward. `optimize_dpcm_samples` builds its noise fallback with no `note` key, contradicting the noise-event contract the live `map_drums` path honors (#195/NH-26). Inert today only because nothing wires it in.

## Evidence
`drum_engine.py:138-141` appends `{"frame":..., "velocity":...}` with no `note` key. `DrumPatternAnalyzer` methods (157-167) have empty/comment bodies returning `None`.

## Impact
Dead surface area and drift risk; if re-wired the missing `note` key becomes a real KeyError / silent mis-pitch on the noise channel.

## Related
#195/NH-26, #331/#302

## Suggested Fix
Delete both (and their tests) if unused, or finish `DrumPatternAnalyzer` and add the `note` key to the fallback.

## Status as filed: NEW / CONFIRMED
