# ARR-2026-08-21-3: Out-of-bucket GM roles (PERCUSSION/SFX) can win _determine_role's max() on the 3.0 GM bonus alone — contradicting the #ARR-2026-08-07-1 fix's stated invariant

**GitHub Issue:** #450
**Source Report:** docs/audits/AUDIT_ARRANGER_2026-08-21.md
**Severity:** MEDIUM · **Domain:** arranger
**Filed:** 2026-08-21

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-08-21.md

## Description
The `defaultdict` fix in `#ARR-2026-08-07-1` stopped the KeyError, but its comment (and the prior audit's rationale) claims an out-of-bucket GM hint "contributes no bonus while the pitch/density/velocity signals below still pick one of the 4 real buckets" and that the appended key is "never enough to win against a real signal". Both claims are false: `role_scores[gm_mapping.role] += 3.0` gives the PERCUSSION/SFX key the full GM bonus, and for an unremarkable track (mid-range pitch, moderate density/velocity, monophonic) the four real buckets top out at 1.0–2.0 — so the out-of-bucket role wins `max()`. When it does, `best_role` is PERCUSSION or SFX: `channel_override` is False (roles "agree"), and **none of the four role-adjustment branches fire** — no priority floor, no `PlayStyle.ARPEGGIATE` for polyphonic harmony, and `analysis.role` carries a value `_assign_channels`' melodic chain has no branch for (a NOISE/DPCM-curated preferred channel falls through to the generic pulse fallback).

## Location
`arranger/role_analyzer.py:215-268` (`_determine_role`)

## Evidence
Reproduced (`/tmp/audit/arranger_role_test.py`): a monophonic mid-range track with program 47 (Timpani) → `role=PERCUSSION, confidence=0.60, preferred=TRIANGLE` (claims the triangle exclusively at priority 6); program 55 (Orchestra Hit) → `role=SFX, preferred=DPCM` → falls through to pulse1; program 115 (Woodblock) → `role=SFX/PERCUSSION, preferred=NOISE` → pulse1. 19/128 GM programs are curated with these roles (`arranger/gm_instruments.py`).

## Impact
Musically-questionable channel claims (a mid-range Timpani/Synth-Drum accompaniment can occupy the bass-reserved triangle at priority 5–6 whenever no priority-8 BASS track outranks it), skipped arpeggiation styling for these tracks, and a comment/audit-trail that documents behavior the code does not have. Determinism is unaffected (dict insertion order is stable; seeded buckets win ties). Contained by the priority sort in typical mixes, hence MEDIUM (suboptimal allocation, playable output).

## Related
#ARR-2026-08-07-1 (the KeyError fix this refines), #408/ARR-2026-08-06-1 (`channel_override` semantics).

## Suggested Fix
Decide the intent and make code+comment agree: either credit an out-of-bucket GM role's bonus to its nearest real bucket (PERCUSSION→DECORATIVE or a drum path, SFX→DECORATIVE) so `max()` always lands in the 4 buckets as the comment claims, or explicitly support PERCUSSION/SFX as first-class roles in the role-adjustment branches and `_assign_channels`.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
