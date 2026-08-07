# #376 — PERF-A-06: Fresh tempo map rebuilt at each detect site + events↔frames round-trip; parse-time tempo never threaded forward

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-19.md

## Description
Two residual redundancies remain after #119 removed the expensive per-pattern tempo analysis: (a) each detect site constructs a fresh `EnhancedTempoMap(initial_tempo=500000)` defaulting to `ticks_per_beat=480` rather than the source file's resolution, because the parse stage discards its tempo map (`parse_midi_to_frames` returns empty `metadata`), so tempo is recomputed/redefaulted rather than reused; and (b) events are re-extracted from the frames dict (`frames_to_events`) that was itself derived from events at the frames stage — an events → frames → events round-trip. Both are cheap now (the tempo object is only allocated, not analyzed, and the detectors read only `note`/`volume`), so this is a correctness-neutral efficiency residual, not the costly path #119 addressed.

## Evidence
`main.py:683` `tempo_map = EnhancedTempoMap(initial_tempo=500000)` (default `ticks_per_beat=480`) and `:690` `events = frames_to_events(frames)`; mirrored at `:895`/`:899`. `parse_midi_to_frames` (`tracker/parser_fast.py:186-189`) returns `"metadata": {}`, so nothing tempo-related survives the parse JSON.

## Impact
A redundant object allocation and a full events-list rebuild per run; no output difference (detectors ignore tempo). Negligible cost on common files.

## Dimension
8 — Cross-stage recompute

## Related
#119 (closed — costly half fixed), #261 (shared `frames_to_events` extractor); Dimension 8.

## Suggested Fix
Low priority. If ever addressed, serialize the tempo summary into the parse JSON and pass it forward, and/or have the frames stage retain the event list it derived frames from so the detector need not re-extract it.

## Completeness Checks
- [ ] **CONTRACT**: If the parse JSON shape changes (tempo summary added), the consumer stages were updated in lockstep
- [ ] **SIBLING**: Same pattern checked at both detect sites (`run_detect_patterns` and `run_full_pipeline`)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #378 — PIPE-2026-07-19-2: Sequential-fallback sampling omits the (lossy) coverage suffix

**Severity:** LOW (labeled medium by GitHub) · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-19.md

## Description
When parallel detection raises and the sequential fallback fires, the events are pre-sampled to `max_events` at `main.py:930` before being passed to `EnhancedPatternDetector.detect_patterns`, which re-runs `sample_events_for_detection` internally (`tracker/pattern_detector.py:211`). Because the list is already at the cap, the detector's own `self.was_sampled` stays `False`. The subsequent `if detector.was_sampled:` check (`main.py:941`) therefore leaves `coverage_lossy_note` empty, so the success banner's "Pattern coverage" line is printed *without* the "(lossy — measured over the sampled subset)" qualifier even though the coverage number genuinely was computed over a sampled subset.

## Evidence
- `main.py:930` — `events, was_sampled = sample_events_for_detection(events, max_events)` sets a **local** `was_sampled` that drives `pattern_loss_warning` (`main.py:931-938`).
- `main.py:941` — the coverage suffix keys off `detector.was_sampled`, a *different* flag reflecting only the detector's internal (now no-op) sampling.
- `tracker/pattern_detector.py:211` — the detector re-samples but, given an already-capped list, `self.was_sampled` remains `False` (initialized `False` at line 172).

## Impact
Cosmetic. The prominent `pattern_loss_warning` ("compression stats are approximate; ROM content is unaffected") still prints, so the user is not misled about ROM integrity — only the coverage line's parenthetical is missing. No effect on ROM bytes.

## Related
#312/PAT-11 (coverage labeling); #176/PL-03.

## Suggested Fix
Drive `coverage_lossy_note` off the local `was_sampled` (OR it with `detector.was_sampled`) in the fallback branch, mirroring how `pattern_loss_warning` is set.

## Completeness Checks
- [ ] **FALLBACK**: The `EnhancedPatternDetector` fallback still fires and now reports the lossy coverage suffix correctly
- [ ] **TESTS**: A regression test pins the coverage-suffix presence when the fallback samples
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #379 — PIPE-2026-07-19-3: Two export call sites pass divergent references shapes (latent, currently inert)

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

---

# #385 — SAFE-2026-07-19-3: export subcommand writes music.asm directly to the user path (not atomic)

**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-19.md

## Description
`export_tables_with_patterns` / `export_direct_frames` write the final ASM via `with open(output_path, 'w') as f: f.write('\n'.join(lines))`. The full content is assembled into `lines` *before* the file is opened, so the exposure window is a single buffered `write` (only a disk-full/IO error could truncate it), but the write is not atomic (no temp-file + `os.replace`).

On such a rare failure the step-by-step `export` subcommand would leave a truncated `.asm` at the user's output path. (The full pipeline is unaffected — it writes to `temp_path/"music.asm"` inside the auto-cleaned `TemporaryDirectory`.)

## Location
`exporter/exporter_ca65.py:1326-1327` and `:897`; reached from `run_export` (`main.py:616`)

## Evidence
```python
# exporter/exporter_ca65.py:1326
with open(output_path, 'w') as f:
    f.write('\n'.join(lines))
```

## Impact
Very low probability; affects only the `export` subcommand's intermediate `.asm`, not a final ROM.

## Related
#123 (loud DPCM-append warnings — same subcommand's separate partial-output risk, already mitigated).

## Suggested Fix
Write to a sibling temp file and `os.replace()` into place so a failed write never overwrites a prior good `music.asm`. Optional hardening.

## Completeness Checks
- [ ] **SIBLING**: Same atomic-write pattern applied to both `export_tables_with_patterns` (:1326) and `export_direct_frames` (:897), and checked in sibling exporters (NSF/FamiStudio)
- [ ] **TESTS**: A regression test pins that a failed write leaves any prior good `music.asm` intact
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
