# NH-HW-2026-08-05-1: --arranger has no producer for the noise mode bit — hi-hats/cowbell lose their metallic timbre

**Severity:** MEDIUM · **Domain:** nes-hardware (cross-filed: arranger) · **Source:** docs/audits/AUDIT_NES-HARDWARE_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/392

## Description
The legacy front-end (`dpcm_sampler/enhanced_drum_mapper.py`) deterministically sets the
noise mode bit ($400E bit 7) to 1 for hi-hats/cowbell via `METALLIC_NOISE_ROLES` (#204/
NH-29). The `--arranger` front-end's `DrumMapping` dataclass has no mode/periodic field at
all, so `arrange_for_nes`'s `data.get('mode', 0)` read can never see anything but the
default 0 — every `--arranger` percussion track renders as long-mode noise regardless of
GM drum role. Revises the 2026-07-19 arranger audit's "parity, not a regression" verdict,
since the legacy producer is deterministic per GM role, not rare/random.

## Location
- `arranger/gm_instruments.py:1191-1264` (`DrumMapping`, `GM_DRUM_MAP`)
- `arranger/voice_allocator.py:314-343`, `:456-461`
- `arranger/pipeline_integration.py:282-290`

## Impact
Every `--arranger` song with GM hi-hats/cowbell loses the intended metallic timbre —
audible quality regression vs. the legacy pipeline. Not a hardware-range violation;
workaround exists (use legacy mode).

## Suggested Fix
Add a `periodic: bool` (or `mode: int`) field to `DrumMapping`, set it on the four
hi-hat/cowbell entries, thread it through `_allocate_noise` → `process_song`'s noise
frame dict → `arrange_for_nes`'s existing `.get('mode', 0)` read (already wired to
consume it once produced).
