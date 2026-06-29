# P-01: detect-patterns --config is declared but silently ignored

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-29.md

## Description
`p_patterns.add_argument('--config', help='Path to pattern detection configuration')` (`main.py:699`) declares a config flag, but `run_detect_patterns` (`main.py:273-314`) never reads `args.config` — it hardcodes `EnhancedTempoMap(initial_tempo=500000)` and the module-level `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`. A user passing `--config my.yaml` gets the defaults with no error. This is the same class of defect as the closed #13 (`map --config`), which was fixed for `map` but not for `detect-patterns`.

## Evidence
`grep "args.config" main.py` returns only `run_config_validate` (`main.py:877`); the `detect-patterns` handler body (`main.py:273-314`) contains no `config` reference.

## Impact
Misleading CLI — the user believes pattern-detection bounds/tempo are configurable per-run but they are silently ignored, yielding a different (default) compression than requested. No ROM corruption; metrics/compression only.

## Related
Closed #13 (the `map --config` sibling). New regression-class sibling. Disjoint from the unrelated patterns-audit issue #100 (also titled "P-01").

## Suggested Fix
Either wire `--config` into `ConfigManager` to source `min_length`/`max_length`/tempo, or drop the flag (as #13 did for `map --config`).

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (`song add --config`, `map --config`)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
