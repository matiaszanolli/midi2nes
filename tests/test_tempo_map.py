# File: test_tempo_map.py (for testing)
from tracker.tempo_map import TempoMap

def test_basic_tempo_map():
    """Test basic tempo map functionality"""
    tempo_map = TempoMap(initial_tempo=500000, ticks_per_beat=480)  # 120 BPM
    
    # Test basic tempo retrieval
    assert tempo_map.get_tempo_at_tick(0) == 500000
    assert tempo_map.get_tempo_bpm_at_tick(0) == 120.0
    
    # Add a tempo change at tick 960 (2 beats at 480 tpqn)
    tempo_map.add_tempo_change(960, 375000)  # 160 BPM
    
    # Test tempo retrieval before and after change
    assert tempo_map.get_tempo_at_tick(500) == 500000  # Still 120 BPM
    assert tempo_map.get_tempo_at_tick(1000) == 375000  # Now 160 BPM
    assert abs(tempo_map.get_tempo_bpm_at_tick(1000) - 160.0) < 0.1
    
    # Test time calculations
    time_1_beat = tempo_map.calculate_time_ms(0, 480)  # 1 beat at 120 BPM
    assert abs(time_1_beat - 500.0) < 1.0  # Should be ~500ms
    
    print("✅ Basic tempo map tests passed!")
    print(f"Debug info: {tempo_map.get_debug_info()}")

if __name__ == "__main__":
    test_basic_tempo_map()
