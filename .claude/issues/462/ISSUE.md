# TD-42: CLAUDE.md cites PROJECT_STATUS.md, which was deleted

- **Issue**: #462

**Severity:** LOW · **Domain:** tech-debt, documentation · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** NEW

## Description
`PROJECT_STATUS.md` was removed in commit `419885e` ("Codebase cleanup.") but the Project Status section of `CLAUDE.md` still points readers (and every Claude session, via the system prompt) at it.

## Evidence
```
$ sed -n '277p' CLAUDE.md
✅ Fully operational end-to-end pipeline (see PROJECT_STATUS.md)

$ ls PROJECT_STATUS.md
ls: cannot access 'PROJECT_STATUS.md': No such file or directory

$ git log --oneline -- PROJECT_STATUS.md
(last touch is the deletion commit 419885e)
```

## Impact
Dangling pointer in the most-read doc in the repo. Cosmetic.

## Suggested Fix
Drop the parenthetical or point it at `docs/ROADMAP.md`, which is current (its "Song banks → ROM … ✅ v1 shipped" section matches the code).

## Related
TD-43 (other doc/prose rot found this cycle).

## Completeness Checks
- [ ] **DOC**: `CLAUDE.md`'s Project Status section no longer references a deleted file
