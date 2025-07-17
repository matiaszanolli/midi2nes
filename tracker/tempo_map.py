# File: tracker/tempo_map.py
from constants import FRAME_MS


class TempoMap:
    def __init__(self, initial_tempo=500000, ticks_per_beat=480):
        """
        Initialize TempoMap with default tempo (120 BPM = 500000 microseconds per beat)
        
        Args:
            initial_tempo: Microseconds per quarter note (500000 = 120 BPM)
            ticks_per_beat: MIDI ticks per quarter note
        """
        self.tempo_changes = [(0, initial_tempo)]  # (tick, tempo_microseconds)
        self.ticks_per_beat = ticks_per_beat
        self._time_cache = {}  # Cache for performance optimization
        
    def add_tempo_change(self, tick, tempo):
        """Add a tempo change at the specified tick"""
        self.tempo_changes.append((tick, tempo))
        self.tempo_changes.sort(key=lambda x: x[0])  # Keep sorted by tick
        self._time_cache = {}  # Clear cache when tempo changes
        
    def get_tempo_at_tick(self, tick):
        """Get the active tempo at a specific tick"""
        # Find the most recent tempo change before or at this tick
        active_tempo = self.tempo_changes[0][1]  # Default to initial tempo
        
        for change_tick, tempo in self.tempo_changes:
            if change_tick <= tick:
                active_tempo = tempo
            else:
                break
                
        return active_tempo
    
    def calculate_time_ms(self, start_tick, end_tick):
        """
        Calculate precise time in milliseconds between two ticks,
        accounting for all tempo changes in between
        """
        if start_tick == end_tick:
            return 0.0
            
        # Check cache first
        cache_key = (start_tick, end_tick)
        if cache_key in self._time_cache:
            return self._time_cache[cache_key]
            
        total_time_ms = 0.0
        current_tick = start_tick
        
        # Find all tempo changes between start and end ticks
        relevant_changes = [
            (tick, tempo) for tick, tempo in self.tempo_changes 
            if start_tick < tick <= end_tick
        ]
        
        # Process each tempo segment
        for change_tick, new_tempo in relevant_changes:
            # Calculate time for current segment
            current_tempo = self.get_tempo_at_tick(current_tick)
            segment_ticks = change_tick - current_tick
            segment_time_ms = self._ticks_to_ms(segment_ticks, current_tempo)
            total_time_ms += segment_time_ms
            current_tick = change_tick
            
        # Handle remaining ticks after last tempo change
        if current_tick < end_tick:
            current_tempo = self.get_tempo_at_tick(current_tick)
            remaining_ticks = end_tick - current_tick
            remaining_time_ms = self._ticks_to_ms(remaining_ticks, current_tempo)
            total_time_ms += remaining_time_ms
            
        # Cache the result
        self._time_cache[cache_key] = total_time_ms
        return total_time_ms
    
    def _ticks_to_ms(self, ticks, tempo_microseconds):
        """Convert ticks to milliseconds for a given tempo"""
        # tempo_microseconds is microseconds per quarter note
        # ticks_per_beat is ticks per quarter note
        microseconds_per_tick = tempo_microseconds / self.ticks_per_beat
        return (ticks * microseconds_per_tick) / 1000.0
    
    def get_frame_for_tick(self, tick):
        """Get the frame number for a specific tick"""
        time_ms = self.calculate_time_ms(0, tick)
        return int(time_ms / FRAME_MS)
    
    def get_tempo_bpm_at_tick(self, tick):
        """Get tempo in BPM at a specific tick"""
        tempo_microseconds = self.get_tempo_at_tick(tick)
        return 60_000_000 / tempo_microseconds  # Convert to BPM
    
    def get_debug_info(self):
        """Get debug information about tempo changes"""
        info = {
            "ticks_per_beat": self.ticks_per_beat,
            "tempo_changes": []
        }
        
        for tick, tempo in self.tempo_changes:
            bpm = 60_000_000 / tempo
            info["tempo_changes"].append({
                "tick": tick,
                "tempo_microseconds": tempo,
                "bpm": round(bpm, 2),
                "time_ms": self.calculate_time_ms(0, tick)
            })
            
        return info
    

def calculate_frame_time(tick, tempo_map):
    """
    Calculate precise frame timing considering tempo changes
    """
    current_time_us = 0
    current_tick = 0
    
    for change_tick, tempo in tempo_map.tempo_changes:
        if change_tick >= tick:
            break
            
        # Calculate time for this tempo segment
        segment_ticks = min(tick - current_tick, change_tick - current_tick)
        us_per_tick = tempo / tempo_map.ticks_per_beat
        current_time_us += segment_ticks * us_per_tick
        current_tick = change_tick
    
    return int(current_time_us / (FRAME_MS * 1000))
