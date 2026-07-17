# Arpeggio Pattern Documentation

## Musical Reasoning and NES-Specific Considerations

### Basic Patterns

#### "up" Pattern: [C, E, G]
- Most common and natural arpeggio pattern
- Follows the harmonic series, creating a rising melodic line
- Perfect for establishing chord progression in NES music
- Low CPU overhead, great for fast passages

#### "down" Pattern: [G, E, C]
- Creates descending melodic motion
- Often used for dramatic or melancholic effects
- Common in classical and baroque music adaptations
- Good for ending phrases or creating resolution

#### "up_down" Pattern: [C, E, G, E]
- Creates a "wave" motion that's very pleasing to the ear
- Emphasizes the middle note (3rd of the chord)
- Popular in folk and classical guitar techniques
- Excellent for sustained chord sections on NES

#### "down_up" Pattern: [G, E, C, E, G]
- More complex pattern with emphasis on root and fifth
- Creates a "bouncing" effect
- Good for heroic or triumphant musical moments
- Longer pattern provides more harmonic richness

#### "random" Pattern: Deterministic shuffle of all notes
- Creates unpredictable-sounding, modern texture
- Useful for mysterious or atmospheric sections
- Avoids predictable melodic patterns
- Each note appears exactly once per cycle
- The order is **seeded from the chord's notes**, not truly random, so a given
  chord always arpeggiates the same way and ROM builds stay reproducible (#92)

### NES-Specific Considerations

- **Timing Constraints**: NES updates at 60Hz (16.67ms per frame), so arpeggio speed must align with frame boundaries
- **Channel Limitations**: Each channel is monophonic, making arpeggios essential for chord simulation
- **Memory Efficiency**: Shorter patterns use less ROM space and CPU cycles
- **Harmonic Context**: Pattern choice should complement the bass line and other channels
- **Style Matching**: Different patterns suit different musical genres (8-bit, classical adaptations, etc.)

### Pattern Selection Guidelines

- **Major Chords**: "up" or "up_down" for bright, cheerful sound
- **Minor Chords**: "down" or "down_up" for darker, more complex emotions  
- **Diminished**: "up_down" to emphasize tension and resolution
- **Augmented**: "random" or "down_up" to highlight the unusual harmonic structure
- **Power Chords**: "up" or "down" since only two notes are available

### Performance Tips

- Faster tempos work better with shorter patterns ("up", "down")
- Slower sections can use longer patterns ("down_up", "up_down")
- Consider the melody line when choosing arpeggio direction
- Use contrasting patterns between channels for textural interest

## Implementation Notes

Each pattern is designed to work within NES hardware constraints while providing maximum musical expressiveness. The pattern system allows for real-time arpeggio generation without requiring pre-computed sequences, saving both ROM space and processing time.

All five patterns are implemented once in `tracker/track_mapper.py`
(`apply_arpeggio_pattern`); the `--arranger` front-end's `ArpStyle` /
`VoiceAllocator._order_arp_notes` delegates to that same function so the two
front-ends never diverge (#92).

**Live-path note:** `arrange_for_nes` does not yet expose `arp_style`, so the
`--arranger` path currently always uses `up`. The other patterns are reachable
via the legacy front-end's chord/style selection (`get_arpeggio_pattern`) and by
constructing a `VoiceAllocator(arp_style=…)` directly.