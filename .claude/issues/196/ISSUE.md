# EXP-08: Arranger's DPCM sample_id clamp still collapses high ids to one wrong drum (misses the #67/D-04 fix)

**Severity:** HIGH · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-03.md

**Status:** Regression of #67 (D-04) — more precisely, an incomplete fix. #67's fix commit
(`fb70f56`) updated `nes/emulator_core.py:124`'s DPCM `sample_id` clamp to a 255 ceiling and
left an explicit code comment recording the contract, but never touched
`arranger/pipeline_integration.py`, which independently builds the same
`output['dpcm'][frame]` shape for the `--arranger` front-end. The original issue's own
"Completeness Checks" only listed `emulator_core` and `exporter_ca65` as siblings checked —
`arranger/pipeline_integration.py` was not on that list and was missed.

## Description
`arrange_for_nes` (the `--arranger` entry point, wired at `main.py:514` via
`from arranger import arrange_for_nes`) builds its own DPCM frame dict independently of
`nes/emulator_core.py`. Its conversion clamps `note = min(95, data['sample'] + 1)`, which is
exactly the pre-#67 formula. The exporter (`exporter/exporter_ca65.py:979-986`) now trusts
frame producers to hand it `note = sample_id + 1` unclamped up to 255 and applies its own
ceiling of 255 only — it has no way to detect that a producer already pre-clamped the value
at 95. Any `data['sample'] >= 94` therefore arrives at the exporter as `note = 95` regardless
of the real sample id, and the exporter faithfully emits `.byte $XX, $5F` — the engine's
`@cmd_dpcm_play` (`audio_engine.asm:231-256`) then looks up `dpcm_bank_table[94]` /
`dpcm_pitch_table[94]` / etc. for every one of those hits, playing one fixed sample instead
of whichever distinct drum the song actually specified.

## Location
`arranger/pipeline_integration.py:276-283`, specifically line 281:
```python
'note': min(95, data['sample'] + 1),
```

## Evidence
```python
# arranger/pipeline_integration.py:276-283
for frame, data in frames['dpcm'].items():
    output['dpcm'][frame] = {
        'note': min(95, data['sample'] + 1),
        'volume': 15,
    }
```
Compare `nes/emulator_core.py:124` (`"note": min(255, sample_id + 1)`, fixed by #67) and the
exporter's own comment at `exporter_ca65.py:979-984` describing the contract this line
violates. `grep -rn "min(95" arranger/ nes/ exporter/` returns only this one remaining call
site.

## Impact
Silent wrong-drum substitution — the exact D-04 impact ("Any song using more than ~94
distinct DPCM samples ... silently maps every high-id hit to a single wrong sample. Audible
drum substitution with no warning") — but now scoped to the `--arranger` pipeline mode
specifically. `--arranger` is a documented, supported top-level flag (`CLAUDE.md`, `main.py
--help`), so any user relying on it for a drum-heavy song with a large DPCM sample palette
hits this. Blast radius: DPCM/noise channel, `--arranger` front-end only (the default/legacy
front-end via `track_mapper.py` + `emulator_core.py` is unaffected — it already uses the
fixed `min(255, ...)`).

## Related
#67/D-04 (original bug + partial fix); #9, #84 (other DPCM-contract mismatches between
arranger and exporter — same root-cause class: the arranger's independent frame-shaping
code drifting from the emulator/exporter contract).

## Suggested Fix
Change `arranger/pipeline_integration.py:281` to `'note': min(255, data['sample'] + 1)`,
matching `nes/emulator_core.py:124` and the exporter's stated contract. Consider factoring
the DPCM-note encoding (`sample_id + 1`, capped at 255) into one shared helper both
front-ends call, so a future third producer can't silently reintroduce this class of bug
again.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
