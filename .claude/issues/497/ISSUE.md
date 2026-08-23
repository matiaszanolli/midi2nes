# PAT-2026-08-23-3: audit-patterns/SKILL.md line citations have drifted again

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-08-23.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/497

## Description
`audit-patterns/SKILL.md`'s line citations have drifted again from the live tree. Commit
`efecc87` (which fixed #435-438) corrected the specific prose describing the removed
`_WORKER_EVENTS` global and the renamed worker entry point, and `d9feba1` (#459) touched one
line for the `DETECTOR_MAX_EVENTS` value — but neither was a full line-number resync, and the
broader drift already catalogued by the 2026-08-21 audit report is confirmed still present:

- `main.py:36-37` (cited for `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`) → actually
  `constants.py:18-19` (imported into `main.py` at line 51).
- `pattern_detector.py:799-829` (`compress_patterns`) → actually `:869-899`.
- `pattern_detector.py:831-841` (`_hash_pattern`) → actually `:901-911`.
- `pattern_detector.py:843-891` (`calculate_compression_stats`) → actually `:913+`.
- `pattern_detector.py:305-323` (selection loop) → the loop starts at `:324`, gate check `:335`.
- `pattern_detector.py:320-338` (`_find_pattern_matches`) → actually `:361-379`.
- `pattern_detector_parallel.py:216-254` (`_select_best_patterns`) → actually starts `:286`.
- `pattern_detector_parallel.py:274-283` (`_empty_result`) → actually `:344`.
- `main.py:827-853` (pipeline fallback try/except) → actually `:1220-1255`.
- `main.py:844` (fallback re-trim) → actually `:1238`.

## Evidence
Each pair verified by direct `grep -n`/read against the current tree during the 2026-08-23
audit session.

## Impact
Future audits chase wrong line numbers, costing extra grep/read round-trips. No functional
impact. Same class already filed and fixed for other domains (#493 arranger, #463 tech-debt).

## Related
`docs/audits/AUDIT_PATTERNS_2026-08-21.md` (PAT-2026-08-21-7),
`docs/audits/AUDIT_PATTERNS_2026-08-07.md` (PAT-2026-08-07-C), #334/PERF-14, #17, #104, #493,
#463.

## Suggested Fix
Run `/audit-sync` over `audit-patterns/SKILL.md` for a full line-number resync, then
`.claude/commands/_audit-validate.sh`.

## Completeness Checks
- [ ] **DOC**: All line citations in `audit-patterns/SKILL.md` re-verified against the live tree
  after the resync
