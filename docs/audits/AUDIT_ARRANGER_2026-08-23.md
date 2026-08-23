# Arranger Audit — 2026-08-23 (re-verification pass)

**Scope**: `--arranger` mode (`arranger/`), its contract with the legacy `frames` shape
(`nes/emulator_core.py`) and the exporter (`exporter/exporter_ca65.py`), and the GM/DPCM
seams shared with `/audit-dpcm` and `/audit-nes-hardware`. All 8 skill dimensions covered.

**This supersedes the earlier same-day report.** The morning's `AUDIT_ARRANGER_2026-08-23.md`
found two findings (`ARR-2026-08-23-1`, a cross-track GM program-change scope bug, and
`ARR-2026-08-23-2`, doc-rot in this skill file itself). Both were filed as **#492** and
**#493**, fixed in commit `2ed6c1c`, and closed the same day. This pass re-audits current
`HEAD` (`fc5027c`) from scratch — not by trusting that report's prose — to confirm the fixes
actually hold and to look for anything new since.

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 0 |

**Contract-parity verdict: PASS** (re-verified empirically this session). Built a legacy-path
`frames` dict and an arranger-path `frames` dict from the same MIDI
(`test_midi/multiple_tracks.mid`) and diffed per-channel frame keys directly: `pulse1`/`pulse2`
match key-for-key (`{'pitch', 'note', 'volume', 'control'}` on both sides). Ran
`tests/test_arranger_frame_contract.py` (6/6 passed) for the triangle/noise/dpcm shapes that
fixture doesn't exercise (no percussion/DPCM content in that particular test MIDI). Confirmed
the exporter genuinely reads the arranger's pre-baked `pitch`/`control` rather than discarding
them (`exporter/exporter_ca65.py:243`, `:264`, `:1417`, `:1436` all call `frame_data.get('pitch'
| 'control', ...)` with a computed fallback only when absent).

**No new findings this pass.** Both prior findings from the earlier same-day report were
independently re-confirmed fixed:

- **#492** (cross-track GM program scope): `tracker/parser_fast.py:127` declares
  `channel_programs = {}` immediately before the second pass and *outside* the
  `for i, track in enumerate(mid.tracks):` loop (`:132`) — confirmed by direct read, not just
  grep-for-absence. The regression test
  (`tests/test_parser_fast.py::test_program_change_on_one_track_reaches_another_track_sharing_its_channel`,
  the exact conductor/violin fixture the original finding used) passes:
  `python -m pytest tests/test_parser_fast.py -k "program_change or channel_scoped"` → 3 passed.
- **#493** (SKILL.md doc-rot): `grep -n "STILL OPEN\|0x81" .claude/commands/audit-arranger/SKILL.md`
  now returns only the historical mention of `0x81` correctly framed as *removed* (the current
  skill text this audit ran from already reads "**#434 is CLOSED**..." — confirmed the live
  file, not a cached copy).

**Other high-risk items independently spot-checked this pass** (not re-listed as findings —
all held; re-verifying reduces risk of silently trusting stale prose from the prior report):
- GM coverage: `len(GM_INSTRUMENT_MAP) == 128`, zero missing programs 0–127 (computed directly).
- No `TRIANGLE`/`NOISE`/`DPCM`-channel mapping in `GM_INSTRUMENT_MAP` or `GM_DRUM_MAP` carries
  a `duty` (computed directly over both tables — 0 conflicts).
- `get_role_priority` (#88/ARR-05): `grep -rn get_role_priority --include="*.py" .` matches only
  the explanatory `# NOTE (#88/ARR-05)` comment at `gm_instruments.py:1326` — no definition, no
  caller, confirming it is genuinely deleted, not merely uncalled.
- `arp_speed` clamp (#91/ARR-08): the property setter at `arranger/voice_allocator.py:107-114`
  still reads `self._arp_speed = max(1, int(value))` and is the sole assignment path (no other
  `self._arp_speed =` write exists outside the setter).
- Triangle-overflow fallback (#409): `arranger/role_analyzer.py:433` still reads
  `if track.role == MusicalRole.BASS and not triangle_assigned:` — the non-BASS branch that
  used to let any role claim triangle as a last resort remains removed.
- Role-tie determinism (#450): `role_scores` is still a `defaultdict(float, {...4 buckets...})`
  (`role_analyzer.py:227`) and the GM-hint bonus is still guarded by `if gm_mapping.role in
  role_scores:` (`:239`) before crediting it — a 5th out-of-bucket key cannot be inserted via
  this path.

## Findings

None. All items checked this pass — both the two previously-open findings and the additional
spot-checks above — are confirmed fixed/holding as of `HEAD` (`fc5027c`). `gh issue list` shows
no arranger-labeled issue currently open.

---

No new issues to publish this cycle. If a future run finds something new:
```
/audit-publish docs/audits/AUDIT_ARRANGER_<TODAY>.md
```
