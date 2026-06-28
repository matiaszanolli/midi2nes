# Unified Severity Definitions — MIDI2NES

This file is referenced by all audit skills. Do NOT use as a slash command.

**Severity is about IMPACT, not likelihood.** A rare but catastrophic bug (a ROM
that bricks on hardware) is CRITICAL, not MEDIUM.

## CRITICAL
Produces a broken/unplayable ROM or corrupts data, with no workaround.
- Generated ROM crashes the CPU or APU on real hardware / accurate emulators (bad reset/NMI/IRQ vectors at $FFFA–$FFFF).
- Music data overruns the mapper's PRG capacity silently (truncated/garbage playback).
- Pattern compression that decompresses to different music than the input (lossy where it claims lossless).
- Pipeline stage emits data a downstream stage parses as valid but means something else (silent contract corruption).
- Data loss: a MIDI event class dropped on the floor with no warning, changing the song.

## HIGH
Wrong output under realistic input, or fails on common MIDI files.
- Notes/timers written outside NES hardware range without clamping (wrong pitch, silent note).
- Triangle channel given a volume/duty it cannot honor (engine writes a register that does nothing or misbehaves).
- Frame timing drifts off the 60Hz grid over a song (tempo→frame accumulation error).
- Inter-stage JSON key mismatch that throws or silently yields empty output for valid input.
- Multiprocessing pattern detector raising on common input without the documented fallback firing.
- CC65 compile failure surfaced as "success" (return code / stderr ignored in `compiler/cc65_wrapper.py`).
- Mapper header / `nes.cfg` mismatch (header says one mapper, linker config another).

## MEDIUM
Incorrect behavior with a workaround, or defense-in-depth gaps.
- Suboptimal channel allocation in the arranger (playable but musically wrong voice dropped).
- Off-by-one in pattern length/reference offsets that still round-trips correctly but wastes space.
- Missing error handling on a recoverable path (bad config file, missing optional input).
- Compression ratio / stats reported inaccurately (cosmetic but misleading).
- Velocity→volume curve that under/over-shoots but stays in range.
- Bare `except` that hides a real but non-fatal error.

## LOW
Code quality, maintainability, hardening.
- Dead code, unused imports, stale TODO/FIXME, duplicated logic.
- Magic numbers that should reference a named NES constant or `docs/APU_*.md`.
- Missing/weak test coverage on a path that currently works.
- Doc-rot: a `docs/*.md` or docstring that contradicts the code.

## Special Rules

| Condition | Minimum Severity |
|-----------|-----------------|
| Bad reset/NMI/IRQ vector or APU never initialized in generated ROM | CRITICAL |
| Music data exceeds mapper PRG capacity without detection | CRITICAL |
| Pattern round-trip mismatch (compressed ≠ original playback) | CRITICAL |
| Pipeline stage JSON contract break (producer/consumer key drift) | HIGH |
| NES value emitted out of hardware range without clamp (note/volume/11-bit timer) | HIGH |
| Triangle channel written with volume/duty semantics | HIGH |
| Frame-timing drift off 60Hz over a song | HIGH |
| CC65 nonzero exit / stderr ignored | HIGH |
| Mapper header vs `nes.cfg` mismatch | HIGH |
| Multiprocessing crash without documented fallback to `EnhancedPatternDetector` | HIGH |
| `unsafe`-equivalent: `eval`/`exec`/shell-injection on user input | HIGH |
| Bare `except:` swallowing an error on a non-recoverable path | MEDIUM |
| Magic number where a `docs/APU_*.md`-backed constant exists | LOW |
| Reported compression/stat inaccurate (cosmetic) | MEDIUM |

> **NES-hardware rows** gate the boundary where Python numeric values become APU
> register writes — `nes/pitch_table.py`, `nes/envelope_processor.py`,
> `nes/emulator_core.py`, and the exporter that serializes them
> (`exporter/exporter_ca65.py`). A value wrong there is wrong on every ROM,
> so the floors above are HIGH/CRITICAL. Cite the relevant `docs/APU_*.md`.

## Decision Tree

```
Does the generated ROM fail to boot / crash the CPU or APU on hardware?
  → YES: CRITICAL (bad vectors, missing APU init, PRG overrun)
Does pattern compression change the music it decompresses to?
  → YES: CRITICAL (claims lossless, isn't)
Does a pipeline stage hand the next stage data that means something different than intended?
  → YES: at least HIGH (contract corruption); CRITICAL if it silently changes the song
Is a note/volume/timer written outside NES hardware range without clamping?
  → YES: at least HIGH
Is the Triangle channel driven with volume/duty it can't honor?
  → YES: at least HIGH
Does frame timing drift off the 60Hz grid over a song?
  → YES: at least HIGH
Is a CC65 nonzero exit or stderr ignored?
  → YES: at least HIGH
Does the mapper header disagree with nes.cfg / the project builder?
  → YES: at least HIGH
Does the multiprocessing detector crash on common input without the fallback firing?
  → YES: at least HIGH
Is it wrong output but with a workaround, or a swallowed non-fatal error?
  → YES: MEDIUM
Is it dead code / magic number / doc-rot / missing test on working code?
  → YES: LOW
Otherwise → MEDIUM
```
