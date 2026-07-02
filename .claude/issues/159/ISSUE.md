# NH-17: Bytecode engine never silences at end-of-stream — every channel's last note drones forever

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

## Description
Each channel's bytecode stream ends with the last *note* event followed by the `$FF`
terminator: `max_frame` is computed per channel from its own frames, all emitted
tone/noise frames have `volume >= 1`, and no trailing rest event is emitted. When the
engine fetches `$FF` it jumps to `@end_of_stream`, which performs **no hardware write**
and leaves `frame_wait = 0`, so every subsequent frame re-fetches the same `$FF`. The
channel's registers keep their last state: pulse `$4000 = duty|$30|vol` (length halted,
constant volume > 0), triangle `$4008 = $FF` (linear halt, continuous reload), noise
`$400C = $30|vol`. Per the length-counter doc, the halt flag means the hardware will
never silence them — the engine's own `@silence` blocks are the only silencer and they
are never reached again.

## Location
`nes/audio_engine.asm:193-195,540-543` (`$FF` -> `@end_of_stream` -> `@next_channel`, no
register write, `frame_wait` left 0); serializer `exporter/exporter_ca65.py:964,1041-1066,1163`
(per-channel loop ends at the channel's own last data frame; final flushed event is always
a note; stream ends `note … $FF`).

## Evidence
Trace: last note event -> `@is_note` sets `frame_wait = len-1` -> after it expires,
`@fetch_byte` reads `$FF` -> `@end_of_stream` -> `@next_channel`. No path writes `$30`/`$80`
to the channel. Direct-export mode is unaffected — it loops the whole song via the
`frame_counter` compare/reset (`exporter/exporter_ca65.py:351-363,776-788`).

## Impact
Default-mode ROMs: (a) any channel whose part ends before the others (e.g. an intro-only
melody line) drones its final note under the rest of the song; (b) at song end, the final
chord plus a constant noise hiss sustain indefinitely. Also the bytecode path never loops
the song (the spec's `$84 CMD_JUMP` "looping the song" is neither emitted nor implemented),
so the drone is permanent. Workaround: `--no-patterns`.

## Related
#83 (EXP-07: spec lists `$84 CMD_JUMP` the exporter never emits), NH-20.

## Hardware ref
`docs/APU_LENGTH_COUNTER_REFERENCE.md` §3 (halt flag set -> length counter never
decrements -> no hardware auto-silence) and §5 ("Software Note-Off: … the sequencer will
manually write a volume of 0 to the channel's control register (or `$80` to `$4008` for the
Triangle)" — exactly the write that is missing here); `docs/APU_PULSE_REFERENCE.md` §5 (a
pulse with nonzero constant volume, nonzero length, valid timer keeps outputting).

## Suggested Fix
On first `$FF` per channel, execute the channel's `@silence` write once (e.g. set
`current_note = 0` and fall into `@process_macros`, or emit an explicit trailing rest event
per channel in the serializer). Optionally implement/emit a song loop instead of halting.

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
