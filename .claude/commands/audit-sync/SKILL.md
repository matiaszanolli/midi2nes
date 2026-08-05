---
description: "Sync audit skill prose to match recently-fixed code — retire stale bug descriptions"
argument-hint: "[--range <A>..<B>] [--commits <N>] [--since <date>] [--issues <N1,N2,...>]"
---

# Audit Skill Sync

The `audit-<name>/SKILL.md` files describe the *current* state of the code — a bug's
exact symptom, a formula, an open gap — so that a future `/audit-<name>` run knows
what to check. When a fix lands, that prose goes stale: it still describes the
pre-fix behavior as live. Left alone, a later audit run can re-report an
already-fixed bug as new, or worse, silently miss a *regression* in the same spot
because the checklist item no longer matches what the code actually does now.

This is a different kind of drift than `.claude/commands/_audit-validate.sh` catches.
That script gates **path** drift (a `Location:`-style backtick reference to a file
that moved or was deleted). This skill gates **content** drift (prose describing
code that changed shape but whose path didn't). Run both; they don't overlap.

This skill edits **the audit tooling** (`.claude/commands/audit-*/SKILL.md`), never
application code. It does not find new bugs — that's what the real `/audit-<name>`
skills are for. Think of it as the maintenance pass those skills need to stay
trustworthy.

Shared protocol (read, do not restate): `.claude/commands/_audit-common.md` for the
project layout and routing conventions. This skill does NOT use the severity scale,
dedup flow, or Base Per-Finding Format — there is no "finding" here, only prose to
update.

## Step 1: Determine scope

| Argument | Scope |
|----------|-------|
| *(none)* | Since the last audit-doc sync commit — auto-detect: `git log --oneline -- '.claude/commands/audit-*/SKILL.md' \| grep -iE 'sync|refresh audit|update audit' \| head -1`, then diff from that commit to `HEAD`. |
| `--commits <N>` | Last N commits: `git diff "HEAD~<N>..HEAD"` |
| `--range <A>..<B>` | Explicit revision range |
| `--since <date>` | Everything since a date (see `/audit-incremental` Step 1 for the exact base-commit derivation — same pattern) |
| `--issues <N1,N2,...>` | Skip the git-range scan; resolve each issue directly via `gh issue view <N> --repo matiaszanolli/midi2nes --json title,body,state` and find its fixing commit with `git log --all --grep "#<N>" --oneline` |

Then pull the fix commits in scope:

```bash
git log --oneline <scope>          # commit list — filter to ones matching /^fix:/ or referencing #NNN
git log --stat <scope>             # which source files each commit touched
```

Only commits that **fix a bug** (title starts `fix:`, or references a closed issue)
are candidates — a `feat:`/`refactor:`/`test:`-only commit rarely makes existing
audit prose wrong, though a `refactor:` that moves code the prose cites by path can
(that's `_audit-validate.sh`'s job, not this skill's — don't duplicate it, but do
flag a rewrite that would also fix a path if you happen to touch that paragraph).

## Step 2: Route each fix to its owning skill(s)

Reuse the routing table in `.claude/commands/audit-incremental/SKILL.md` § Step 2 —
same changed-path → owning-audit-skill mapping. Don't duplicate the table here; read
it. A commit can route to more than one skill (e.g. a fix touching both
`arranger/voice_allocator.py` and `nes/envelope_processor.py` routes to both
`/audit-arranger` and `/audit-nes-hardware` — update both if both describe the old
behavior).

## Step 3: Find and rewrite stale prose

For each (fix commit, owning skill) pair:

1. Read the commit's full message (`git show --stat <hash>` then `git show <hash>` for
   the diff) — the body almost always explains the old buggy behavior and the new
   fixed behavior in prose. This is the source material for the rewrite; don't
   re-derive it from the diff alone if the message already states it clearly.
2. Search the owning skill for descriptions of the old state:
   - `grep` for function/constant/class names the diff touched.
   - `grep` for the issue number (`#NNN`) — it may already be mentioned as an open
     question or not mentioned at all.
   - `grep` for a distinctive fragment of the old code the diff *removed* (a formula,
     a magic number, a specific claim) — these are the highest-confidence hits.
3. Classify what you find:
   - **Describes the old state as current/live/an open gap** → rewrite. Read the
     current code at the fixed location first (don't paraphrase the commit message
     blind — confirm it against the file as it stands now).
   - **Already accurate / already marked fixed** → leave untouched. Most files in
     scope will land here; that's expected, not a sign of missed work.
   - **No mention at all, but the fix closed a real invariant worth guarding** → do
     **not** invent a new dimension or checklist item. Record it in the summary as
     "no owning prose — consider a manual addition to `<skill>`" and move on. Adding
     new dimensions is a human editorial call, not this skill's job.
4. Rewrite using the house style already used throughout `audit-*/SKILL.md` — match
   it exactly, don't invent a new convention:

   ```
   **#NNN (ID) is CLOSED**: <what was wrong, why it mattered> ... <what the code does
   now, with exact file:line/symbol and any docs/*.md citation> ... Verify-the-fix:
   <what a future audit run should still confirm — the regression-prevention angle,
   not a restatement of the fix>.
   ```

   Keep edits surgical — preserve the surrounding paragraph's voice and citations;
   don't rewrite adjacent, still-accurate prose just because you're in the
   neighborhood. If the paragraph already had a "Verify-the-fix" style checklist for
   a *different* closed issue, append to it rather than duplicating the pattern.

## Step 4: Validate

```bash
.claude/commands/_audit-validate.sh
```

Path drift can surface incidentally while you're editing (a rewrite that now cites a
file the old prose didn't). Fix or un-backtick before finishing.

## Step 5: Report

Print a summary table — this is the completeness gate, mirroring `/audit-publish`'s:

| Fix commit | Issue(s) | Owning skill(s) | Action |
|------------|----------|------------------|--------|
| `7a2054d` | #364 | audit-nes-hardware, audit-exporters | Updated (2 files) |
| `ed056b0` | #358 | audit-mappers | Already current |
| ... | ... | ... | Flagged: no owning prose (`<file>`) |

Every fix commit in scope must reach a terminal action: **Updated**, **Already
current**, or **Flagged**. Do not silently drop one.

Then, if anything was updated:

```
git diff --stat .claude/commands/audit-*/SKILL.md
```

Suggest a commit (do not commit automatically — this is prose about the codebase,
the user should review it):

```
chore: refresh audit skills to match current code state
```

(matches the convention of prior sync commits — `git log --oneline -- '.claude/commands/audit-*/SKILL.md'`
to see them.)

## Guardrails

- Edits application-audit **prose only** — never touches `main.py`, `tracker/`,
  `nes/`, etc. If you find yourself wanting to fix code, stop; that's `/fix-issue`.
- Never changes severity definitions, dedup flow, or the finding format — those live
  in `_audit-common.md`/`_audit-severity.md` and are out of scope here.
- Never adds or removes a `### Dimension N` heading — only updates prose inside
  existing dimensions. Structural changes to an audit's coverage are a human call.
- Not a replacement for actually running `/audit-<name>` — this only retires
  descriptions of bugs already known to be fixed; it does not look for new ones.
