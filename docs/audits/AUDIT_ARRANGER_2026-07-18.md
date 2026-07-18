# Arranger Audit — 2026-07-18

**Scope:** The `--arranger` front-end (`arranger/` subsystem): role detection
(`role_analyzer.py`), GM-instrument mapping (`gm_instruments.py`), priority-based voice
allocation + arpeggiation (`voice_allocator.py`), and the `arrange_for_nes` integration
(`pipeline_integration.py`). All 8 dimensions of `audit-arranger/SKILL.md`.

**This is a delta/re-verify pass.** The branch `fix/audit-167-88-91` has uncommitted changes
directly in this audit's scope — `arranger/__init__.py`, `arranger/gm_instruments.py`,
`arranger/role_analyzer.py`, `arranger/voice_allocator.py`, `tests/test_voice_allocator.py` —
that appear to be an in-progress fix for the two items the 2026-07-17 report left open: **#88
(ARR-05)** and **#91 (ARR-08)**. This audit was run against the current working tree (not just
HEAD), verifying that in-progress fix plus re-checking the rest of the subsystem for
regressions.

**Entry path traced:** `main.py` `run_full_pipeline` (`arp_speed=3` hardcoded at the call
site) → `arrange_for_nes` (`arranger/pipeline_integration.py:201`) → `analyze_midi_events`
(incl. `_apply_sustain`) → `allocate_with_arpeggiation` →
`FrameByFrameAllocator.process_song` → `VoiceAllocator.set_arrangement` / `allocate_frame`.
Downstream: `frames` → Step-4 pattern detection (`main.py`) →
`CA65Exporter.export_tables_with_patterns`.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 0 |
| **Total** | **0 new** |

No new findings survived skeptical re-reading. Both previously-open items (#88, #91) have
correct, complete fixes in the working tree (see "Verified fixed" below). The one previously
open LOW finding, **ARR-NEW-5** (GM-program hint picks the first note's program, not a
program change that arrives later), is untouched by this diff and remains open — carried
forward, not re-filed.

**Contract-parity verdict: PASS.** The working-tree diff does not touch
`pipeline_integration.py`'s frame-conversion code (the `output` dict construction for
`pulse1`/`pulse2`/`triangle`/`noise`/`dpcm`), so the 2026-07-17 verdict still holds unchanged:
`arrange_for_nes` emits the canonical key set (`note`/`pitch`/`volume`/`control`) the exporter
reads for every channel, triangle carries no duty, and noise/DPCM use the rest-sentinel-safe
floors from #84/#253. Re-ran `tests/test_arranger_frame_contract.py` (all pass) to confirm.

**Highest-leverage item:** none — this run is a clean bill for the two items it was scoped to
verify. #91 (ARR-08) was the last unguarded crash path in the arranger and is now closed.

## Verified fixed (this run's diff)

- **#91 (ARR-08) — FIXED, verified complete.** `VoiceAllocator.arp_speed` is now a property
  (`arranger/voice_allocator.py:97-108`) whose setter clamps `self._arp_speed = max(1,
  int(value))`. Checked **every** mutation site that sets `arp_speed` on a `VoiceAllocator`
  instance:
  - `VoiceAllocator.__init__` (`:77`): `self.arp_speed = arp_speed` — assigns through the
    property (not `self._arp_speed` directly), so construction with `arp_speed=0` or negative
    is clamped to 1.
  - `allocate_with_arpeggiation` (`:483`): `processor.allocator.arp_speed = arp_speed` —
    also an attribute assignment on the instance, so it goes through the same setter.
  - `grep -rn "_arp_speed\b"` across the repo shows only the property's own `getter`/`setter`
    body touch the private attribute — no code path bypasses the setter to write
    `self._arp_speed` directly.
  - The consuming read site, `state.arp_frame % self.arp_speed` (`:267`), now can never see 0.
  - Reproduced the prior crash is gone: `arrange_for_nes(events, arp_speed=0)` on a 3-note
    chord that persists across two frames (the exact repro condition documented in the
    2026-07-17 report — the crash previously hit on the *second* frame of a held chord, not
    the first) now returns normally instead of raising `ZeroDivisionError`.
  - `int(value)` also absorbs non-int numeric input (e.g. a stray float `arp_speed=0.0`)
    before the floor, so the guard is not narrowly typed to `int` inputs only.
  - New test class `tests/test_voice_allocator.py::TestArpSpeedValidation` (3 tests) covers
    construction with `arp_speed=0` and `-5`, reassignment to `0` post-construction, and an
    end-to-end `arrange_for_nes(events, arp_speed=0)` call — all pass (`python -m pytest
    tests/test_voice_allocator.py -q` → 21 passed). This is the right regression net: it pins
    both mutation sites, not just the constructor.
- **#88 (ARR-05) — FIXED, verified complete (different fix than previously suggested).**
  Rather than wiring `get_role_priority()` into `_assign_channels` (the "Suggested Fix" in
  earlier reports), this diff removes the function entirely: deleted from
  `arranger/gm_instruments.py` (replaced with an explanatory comment at the former location,
  `:1300-1305`, pointing at `TrackAnalysis.priority` as the single source of truth) and
  un-exported from `arranger/__init__.py` (both the `from .gm_instruments import
  get_role_priority` line and its `__all__` entry). `grep -rn "get_role_priority"` across the
  whole repo now matches only that explanatory comment — no remaining import, call site, or
  test reference. This is a valid resolution of the underlying problem (dead code that could
  mislead a maintainer into thinking it governs drop order) without the risk of wiring in a
  second, contradictory priority scheme. `role_analyzer.py`'s only change is a comment
  clarifying `TrackAnalysis.priority` is the live drop key (`:287-288`) — no behavior change,
  confirmed by diff.
  - Full arranger-scoped test run after the removal: `python -m pytest tests/test_arranger.py
    tests/test_arranger_drum_detection.py tests/test_arranger_frame_contract.py
    tests/test_voice_allocator.py tests/test_role_analyzer.py -q` → all pass, no
    `ImportError`/`AttributeError` from the removed export.

## Verified unaffected by this diff (re-confirmed, not re-filed)

- **#84–#87, #89–#90, #92, #205–#207, #230–#232, #251–#253, #268, #295/#296 — still fixed.**
  None of the files touched by this working-tree diff (`__init__.py`, `gm_instruments.py`,
  `role_analyzer.py`, `voice_allocator.py`) alter the frame-key contract, GM drum routing,
  pitch-table delegation, per-note drum dispatch, per-chord arp phase, or `_apply_sustain`
  overlap logic — all diff hunks are scoped to the `arp_speed` property and the
  `get_role_priority` removal. Re-ran the full arranger + role-analyzer + voice-allocator test
  files (`56 passed`) as a regression net.
- **ARR-NEW-5 (2026-07-17, LOW, no issue number yet)** — `analyze_midi_events`
  (`arranger/pipeline_integration.py:134-137`) still picks the *first* event with a non-`None`
  `program` rather than accounting for a program change arriving after the first note-on. This
  file is untouched by the current diff; the gap is unchanged and not re-filed here since it
  was already reported last cycle.

## Findings

None. No new defect survived the skeptical re-read: the `arp_speed` fix guards both
mutation sites with no bypass, and the `get_role_priority` removal has no dangling references.
The scope of this run's diff is narrow and the fixes are complete for what they target.

---

*Generated by `/audit-arranger` (delta/re-verify pass on uncommitted working-tree changes).
Deduplicated against `/tmp/audit/issues.json` (matiaszanolli/midi2nes open issues, 27 entries
including #88 and #91, both still OPEN on GitHub pending commit/close) and `docs/audits/`
prior reports (`AUDIT_ARRANGER_2026-06-29/07-03/07-05/07-06/07-17.md`). #88 and #91 have
verified-complete fixes in the working tree but remain open on GitHub until committed and
closed. ARR-NEW-5 carries forward unchanged, untouched by this diff.*

Suggested next step (once the working-tree changes are committed):

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-07-18.md
```
