# Pattern Detection & Compression Audit — 2026-07-18

## Summary

- **Findings by severity**: CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 1 (total 1)
- **All findings are already tracked** — no NEW defects. The single LOW is an existing
  open test-coverage gap (#311).
- **Headline round-trip result: LOSSLESS CONFIRMED.** Both compression paths were
  actually round-tripped on synthetic samples with known repeats and diffed:
  - **Pattern-dedup path** (`EnhancedPatternDetector` → `PatternCompressor`): every stored
    `references` position was verified to point at a window byte-identical to the pattern's
    stored `events`. `positions` is exact-only (PAT-01/#168 holds); no variation position
    leaks into `references`.
  - **RLE/delta path** (`CompressionEngine.compress_pattern` ↔ `decompress_pattern`): a
    mixed pattern exercising an RLE run, a delta chain, and a raw event with an extra key
    round-tripped exactly. The zero-diff-key case (a numeric key constant across a delta
    block, so omitted from the delta) was specifically verified to be **preserved**, not reset.
- **Highest-leverage actions** (all confirmations, not fixes):
  1. Land a test for the exact-window invariant (#311 / PAT-10) so the PAT-01 fix can't
     silently regress — it is the only pattern invariant verified in code but unpinned by tests.
  2. Keep the exporter contract intact: `export_tables_with_patterns` must continue to
     ignore `references` (verified — the arg appears only in the signature/docstring, #4).
  3. Keep `_collect_length_candidates`'s docstring owning the parallel/sequential
     non-equivalence caveat (PAT-05/#171) — do not let it regress to an equivalence claim.

### What was verified clean (evidence)

| Check | Dimension | Result |
|-------|-----------|--------|
| Pattern-dedup compress→reference round-trip, frame-by-frame diff | 1 | Lossless; all refs exact |
| RLE + delta + raw round-trip incl. zero-diff-key preservation | 1 | `decompressed == original` |
| Both producers + `--no-patterns` stub emit identical 7-key `stats` + 4-key envelope | 2 | Unified (#104/#258/#172 hold) |
| `variations` inner shape identical across paths (`{variation_count, exact_match_count, transposition_range, volume_range}`) | 2 | Unified; parallel neutral (0,0) |
| `len(compressed['events']) == length`; `references` not consumed by exporter | 3 | Holds (#4) |
| `coverage_ratio` distinct from dedup ratio; ≤ 100%; measured post-sampling | 4 | 84.6% / 100% on samples; pinned by tests |
| `_find_pattern_matches` self-similar run (12×, len 4 → `[0,4,8]`) | 8 | No self-overlap (PAT-04/#170 holds) |
| `_hash_pattern` returns raw `((note,volume),…)` tuple, not `hash()` | 8 | Exact key (PAT-07/#173 holds) |
| Serial fallback returns bare patterns dict, re-wrapped by caller | 5 | Correct |
| Worker payload (`initargs`) picklable; no per-chunk sequence copies; no shared mutation | 6 | Holds (#114) |
| Loop `end > start` guaranteed; tempo-key format matches read-back | 9 | Holds |

## Findings

### PAT-10: Exact-only round-trip invariant is verified in code but unpinned by any test
- **Severity**: LOW
- **Dimension**: 1 (Round-Trip Integrity)
- **Location**: `tests/test_pattern_integration.py:120-137`
- **Status**: Existing: #311
- **Description**: The critical exact-only invariant — every persisted `references`/`positions`
  entry points at a sequence window byte-identical to the pattern's stored `events` — currently
  holds in code (PAT-01/#168 made `positions = sorted(set(exact_matches))`, and my live
  round-trip confirmed it). But `test_pattern_positions_format` only asserts each position
  `isinstance(pos, int)`; no test reconstructs the referenced window and compares it to the
  pattern's `events`. A future change that re-admits variation positions into `positions`
  (as the pre-#168 code did) would reintroduce a lossy-where-claimed-lossless regression that
  the suite would not catch.
- **Evidence**: `tests/test_pattern_integration.py:132-137` asserts only `assertIsInstance(pos, int)`.
  My round-trip harness reconstructed `seqtuples[pos:pos+length]` for every reference and confirmed
  equality with `pattern_info['events']` — no equivalent assertion exists in the suite.
- **Impact**: Defense-in-depth gap on a CRITICAL invariant. No current mis-behavior; risk is a
  silent future regression to lossy compression on the pattern-dedup path.
- **Related**: #168 (PAT-01, closed — the fix this would pin), #4 (references analysis-only).
- **Suggested Fix**: Add a test that runs `EnhancedPatternDetector.detect_patterns` on events
  with known repeats and asserts, for every `pid` and every `pos` in `references[pid]`, that the
  reconstructed window equals `patterns[pid]['events']`.

## Notes on related open items (already tracked, not re-filed)
- **#302 (EXP-09)** — the RLE/delta `CompressionEngine` is dead code (no live pipeline consumer).
  It still round-trips losslessly and is well covered frame-by-frame by
  `tests/test_compression.py` / `tests/test_compression_integration.py`; no correctness issue.
- **#262 (PERF-11)** / **#115 (PERF-04)** — pattern-detection benchmark length mismatch and
  event-copy memory footprint; performance-domain, out of scope here.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-07-18.md
```
