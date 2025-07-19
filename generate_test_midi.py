import mido
from mido import Message, MetaMessage, MidiFile, MidiTrack
import os

def create_test_midi_files():
    test_cases = {
        "simple_loop.mid": create_simple_loop,
        "tempo_changes.mid": create_tempo_changes,
        "multiple_tracks.mid": create_multiple_tracks,
        "complex_patterns.mid": create_complex_patterns,
        "short_loops.mid": create_short_loops,
        "long_composition.mid": create_long_composition
    }
    
    # Create test_midi directory if it doesn't exist
    if not os.path.exists("test_midi"):
        os.makedirs("test_midi")
    
    # Generate each test file
    for filename, creator_func in test_cases.items():
        mid = creator_func()
        mid.save(os.path.join("test_midi", filename))
        print(f"Created {filename}")

def create_simple_loop():
    """Creates a simple MIDI file with a clear repeating pattern."""
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)
    
    # Set initial tempo (120 BPM)
    track.append(MetaMessage('set_tempo', tempo=500000, time=0))
    
    # Simple repeating pattern: C4, E4, G4
    pattern = [(60, 64), (64, 64), (67, 64)]  # (note, velocity)
    
    # Repeat pattern 4 times
    for _ in range(4):
        for note, velocity in pattern:
            # Note on
            track.append(Message('note_on', note=note, velocity=velocity, time=480))
            # Note off
            track.append(Message('note_off', note=note, velocity=0, time=480))
    
    return mid

def create_tempo_changes():
    """Creates a MIDI file with tempo changes."""
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)
    
    # Start at 120 BPM (500000 microseconds per beat)
    track.append(MetaMessage('set_tempo', tempo=500000, time=0))
    
    # Add some notes
    track.append(Message('note_on', note=60, velocity=64, time=480))
    track.append(Message('note_off', note=60, velocity=0, time=480))
    
    # Change to 150 BPM (400000 microseconds per beat)
    track.append(MetaMessage('set_tempo', tempo=400000, time=0))
    
    track.append(Message('note_on', note=64, velocity=64, time=480))
    track.append(Message('note_off', note=64, velocity=0, time=480))
    
    # Change to 100 BPM (600000 microseconds per beat)
    track.append(MetaMessage('set_tempo', tempo=600000, time=0))
    
    track.append(Message('note_on', note=67, velocity=64, time=480))
    track.append(Message('note_off', note=67, velocity=0, time=480))
    
    return mid

def create_multiple_tracks():
    """Creates a MIDI file with multiple tracks playing different patterns."""
    mid = MidiFile()
    
    # Melody track
    melody = MidiTrack()
    mid.tracks.append(melody)
    melody.append(MetaMessage('set_tempo', tempo=500000, time=0))
    melody_pattern = [(60, 64), (64, 64), (67, 64)]
    
    # Bass track
    bass = MidiTrack()
    mid.tracks.append(bass)
    bass_pattern = [(48, 64), (52, 64)]
    
    # Add notes to melody track
    for note, velocity in melody_pattern * 4:
        melody.append(Message('note_on', note=note, velocity=velocity, time=480))
        melody.append(Message('note_off', note=note, velocity=0, time=480))
        
    # Add notes to bass track
    for note, velocity in bass_pattern * 6:
        bass.append(Message('note_on', note=note, velocity=velocity, time=640))
        bass.append(Message('note_off', note=note, velocity=0, time=640))
    
    return mid

def create_complex_patterns():
    """Creates a MIDI file with more complex musical patterns."""
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)
    
    # Set tempo
    track.append(MetaMessage('set_tempo', tempo=500000, time=0))
    
    # Complex pattern with varying note lengths
    pattern = [
        (60, 64, 240),  # C4, short
        (64, 64, 120),  # E4, shorter
        (67, 64, 120),  # G4, shorter
        (72, 64, 480),  # C5, long
        (71, 64, 240),  # B4, short
        (69, 64, 240),  # A4, short
    ]
    
    # Repeat pattern with variations
    for cycle in range(3):
        for i, (note, velocity, duration) in enumerate(pattern):
            # Add slight variation in velocity for each cycle
            vel = velocity + (cycle * 10) if velocity + (cycle * 10) <= 127 else velocity
            track.append(Message('note_on', note=note, velocity=vel, time=0))
            track.append(Message('note_off', note=note, velocity=0, time=duration))
    
    return mid

def create_short_loops():
    """Creates a MIDI file with short, repetitive loops."""
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)
    
    # Set tempo
    track.append(MetaMessage('set_tempo', tempo=500000, time=0))
    
    # Short pattern: C4, D4
    pattern = [(60, 64), (62, 64)]
    
    # Repeat many times
    for _ in range(8):
        for note, velocity in pattern:
            track.append(Message('note_on', note=note, velocity=velocity, time=240))
            track.append(Message('note_off', note=note, velocity=0, time=240))
    
    return mid

def create_long_composition():
    """Creates a longer MIDI file with multiple sections."""
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)
    
    # Set tempo
    track.append(MetaMessage('set_tempo', tempo=500000, time=0))
    
    # Section A - Major triad
    pattern_a = [(60, 64), (64, 64), (67, 64)]
    # Section B - Minor triad
    pattern_b = [(65, 64), (68, 64), (72, 64)]
    # Section C - Diminished
    pattern_c = [(62, 64), (65, 64), (68, 64)]
    
    # Play sequence: A A B A C A (classic song structure)
    all_patterns = []
    all_patterns.extend(pattern_a * 2)  # A A
    all_patterns.extend(pattern_b)      # B
    all_patterns.extend(pattern_a)      # A
    all_patterns.extend(pattern_c)      # C
    all_patterns.extend(pattern_a)      # A
    
    for note, velocity in all_patterns:
        track.append(Message('note_on', note=note, velocity=velocity, time=480))
        track.append(Message('note_off', note=note, velocity=0, time=480))
    
    return mid

def create_nested_loops():
    """Creates a MIDI file with nested loop structures."""
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)
    
    # Set tempo
    track.append(MetaMessage('set_tempo', tempo=500000, time=0))
    
    # Inner loop: C4, D4
    inner_pattern = [(60, 64), (62, 64)]
    # Outer pattern: Inner loop + E4
    
    for _ in range(4):  # Outer loop
        # Play inner pattern twice
        for _ in range(2):
            for note, velocity in inner_pattern:
                track.append(Message('note_on', note=note, velocity=velocity, time=240))
                track.append(Message('note_off', note=note, velocity=0, time=240))
        # Add E4
        track.append(Message('note_on', note=64, velocity=64, time=480))
        track.append(Message('note_off', note=64, velocity=0, time=480))
    
    return mid

if __name__ == "__main__":
    create_test_midi_files()
    print("All test MIDI files created successfully!")
