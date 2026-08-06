# DP-DPCM-07: _real_sample_size doesn't cache unresolvable (missing-file) lookups

**Severity:** LOW · **Domain:** dpcm · **Source:** docs/audits/AUDIT_DPCM_2026-08-06.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/413

## Description
`_real_sample_size` caches successfully-resolved sizes but not `None` results from either
early-return path (missing `filename` key, or `resolve_dpcm_sample_path` returning `None`).
A catalog sample whose backing `.dmc` file is missing re-runs the full candidate-path probe
on every occurrence in a song instead of once, contradicting the cache's own documented
"one `os.path.getsize` call per song" guarantee.

## Location
- `dpcm_sampler/enhanced_drum_mapper.py:227-250` (`_real_sample_size`)

## Impact
Performance/doc-accuracy gap only; the placeholder fallback still works correctly.

## Suggested Fix
Cache the miss too — store `None` in `self._sample_size_cache[sample_name]` on both
early-exit paths; `dict.__contains__` already distinguishes "cached miss" from "unseen."
