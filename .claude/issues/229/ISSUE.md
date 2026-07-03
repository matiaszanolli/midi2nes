# TD-19: A prior audit report is corrupted with leaked tool-call syntax

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-07-03.md

## Description
The last two lines of the checked-in `docs/audits/AUDIT_TECH_DEBT_2026-06-29.md` are `</content>` and `</invoke>` — XML-like tags from some tool-call/harness serialization that leaked into the markdown body instead of being stripped before the file was written. This is committed at `HEAD` (`git show HEAD:docs/audits/AUDIT_TECH_DEBT_2026-06-29.md | tail -2` reproduces both lines), not a local/uncommitted artifact.

Note: this is inert leftover markup, not a natural-language instruction — it contains no directive and was not acted on as one; it is reported here purely as checked-in cruft.

**Location:** `docs/audits/AUDIT_TECH_DEBT_2026-06-29.md:295-296`

## Evidence
- `git log --oneline -- docs/audits/AUDIT_TECH_DEBT_2026-06-29.md` → `9b4f3f8 Add tech-debt and tempo audits for 2026-06-29`; the tags are part of that commit's blob.
- `git show HEAD:docs/audits/AUDIT_TECH_DEBT_2026-06-29.md | tail -2` → `</content>` / `</invoke>`.

## Impact
Cosmetic only — the corruption is after the report's closing `---` divider, so it doesn't affect the readable content above it. But it is confusing cruft in a checked-in doc.

## Suggested Fix
Delete the two trailing lines in a follow-up commit; consider a sanity check (e.g. `grep -L '</invoke>\|</content>'`) before committing future audit-generated docs.

## Related
None.

## Note on filing decision
This finding is about a corrupted documentation file, not a code bug — arguably a trivial direct fix would suffice instead of a tracked issue. Filed as an issue per the audit-publish skill's uniform "every NEW finding reaches a terminal action" process; flagged here for the maintainer to judge whether to just fix-and-close immediately (`/fix-issue 229`) or handle it as a one-line PR outside the audit flow.

## Completeness Checks
- [ ] **DOC**: Trailing `</content>`/`</invoke>` lines removed from `docs/audits/AUDIT_TECH_DEBT_2026-06-29.md`
- [ ] **TESTS**: A pre-commit/CI sanity check for leaked tool-call markup in `docs/audits/*.md` (or docs generally) is added
