---
description: "Delta audit — check only recently changed code for regressions and new bugs"
argument-hint: "[--working] [--commits <N>] [--range <A>..<B>] [--since <date>]"
---

# Incremental / Delta Audit

Audit **only what changed**, not a whole subsystem. The goal is to catch *new* bugs and
*regressions* introduced by recent work — fast — by routing each changed file to the
audit dimensions that own it and applying their checks to the diff alone.

This is a meta-audit: it does not define dimensions, it *dispatches* to the real audit
skills (each at `.claude/commands/audit-<NAME>/SKILL.md`). Use those for the authoritative
checklist of any one area.

See `.claude/commands/_audit-common.md` for project layout, inter-stage contracts,
severity, methodology, deduplication, and the base finding format.
See `.claude/commands/_audit-severity.md` for the severity scale + special rules (the
NES-range / contract-break / round-trip rows are the ones a delta most often trips).

## Step 1: Determine the diff scope

Default to the working tree if nothing is specified.

| Argument | Scope | Diff command |
|----------|-------|--------------|
| *(none)* / `--working` | uncommitted work | `git diff HEAD --name-only` (staged-only: `git diff --staged --name-only`) |
| `--commits <N>` | last N commits | `git diff "HEAD~<N>..HEAD" --name-only` |
| `--range <A>..<B>` | explicit revision range | `git diff "<A>..<B>" --name-only` |
| `--since <date>` | everything since a date | base=`$(git log --since="<date>" --format="%H" \| tail -1)`; then `git diff "${base}^..HEAD" --name-only` |

Then pull the actual hunks + log for the same scope:

```bash
git diff HEAD~10..HEAD --stat        # changed-file overview (substitute your scope)
git diff HEAD~10..HEAD               # the hunks you will actually audit
git log --oneline HEAD~10..HEAD      # commit themes, PR/issue numbers
```

Audit the **diff**, with just enough surrounding context to confirm each finding — do not
re-audit untouched code.

## Step 2: Route each changed file to its audit dimension

Map every changed path to the audit skill(s) that own it, then apply that skill's checks
to the diff. A file can hit multiple rows. Risk is the *floor* severity for an
un-disproven finding in that area.

| Changed path | Owning audit(s) | Risk |
|--------------|-----------------|------|
| `main.py` | `/audit-pipeline`, `/audit-safety` | HIGH |
| `tracker/parser_fast.py`, `tracker/parser.py` | `/audit-pipeline`, `/audit-performance` | HIGH |
| `tracker/track_mapper.py` | `/audit-pipeline`, `/audit-nes-hardware` | HIGH |
| `tracker/tempo_map.py`, `tracker/loop_manager.py` | `/audit-tempo` | HIGH |
| `tracker/pattern_detector_parallel.py`, `tracker/pattern_detector.py` | `/audit-patterns`, `/audit-performance` | HIGH |
| `nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py` | `/audit-nes-hardware` | HIGH |
| `nes/project_builder.py`, `nes/debug_overlay.py` | `/audit-mappers`, `/audit-pipeline` | HIGH |
| `mappers/**` | `/audit-mappers` | HIGH |
| `compiler/**` | `/audit-mappers`, `/audit-safety` | HIGH |
| `exporter/exporter_ca65.py`, `exporter/compression.py` | `/audit-exporters`, `/audit-patterns` | HIGH |
| `exporter/exporter_nsf.py`, `exporter/exporter_famistudio.py`, `exporter/base_exporter.py` | `/audit-exporters` | MEDIUM |
| `arranger/**` | `/audit-arranger`, `/audit-nes-hardware` | HIGH |
| `dpcm_sampler/**`, `dpcm_index.json` | `/audit-dpcm`, `/audit-exporters` | MEDIUM |
| `nes/song_bank.py` | `/audit-pipeline` | MEDIUM |
| `config/**` | `/audit-safety` | MEDIUM |
| `core/**` | `/audit-safety`, `/audit-pipeline` | MEDIUM |
| `utils/**`, `benchmarks/**` | `/audit-performance` | MEDIUM |
| `debug/**` | `/audit-mappers` (ROM diagnostics) | LOW |
| `tests/**`, `**/*_test*.py` | `/audit-regression` | LOW |
| `docs/**`, `*.md`, docstrings | `/audit-tech-debt` (doc rot) | LOW |

> The authoritative tree is in `_audit-common.md` § Project Layout — route against it,
> not against memory. `main.py`'s default (subcommand-less) path is `run_full_pipeline`;
> a change there affects the one-command flow even if no subcommand changed.

## Step 3: Regression-focused checks on each changed file

For every changed file, read the hunk + minimal context and ask:

- [ ] **New bug** — logic error, off-by-one, wrong byte/timer width, wrong per-channel pitch table.
- [ ] **Contract break** — a stage's output JSON shape changed but its consumer wasn't updated
      (the classic silent break; see _audit-common § Inter-Stage Data Contracts). `grep` the key
      across producer and consumer.
- [ ] **NES range** — a note/volume/11-bit timer that can now exceed hardware range without a clamp.
- [ ] **Triangle misuse** — volume/duty applied to the triangle channel.
- [ ] **Round-trip** — a pattern/compression change that could make decompressed playback differ
      from the input.
- [ ] **Fallback** — a `ParallelPatternDetector` change that could break the documented fallback
      to `EnhancedPatternDetector`.
- [ ] **Subprocess** — a `compiler/cc65_wrapper.py` change that could swallow a nonzero exit / stderr.
- [ ] **Error handling delta** — a new bare `except`, swallowed exception, or unguarded `json.loads` /
      file open on a user path.
- [ ] **Timing drift** — tempo→frame math that can accumulate off the 60Hz grid.
- [ ] **Missing test** — a changed code path with no test update (flag in "Missing Tests" even if
      the code is right).

## Step 4: Deduplicate

Run the dedup pass from `_audit-common.md` § Deduplication for every finding (existing-issue
search + prior-report scan) before recording it. A regression of a *closed* issue is reported
as "Regression of #NNN".

## Extra Per-Finding Field

In addition to the base format:

- **Changed in**: `<file-path>` (commit `<hash>` / working tree)

## Output

Write to: **`docs/audits/AUDIT_INCREMENTAL_<TODAY>.md`** (YYYY-MM-DD).

### Report structure
1. **Change summary** — scope (range/commits/since), files changed, themes.
2. **Routing map** — each changed file → dimension(s) it was audited under.
3. **Findings** — new bugs + regressions (base format + `Changed in`).
4. **Missing tests** — changed code paths with no test update.

Then suggest:

```
/audit-publish docs/audits/AUDIT_INCREMENTAL_<TODAY>.md
```
