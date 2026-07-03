# NH-26: Drum noise-fallback events lack a `note` key — crashes `process_all_tracks` on common drum input

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/195
**Severity:** CRITICAL
**Domain:** nes-hardware
**Source:** docs/audits/AUDIT_NES-HARDWARE_2026-07-03.md
**Labels:** critical, nes-hardware, bug

## Description
`EnhancedDrumMapper.map_drums` resolves each drum hit to a DPCM sample name via `_resolve_dpcm_sample_name`; when that returns falsy (no matching sample — per `AUDIT_DPCM_2026-06-29.md` D-10 this is the default-mapping norm for everything except kick/snare, and even those miss because the velocity-split sample names the advanced map requests aren't in the shipped `dpcm_index.json`), the hit is appended to `noise_events` as `{"frame": frame, "velocity": velocity}` — **no `note` field**. `assign_tracks_to_nes_channels` routes this list straight into `nes_tracks['noise']` (when the noise channel isn't already claimed by another track). `process_all_tracks`'s noise branch (added when NH-01/#9 was fixed) assumes every noise event carries a MIDI `note` to convert to a period index via `self.midi_to_nes_pitch(e['note'], 'noise')` — an assumption the drum-mapper fallback never satisfies. The dict access raises `KeyError: 'note'` with no guard anywhere on the path, so the exception propagates out of the `frames` pipeline stage (and the single-command `run_full_pipeline`), aborting the entire build.

## Location
- `dpcm_sampler/enhanced_drum_mapper.py:307-311` (`noise_events.append({"frame": frame, "velocity": velocity})` — no `note` key)
- Consumed at `nes/emulator_core.py:165` (`period = max(1, self.midi_to_nes_pitch(e['note'], 'noise'))`)
- Reached via `tracker/track_mapper.py:243-249` (`nes_tracks['noise'] = noise_events`)

## Impact
Any MIDI file with a percussion track that the shipped DPCM index doesn't fully cover — i.e. essentially any real-world drummed song under the default `use_advanced=True` mapping — crashes `main.py` (both the full pipeline and the `frames` subcommand) before any ROM is produced. No workaround except manually stripping percussion from the source MIDI or supplying a DPCM index that happens to resolve every used drum note.

## Related
D-10/D-11 (`AUDIT_DPCM_2026-06-29.md`, closed #73/#74), closed #9/NH-01.

## Suggested Fix
Either have `enhanced_drum_mapper.py`'s noise fallback carry a sensible default `note` (e.g. the GM drum's own MIDI note, already in scope as `midi_note`), or make `process_all_tracks`'s noise branch tolerate a missing `note` with `e.get('note')` and a documented default period/mode instead of a bare `e['note']`.

## Dedup
Checked against `/tmp/audit/issues_nes-hardware.json` (47 open issues) via `gh search issues` for "noise_events", "KeyError" — no open match. Closed #73/#74 (D-10/D-11) are related upstream findings but do not cover the missing-`note`-key consumer crash.
