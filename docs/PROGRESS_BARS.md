# Progress Bars in Pattern Detection

The MIDI2NES project now includes visual progress bars for long-running pattern detection operations, powered by the `tqdm` library.

## Features

### Parallel Pattern Detector
- **Progress Bar**: Shows "Processing pattern chunks" with chunk-based progress
- **Speed Display**: Shows processing speed in chunks/s
- **Pattern Counter**: Displays number of patterns found in real-time
- **Automatic Activation**: Appears when processing large MIDI files with multiple work chunks

Example output:
```
🚀 Starting parallel pattern detection with 7 workers
🔧 Created 236 work chunks for parallel processing
Processing pattern chunks: 100%|████████████| 236/236 [00:00<00:00, 1474.74chunk/s, patterns=5505]
📈 Found 5505 candidate patterns
✅ Parallel pattern detection completed in 0.26s
```

### Enhanced Pattern Detector
- **Progress Bar**: Shows "Finding patterns" with position-based progress
- **Speed Display**: Shows processing speed in positions/s
- **Candidate Counter**: Displays number of pattern candidates found
- **Smart Activation**: Only appears for large tasks (>1000 iterations)

Example output:
```
Finding patterns: 100%|█████████████████████| 5505/5505 [00:06<00:00, 794.53pos/s, candidates=5505]
```

## Technical Details

### Dependencies
- **tqdm**: Version 4.67.1 added to `requirements.txt`
- **Automatic Import**: Progress bars are imported only when needed

### Performance Impact
- **Minimal Overhead**: Progress bars only appear for computationally intensive tasks
- **Smart Thresholds**: 
  - Parallel detector: Always shows progress for chunk processing
  - Serial detector: Only shows progress for >1000 total iterations
- **Non-blocking**: Progress bars don't interfere with the actual processing

### Progress Information
- **Percentage**: Visual bar showing completion percentage
- **Speed**: Real-time processing speed
- **Time**: Elapsed time and estimated time remaining
- **Context**: Task-specific information (patterns found, candidates, etc.)

## Benefits

1. **User Feedback**: Clear indication that processing is active, not frozen
2. **Performance Monitoring**: Real-time speed metrics help identify performance issues
3. **Planning**: Time estimates help users plan workflow
4. **Debugging**: Progress information aids in performance tuning

## Implementation Notes

The progress bars are implemented with minimal code changes:
- **Parallel detector**: Wraps the `as_completed()` loop for chunk processing
- **Serial detector**: Wraps the nested pattern search loops with total iteration counting
- **Error handling**: Progress bars handle exceptions gracefully using `pbar.write()`
- **Threading safe**: Uses tqdm's thread-safe update mechanisms

The implementation maintains full backward compatibility - existing code continues to work unchanged, with progress bars appearing automatically for appropriate workloads.
