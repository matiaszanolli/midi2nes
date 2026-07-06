---
description: "Convert an audit report's findings into GitHub issues with completeness checks"
argument-hint: "<path-to-audit-report>"
---

# Audit → GitHub Issues Publisher

Turn a finished audit report (`docs/audits/AUDIT_<TYPE>_<DATE>.md`) into one GitHub
issue per actionable finding, with dedup, label reconciliation, and a completeness
gate so nothing silently slips through.

Shared protocol (read, do not restate): `.claude/commands/_audit-common.md` —
the **Base Per-Finding Format** (the exact field set this skill parses) and the
**Deduplication (MANDATORY)** flow. Severity scale: `.claude/commands/_audit-severity.md`.

This skill is the *only* place issues are created. Audit skills stop at writing the
report; they never call `gh issue create`.

## Process

### 1. Load + parse the report

Read `$ARGUMENTS` (e.g. a report named `docs/audits/AUDIT_<TYPE>_<DATE>.md`). Each finding block
follows _audit-common's Base Per-Finding Format: `### <ID>: <Title>` then `Severity`,
`Dimension`, `Location`, `Status`, `Description`, `Evidence`, `Impact`, `Related`,
`Suggested Fix`. Extract those fields per finding; ID + Severity + Location + Status
are required, the rest carry into the issue body.

### 2. Path-validation gate (run first, before judging any finding)

```bash
.claude/commands/_audit-validate.sh        # exit 1 on any STALE backticked path
```

This fails fast when a report was written against moved/renamed paths — a `Location:`
pointing at a file that no longer exists. If a path moved (refactor, not a fix),
re-map it in step 4 before filing; do not file a STALE path.

### 3. Filter by status

Process only findings with status **NEW**. `Existing: #NNN` and `Regression of #NNN`
are already tracked — record them in the summary, do not re-file.

### 4. Validate each NEW finding against current code

- Read the referenced file at the symbol (not the line — line numbers drift; trust
  `grep -rn <fn/class>`).
- **Re-map before judging.** If the `Location:` file no longer exists but the code does
  (a move/rename, not a fix), resolve to the current path and update the finding before
  filing. Do NOT mark a move as STALE.
- Classify: **CONFIRMED** (bug still present) → file it; **STALE** (already fixed) → skip,
  record in summary; **UNVERIFIABLE** (cannot confirm against code) → skip, record in summary.

### 5. Deduplicate against open issues

Follow _audit-common's **Deduplication** flow:

```bash
mkdir -p /tmp/audit
gh issue list --repo matiaszanolli/midi2nes --limit 400 --json number,title,state,labels \
  > /tmp/audit/issues.json
```

Match each CONFIRMED finding's keywords against existing **open** issue titles/bodies.
On a match, skip and record `Existing #NNN` in the summary. If a *closed* issue matches
and the bug is back, file it and note it as a regression of `#NNN`.

### 6. Apply labels from the live repo set

The set of labels that exist in the repo is authoritative — `gh issue create` rejects an
unknown label. Pull the live set first:

```bash
gh label list --repo matiaszanolli/midi2nes --limit 200 --json name --jq '.[].name' \
  > /tmp/audit/labels.txt
```

The audit label set **already exists** (created once, deliberately): severity
(`critical`, `high`, `medium`, `low`) and one domain label per subsystem (`pipeline`,
`nes-hardware`, `mappers`, `exporters`, `patterns`, `dpcm`, `arranger`, `performance`,
`safety`, `tech-debt`, `regression`, `tempo`, plus `documentation`), alongside the
default GitHub labels. File each finding with its **severity + domain** labels directly,
e.g. `--label high --label mappers` (add `bug`/`enhancement` as the kind). Keep the badge
line at the top of the issue body too — it carries the **Source** report reference the
labels don't:

```
**Severity:** HIGH · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-06-28.md
```

If `/tmp/audit/labels.txt` ever shows one missing (e.g. a newly added domain), recreate
just that one before filing — never `gh label create` ad hoc per finding:

```bash
# severity colors: critical b60205, high d93f0b, medium fbca04, low 0e8a16
# domain color:    1d76db  (description "Audit domain: <name>")
gh label create <name> --repo matiaszanolli/midi2nes --color <hex> --description "<desc>" || true
```

Every token passed to `--label` MUST appear in `/tmp/audit/labels.txt`. If `gh` rejects a
label, the reconciliation missed one — fix it, do not drop the finding silently.

**Report-family → domain default** (a per-finding `Dimension` always overrides it):

| Report (`AUDIT_<TYPE>_*.md`) | Default domain |
|------------------------------|----------------|
| `AUDIT_PIPELINE_*` | pipeline |
| `AUDIT_NES_HARDWARE_*` | nes-hardware |
| `AUDIT_PATTERNS_*` | patterns |
| `AUDIT_EXPORTERS_*` | exporters |
| `AUDIT_DPCM_*` | dpcm |
| `AUDIT_ARRANGER_*` | arranger |
| `AUDIT_MAPPERS_*` | mappers |
| `AUDIT_TEMPO_*` | tempo |
| `AUDIT_PERFORMANCE_*` | performance |
| `AUDIT_SAFETY_*` | safety |
| `AUDIT_TECH_DEBT_*` | tech-debt (+ `documentation` for doc-rot) |
| `AUDIT_REGRESSION_*` | regression |
| `AUDIT_INCREMENTAL_*` | per-finding |

### 7. Build the completeness checklist (per CONFIRMED finding)

Append to each issue body. Drop rows that can't apply:

```markdown
## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
```

### 8. Create the issue

```bash
gh issue create --repo matiaszanolli/midi2nes \
  --title "<ID>: <title>" \
  --body  "<badge line + description + evidence + impact + suggested fix + completeness checks>" \
  --label "bug"          # Mode A; or "<severity>,<domain>,bug" in Mode B
```

### 9. Snapshot to local tracking

```bash
mkdir -p .claude/issues/<NUMBER>
```

Write `.claude/issues/<NUMBER>/ISSUE.md` with the finding details. This is the issue
*as filed* — an immutable snapshot, not a live mirror. GitHub is authoritative for
current state (`gh issue view <N> --json state`). Do not write a `State:` field.

### 10. Completeness summary (the gate)

Every NEW finding must reach a terminal action — created, skipped-as-duplicate, or
skipped-with-reason. Print the table and assert: NEW findings parsed == (Created + Skipped).

| Finding | Action | Reason |
|---------|--------|--------|
| PAT-001 | Created #12 | NEW, CONFIRMED |
| PAT-002 | Skipped | Existing #8 |
| PAT-003 | Skipped | STALE (fixed in `tracker/pattern_detector.py`) |

State which label mode (A or B) was used and flag any finding filed with `bug` only
because no domain label exists.

### 11. Suggest next step

For each created issue:

```
Fix with: /fix-issue <number>
```
