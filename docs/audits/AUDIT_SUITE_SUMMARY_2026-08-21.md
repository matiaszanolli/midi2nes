# Audit Suite Summary — comprehensive — 2026-08-21

> ⚠️ **2 CRITICAL findings** — both new regressions in the current master, both live-reproduced:
>
> 1. **PIPE-2026-08-21-1** — Commit `ffccf51` (drum-mapping fix) un-gated `EnhancedDrumMapper.map_drums`'s channel-blind scan: every melodic note-on is drum-mapped, so drumless MIDIs ship ROMs with phantom DPCM percussion, and `song build` falsely rejects every melodic song in legacy mode — **all CLI-level jukebox builds are currently blocked**. Independently confirmed by the dpcm and exporters audits.
> 2. **PIPE-2026-08-21-3** — Jukebox `song_table` is indexed with 8-bit `current_song*5` math in `audio_engine.asm` while the exporter emits an unbounded stride-5 table: banks with ≥ 52 songs pass every gate (capacity, CC65, validation) then silently play wrong streams/channels from song index 51. Independently confirmed by the nes-hardware, exporters, and mappers audits.

## Results by audit

| Audit | Findings | CRITICAL | HIGH | MEDIUM | LOW | Report |
|-------|----------|----------|------|--------|-----|--------|
| pipeline | 8 | 2 | 2 | 1 | 3 | AUDIT_PIPELINE_2026-08-21.md |
| nes-hardware | 8 | 0 | 1 | 5 | 2 | AUDIT_NES_HARDWARE_2026-08-21.md |
| patterns | 7 | 0 | 0 | 2 | 5 | AUDIT_PATTERNS_2026-08-21.md |
| exporters | 9 | 0 | 0 | 3 | 6 | AUDIT_EXPORTERS_2026-08-21.md |
| dpcm | 5 | 1* | 1 | 0 | 3 | AUDIT_DPCM_2026-08-21.md |
| arranger | 5 | 0 | 2* | 2 | 1 | AUDIT_ARRANGER_2026-08-21.md |
| mappers | 2 | 0 | 0 | 1 | 1 | AUDIT_MAPPERS_2026-08-21.md |
| tempo | 1 | 0 | 0 | 0 | 1 | AUDIT_TEMPO_2026-08-21.md |
| performance | 3 | 0 | 0 | 2 | 1 | AUDIT_PERFORMANCE_2026-08-21.md |
| safety | 5 | 0 | 0 | 4 | 1 | AUDIT_SAFETY_2026-08-21.md |
| tech-debt | 13 | 0 | 0 | 1 | 12 | AUDIT_TECH_DEBT_2026-08-21.md |
| regression | 7 | 0 | 1 | 5 | 1 | AUDIT_REGRESSION_2026-08-21.md |
| **Raw total** | **73** | **3** | **7** | **26** | **37** | |

**Total unique: 70 findings (2 critical, 6 high, 25 medium, 37 low)** after cross-audit dedup:
- \* dpcm's CRITICAL is a cross-reference to PIPE-2026-08-21-1 (independently confirmed, not re-filed).
- \* arranger's ARR-2026-08-21-1 and dpcm's DPCM-2026-08-21-2 are the same defect (counted once as HIGH).
- nes-hardware's jukebox `current_song*5` wrap MEDIUM is the engine-side view of PIPE-2026-08-21-3 (counted once as CRITICAL).

## CRITICAL and HIGH findings (unique)

| # | ID | Sev | Description |
|---|----|----|-------------|
| 1 | PIPE-2026-08-21-1 | CRITICAL | `ffccf51` regression: channel-blind drum scan → phantom DPCM on melodic MIDIs; blocks all `song build` runs |
| 2 | PIPE-2026-08-21-3 | CRITICAL | 8-bit `current_song*5` jukebox indexing silently corrupts playback at song index ≥ 51 |
| 3 | PIPE-2026-08-21-2 | HIGH | #377 wrong-stage-JSON guard fix (`c4894d2`) never merged — parse JSON into `frames`/`export` still exits 0 with empty output |
| 4 | PIPE-2026-08-21-4 | HIGH | `run_song_build` has no backup/restore or exception net — a failed rebuild destroys a previously good jukebox ROM in place |
| 5 | NH-HW-2026-08-21-1 | HIGH | Engine addresses only 32 instruments but exporter guard allows 256 — ids ≥ 32 silently alias to `id % 32` (wrong volume/pitch/duty) |
| 6 | DPCM-2026-08-21-2 / ARR-2026-08-21-1 | HIGH | Arranger DPCM slot ids consumed as catalog ids (no `dpcm_sample_map`) — every `--arranger` kick plays "Hit 1", every snare plays a kick |
| 7 | ARR-2026-08-21-2 | HIGH | `analyze_midi_events` single-slot `active_notes` overwrite destroys overlapping same-pitch notes (200 frames collapse to 2) |
| 8 | REG-30 | HIGH | Drum-mapper tests direction-blind (no melodic-negative fixtures) — the reason PIPE-2026-08-21-1 shipped with a green suite |

## Cross-cutting themes

1. **Stranded fixes on unmerged branches**: three closed issues' fixes never reached master — #377 (PIPE-2026-08-21-2, HIGH), #352 `DETECTOR_MAX_EVENTS` recalibration (TD-39, MEDIUM — the ~26s `detect-patterns` stall is still live), #346/#347 dead-code removal (TD-38). 13 unmerged fix branches were triaged; the other 10 landed via other commits.
2. **Jukebox path (#30/F-13)**: the 2026-08-07 defects (MAP-1/2, REG-27/28) are confirmed fixed in `8ea7ac3` with real regression tests — but new gates remain: phantom-DPCM rejection blocks all CLI builds (CRITICAL 1), ≥ 52-song banks corrupt (CRITICAL 2), split `prepare`/`compile` always fails at link (MAP-2026-08-21-1), and a failed rebuild clobbers the old ROM (HIGH 4).
3. **Tests pass while features are broken**: every HIGH/CRITICAL above was invisible to the suite — direction-blind drum fixtures, wrong-target pinned slot ids, FamiStudio fixtures that dodge the buggy branch, untested CLI paths (regression audit REG-30…REG-35).
4. **Stale audit-skill prose**: tempo (#259/#260), dpcm (#76), arranger (#88/#91), performance, and tech-debt skills describe already-fixed bugs — run `/audit-sync` to retire them.
5. **Good news**: pattern compression round-trip is empirically lossless on both detectors; 60Hz frame timing has zero drift over a 5-minute song; all 20 historical PERF fixes and all 13 closed safety fixes hold.

## Suggested next steps

Publish each report's findings as GitHub issues:

```
/audit-publish docs/audits/AUDIT_PIPELINE_2026-08-21.md
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-08-21.md
/audit-publish docs/audits/AUDIT_PATTERNS_2026-08-21.md
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-08-21.md
/audit-publish docs/audits/AUDIT_DPCM_2026-08-21.md
/audit-publish docs/audits/AUDIT_ARRANGER_2026-08-21.md
/audit-publish docs/audits/AUDIT_MAPPERS_2026-08-21.md
/audit-publish docs/audits/AUDIT_TEMPO_2026-08-21.md
/audit-publish docs/audits/AUDIT_PERFORMANCE_2026-08-21.md
/audit-publish docs/audits/AUDIT_SAFETY_2026-08-21.md
/audit-publish docs/audits/AUDIT_TECH_DEBT_2026-08-21.md
/audit-publish docs/audits/AUDIT_REGRESSION_2026-08-21.md
```

Note: the performance audit flagged that the 2026-08-07 suite's findings were never published to GitHub — worth publishing both rounds together.
