# PL-03: The fallback's "the ROM is INCOMPLETE" warning is false — event sampling cannot make the ROM incomplete, and the advice it gives makes ROMs bigger

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
When the sequential fallback samples events down to `DETECTOR_MAX_EVENTS` (1000), the
pipeline prints and re-prints at success: "the ROM is INCOMPLETE. Re-run with
--no-patterns for full fidelity." But sampled `events` feed only pattern detection, whose
output affects the ROM solely via `patterns` truthiness (serializer selection) — every
emitted byte derives from the full `frames` dict (confirmed in the macro path which
iterates `range(max_frame + 1)` over `frames`). The ROM contains the whole song either way.
The message is also inconsistent with the parallel path, which samples to 15000, printing
only an inline "lossy" note and no INCOMPLETE banner — two sampling events of the same kind
get opposite messaging.

## Location
`main.py:522-530` (`pattern_loss_warning` text), `main.py:661-662` ("INCOMPLETE OUTPUT"
success-banner line); ground truth `exporter/exporter_ca65.py:862-874`.

## Evidence
`main.py:525-528` (warning text) vs `exporter/exporter_ca65.py:873-874`
(`if not patterns: return self.export_direct_frames(...)` — the only read of pattern data)
and `:964-965` (frame loop over `frames`, not `events`).

## Impact
Users with large files hitting the fallback are told their ROM is broken when it is not,
and are directed to `--no-patterns` — which switches to the direct-frame serializer,
typically producing a much larger ROM (and closer to the MMC3 capacity gate) for zero
fidelity gain. Only the compression metrics are affected by sampling.

## Related
Closed #10 (introduced the warning), #100 (fixed its numbers), #4 (references are analysis-only — the fact that makes the claim false); PAT-02 (patterns audit, same defect, deduped here as canonical).

## Suggested Fix
Reword both messages to what is true: "pattern analysis was sampled (N->M events);
compression stats are approximate; ROM content is unaffected." Drop the `--no-patterns`
advice, and align the parallel path's sampling message with the fallback's.

## Completeness Checks
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
- [ ] **TESTS**: A regression test pins this specific fix
