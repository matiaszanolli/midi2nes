# Batch fix: #332, #333, #338, #339

Fetched via `gh issue view 332 333 338 339 --repo matiaszanolli/midi2nes --json title,body,labels,state`.
Immutable snapshot as filed — GitHub is authoritative for current state.

## #332 — PERF-12: Pattern-length chunking ceilings parallelism at ~10 tasks regardless of core count
Labels: bug, medium, performance
Source: AUDIT_PERFORMANCE_2026-07-18.md

The #114 fix reshaped `work_chunks` to one dict per pattern length
(`tracker/pattern_detector_parallel.py:120-124`). With pipeline defaults
(min 3, max 12) that's at most 10 tasks regardless of input size or core
count; `pool_workers = min(self.max_workers, len(work_chunks))` caps at 10.
Wasted parallelism on >10-core hosts; work is also unbalanced (each task is
one length, longer lengths cost more). Suggested fix: sub-chunk long
sequences by start-range within each length (or bucket lengths across
workers) so task count scales toward core count; alternatively document the
ceiling and correct CLAUDE.md's "distributes work across all CPU cores" claim.

## #333 — PERF-13: No event-count serial guard before spawning the process pool (only a single-chunk guard)
Labels: bug, low, performance
Source: AUDIT_PERFORMANCE_2026-07-18.md

Only `len(work_chunks) == 1` bypasses the pool (#218). A ~40-event input
still yields up to 10 chunks and spawns a `ProcessPoolExecutor`, pickling
the full sequence/valid_events into every worker, even though serial would
finish before the processes spawn. Suggested fix: add a `len(sequence) < N`
guard before pool construction that calls `_detect_patterns_serial` inline.

## #338 — REG-19: generate_dpcm_index() directory-walk and the sample-not-found skip branch are untested
Labels: bug, low, regression
Source: AUDIT_REGRESSION_2026-07-18.md

`generate_dpcm_index.py` is imported by the live pipeline but only
`get_dpcm_sample_ids_from_frames`/`load_dpcm_index_into_packer` are tested
(66%). The `os.walk`-based `generate_dpcm_index()` builder and the "DPCM
sample not found -> skipped += 1" branch inside `load_dpcm_index_into_packer`
have no coverage — the skip branch is on the live packer path. Suggested
fix: add tests for (a) the walk builder producing one JSON entry per file
with sequential id, (b) a missing-filename index asserting
`skipped==1, loaded==0` with no raise.

## #339 — REG-20: Two FamiStudio/exporter tests still gate on bare assertIn("PATTERNS") structural presence
Labels: bug, low, regression
Source: AUDIT_REGRESSION_2026-07-18.md

`tests/test_exporter_integration.py:121` and
`tests/test_famistudio_export.py:61` assert only that "PATTERNS" appears in
the export, which would still pass if every note/volume value were wrong.
Partially rescued by an adjacent single note-value check and a dedicated
golden-bytes class, but the weak structural checks remain. Suggested fix:
remove the redundant assertIn("PATTERNS") checks (golden-bytes class already
pins pattern rows), or upgrade each to a full expected pattern-row assertion.
