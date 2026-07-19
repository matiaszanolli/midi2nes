# Batch fix: #266, #269, #300, #301

Fetched via `gh issue view 266 269 300 301 --repo matiaszanolli/midi2nes --json title,body,labels,state`.
Immutable snapshot as filed — GitHub is authoritative for current state.

## #266 — TD-22: Superseded v0.4.0 planning/coverage docs are unlabeled as historical, assert stale current status
Labels: bug, low, tech-debt, documentation
Source: AUDIT_TECH-DEBT_2026-07-05.md

Three docs present long-superseded figures as current status with no "archived"/
"superseded" banner: `docs/IMMEDIATE_ACTIONS.md` ("v0.4.0", "186 tests passing"),
`docs/COVERAGE_REPORT.md` ("186 tests"), `docs/TEST_COVERAGE_IMPROVEMENTS.md`
("568 to 582 tests"). Project is on 0.5.0-dev with 900 tests. Same family as TD-17's
`WORK_PLAN_1.0.0.md` (never filed as its own issue). Suggested fix: add an
"Archived — superseded by docs/ROADMAP.md" banner to all four docs, or move them
under docs/history/.

## #269 — PL-08: compile --mapper has no 'auto', so a prepare --mapper auto project has no matching compile invocation
Labels: enhancement, low, pipeline
Source: AUDIT_PIPELINE_2026-07-05.md

`prepare --mapper auto` resolves and bakes a concrete mapper into the project dir;
`compile --mapper` has no `auto` choice (only nrom/mmc1/mmc3, default mmc3), so a user
must know and pass the resolved mapper explicitly, or `compile_rom`'s exact PRG-size
check raises a clean `CompilationError` (backup/restore contract handles it, no bad ROM
left). Suggested fix: add `auto` to `compile --mapper`, re-running `auto_select` against
the project's own `music.asm` the same way `resolve_mapper` already does for the
non-auto case, OR have `prepare` record the resolved mapper for `compile` to read.

## #300 — DP-05: DMC 'layering' emits a duplicate of the primary sample that the same-frame collapse discards with a misleading 'note dropped' warning
Labels: bug, low, dpcm
Source: AUDIT_DPCM_2026-07-06.md, Status: NEW

For kick (36) / snare (38), `ADVANCED_MIDI_DRUM_MAPPING`'s `layers` list is
`[primary_name, alt_name]` where `alt_name` (`kick_sub`/`snare_rattle`) doesn't exist
in the shipped index. `_handle_layered_samples` always re-emits the primary as a
"layer" on the same frame, producing two identical DPCM events per hit that
`_collapse_same_frame_events` silently dedupes back to one while printing a false
"note(s) dropped" warning. DMC is physically monophonic (`docs/APU_DMC_REFERENCE.md`
§1) — layering can't work there regardless. Suggested fix: remove
`_handle_layered_samples`/`layers` lists, or dedupe against the primary so no
same-frame duplicate is ever emitted.

## #301 — MAP-2026-07-06-2: capacity pre-flight undercounts DPCM .align 64 padding (bounded, packer-guarded)
Labels: bug, low, mappers
Source: AUDIT_MAPPERS_2026-07-06.md, Status: NEW

`estimate_segment_sizes` scores each DPCM `.incbin` at its raw byte size, ignoring the
`.align 64` directive `DpcmPacker` emits before every packed sample, undercounting a
`DPCM_NN` segment's real footprint by up to 63 bytes/sample. Unreachable through the
normal pipeline today since `DpcmPacker` already caps each bank's *aligned* total at
8192 bytes at pack time — only a hand-edited `music.asm` in the narrow undercount
window could pass the pre-flight and then fail at `ld65` instead of failing cleanly
pre-flight. Suggested fix: round each `.incbin` contribution up to the next `.align`
boundary in `estimate_segment_sizes` so the pre-flight matches the packer's
`aligned_size`.
