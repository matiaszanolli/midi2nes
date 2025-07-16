from constants import FRAME_MS

class TempoMap:
    def __init__(self, initial_tempo=500000):  # 120 BPM default
        self.tempo_changes = [(0, initial_tempo)]  # (tick, tempo)
        self.ticks_per_beat = None

    def add_tempo_change(self, tick, tempo):
        self.tempo_changes.append((tick, tempo))
        self.tempo_changes.sort(key=lambda x: x[0])

    def get_tempo_at_tick(self, tick):
        # Find the active tempo for the given tick
        for i in range(len(self.tempo_changes) - 1):
            if self.tempo_changes[i][0] <= tick < self.tempo_changes[i + 1][0]:
                return self.tempo_changes[i][1]
        return self.tempo_changes[-1][1]
    

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
