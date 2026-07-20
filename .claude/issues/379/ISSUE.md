# PIPE-2026-07-19-3: Two export call sites pass divergent references shapes (latent, currently inert)

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-19.md

## Description
`run_full_pipeline` passes a bare empty dict `{}` for the `references` argument regardless of what pattern detection produced, while the step-by-step `run_export` passes the detector's native `{'pattern_id': [positions]}` shape through unmodified. Today this is completely inert: `export_tables_with_patterns` documents that `references` is **not consumed** (`exporter/exporter_ca65.py:965-973`, F-01/#4, confirmed intentional per CLAUDE.md). So there is no live mismatch. The risk is purely forward-looking.

## Evidence
- `main.py:1020-1027` — `run_full_pipeline` passes literal `{}` (line ~1023) as the `references` arg.
- `main.py:616-623` — `run_export` passes `pattern_data['references']` (the detector-native shape).
- `exporter/exporter_ca65.py:965-973` — docstring states the `references` argument is **not consumed**; retained for call-site compatibility.

## Impact
None currently. If `references` is ever wired up to affect output bytes, the two entry points would diverge (default path would have no references data; step-by-step would), breaking the "same ROM from both paths" guarantee. Flagged per the pipeline audit skill's explicit forward-looking request.

## Related
F-01/#4 (references intentionally unused).

## Suggested Fix
If/when `references` becomes load-bearing, unify both call sites on one shape (or have both derive it from `pattern_result`). No action needed while it stays inert; a comment at `main.py:1023` already notes the empty-dict choice.

## Completeness Checks
- [ ] **CONTRACT**: If `references` is wired up, both entry points feed the exporter the same shape
- [ ] **SIBLING**: Both export call sites (`run_full_pipeline` and `run_export`) unified on one `references` source
- [ ] **ROUNDTRIP**: If `references` becomes load-bearing, decompressed playback == original from both paths
- [ ] **TESTS**: A regression test pins parity of the `references` arg across both entry points
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
