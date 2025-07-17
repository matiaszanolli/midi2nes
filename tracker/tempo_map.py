from constants import FRAME_MS

class TempoMap:
    def __init__(self, initial_tempo=500000, ticks_per_beat=480):
        self.tempo_changes = [(0, initial_tempo)]
        self.ticks_per_beat = ticks_per_beat
        self._cache = {}  # For performance optimization

    def add_tempo_change(self, tick, tempo):
        self.tempo_changes.append((tick, tempo))
        self.tempo_changes.sort(key=lambda x: x[0])
        self._cache = {}  # Clear cache on tempo changes

    def get_tempo_at_tick(self, tick):
        if tick in self._cache:
            return self._cache[tick]

        for i in range(len(self.tempo_changes) - 1):
            if self.tempo_changes[i][0] <= tick < self.tempo_changes[i + 1][0]:
                self._cache[tick] = self.tempo_changes[i][1]
                return self.tempo_changes[i][1]
        
        self._cache[tick] = self.tempo_changes[-1][1]
        return self.tempo_changes[-1][1]

    def calculate_time_ms(self, start_tick, end_tick):
        """Calculate precise time between ticks considering tempo changes"""
        time_ms = 0
        current_tick = start_tick

        for change_tick, tempo in self.tempo_changes:
            if change_tick <= start_tick:
                continue
            if change_tick >= end_tick:
                break

            # Calculate time for this segment
            segment_ticks = change_tick - current_tick
            ms_per_tick = tempo / (self.ticks_per_beat * 1000)
            time_ms += segment_ticks * ms_per_tick
            current_tick = change_tick

        # Calculate remaining time
        final_tempo = self.get_tempo_at_tick(current_tick)
        remaining_ticks = end_tick - current_tick
        ms_per_tick = final_tempo / (self.ticks_per_beat * 1000)
        time_ms += remaining_ticks * ms_per_tick

        return time_ms
    

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
