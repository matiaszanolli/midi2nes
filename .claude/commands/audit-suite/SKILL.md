---
description: "Run a preset suite of audits in parallel"
argument-hint: "--preset <name>"
---

# Audit Suite Orchestrator

Runs a **named preset** — a curated list of other `/audit-*` skills — by fanning them
out as background agents in parallel, then merges their reports into one summary. This
skill owns no audit logic of its own; it only sequences and aggregates. Shared protocol
(project layout, severity, dedup, report format) lives in
`.claude/commands/_audit-common.md` and `.claude/commands/_audit-severity.md` — not repeated here.

Every audit referenced below is a live skill at `.claude/commands/audit-<name>/SKILL.md`,
invoked as `/audit-<name>`. The full subsystem + meta set (12):
pipeline, nes-hardware, patterns, exporters, dpcm, arranger, mappers, tempo,
performance, safety, tech-debt, regression. (`/audit-incremental` is the delta meta-audit;
`/audit-publish` is post-processing, never part of a preset.)

## Preset Index

| Preset | When | Audits |
|--------|------|--------|
| `quick` | after any change, < 10 min | incremental |
| `pre-release` | before tagging a version | pipeline · nes-hardware · mappers · regression |
| `comprehensive` | monthly / pre-milestone | all 12 |
| `tech-debt-deep` | after a milestone closes | tech-debt · incremental |
| `audio-correctness` | after APU/channel/pitch/envelope work | nes-hardware · tempo · exporters |
| `compression-deep` | after pattern/compression work | patterns · exporters · regression |
| `rom-deep` | after mapper / project-builder / compiler work | mappers · pipeline · nes-hardware |
| `arranger-deep` | after arranger / voice-allocation work | arranger · nes-hardware · tempo |
| `dpcm-deep` | after DPCM / drum work | dpcm · exporters |
| `pipeline-deep` | after main.py / stage-contract work | pipeline · patterns · exporters · safety |

## Presets

### `--preset quick`
Fast sanity check after a change (< 10 min):
1. `/audit-incremental --commits 5`

### `--preset pre-release`
Run before tagging a release — the stages that decide whether a ROM boots and plays:
1. `/audit-pipeline`
2. `/audit-nes-hardware`
3. `/audit-mappers`
4. `/audit-regression`

### `--preset comprehensive`
Full coverage (longest — run monthly or before a major milestone). Every subsystem +
both meta audits:
1. `/audit-pipeline`
2. `/audit-nes-hardware`
3. `/audit-patterns`
4. `/audit-exporters`
5. `/audit-dpcm`
6. `/audit-arranger`
7. `/audit-mappers`
8. `/audit-tempo`
9. `/audit-performance`
10. `/audit-safety`
11. `/audit-tech-debt`
12. `/audit-regression`

### `--preset tech-debt-deep`
Surface accumulated debt (run after a milestone closes, before opening the next):
1. `/audit-tech-debt`
2. `/audit-incremental --commits 30`

### `--preset audio-correctness`
After APU register / channel / pitch-table / envelope work — the path from a note to a
register write:
1. `/audit-nes-hardware`
2. `/audit-tempo`
3. `/audit-exporters`

### `--preset compression-deep`
After pattern-detection or compression changes — round-trip integrity is the headline risk:
1. `/audit-patterns`
2. `/audit-exporters`
3. `/audit-regression`

### `--preset rom-deep`
After mapper, project-builder, or CC65-compiler changes:
1. `/audit-mappers`
2. `/audit-pipeline`
3. `/audit-nes-hardware`

### `--preset arranger-deep`
After arranger / role-analysis / voice-allocation / arpeggiation changes:
1. `/audit-arranger`
2. `/audit-nes-hardware`
3. `/audit-tempo`

### `--preset dpcm-deep`
After DPCM sample / drum-mapping changes:
1. `/audit-dpcm`
2. `/audit-exporters`

### `--preset pipeline-deep`
After `main.py` dispatch or stage-contract changes:
1. `/audit-pipeline`
2. `/audit-patterns`
3. `/audit-exporters`
4. `/audit-safety`

## Execution

1. Parse the `--preset` argument from `$ARGUMENTS`. If unknown, list the preset index above and stop.
2. `mkdir -p /tmp/audit`.
3. Launch each audit in the preset as a **background agent**, max 3 concurrent. The audits
   are independent — they read the tree and write distinct reports — so they fan out in
   parallel with no ordering dependency.
4. Each audit writes its own report to `docs/audits/AUDIT_<TYPE>_<TODAY>.md` (per _audit-common finalization).
5. When all complete, produce a combined summary:

```markdown
# Audit Suite Summary — <preset> — <date>

| Audit | Findings | CRITICAL | HIGH | MEDIUM | LOW | Report |
|-------|----------|----------|------|--------|-----|--------|
| pipeline | 3 | 0 | 1 | 2 | 0 | AUDIT_PIPELINE_... |
| ...   | ... | ... | ... | ... | ... | ... |

Total: X findings (C critical, H high, M medium, L low)
```

6. If any CRITICAL findings exist, warn prominently at the top of the summary.
7. For each report that has findings, suggest:
   `/audit-publish docs/audits/AUDIT_<TYPE>_<TODAY>.md`
