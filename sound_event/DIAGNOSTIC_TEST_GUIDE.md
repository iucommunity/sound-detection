# Diagnostic Test Guide

## Quick Start

```bash
# Run test (press Ctrl+C to stop)
python scripts/test_realtime_diagnostic.py

# Run for specific duration (e.g., 30 seconds)
python scripts/test_realtime_diagnostic.py --duration 30

# Run with verbose output (see each frame)
python scripts/test_realtime_diagnostic.py --verbose

# Specify output directory
python scripts/test_realtime_diagnostic.py --output-dir my_test_logs
```

## Output Files

The script creates three log files in `data/diagnostic_logs/` (or your specified directory):

### 1. `diagnostic_TIMESTAMP.txt`
**Purpose**: General diagnostic messages and summary

**Contains**:
- Test start/stop times
- Configuration information
- Status updates during test
- Final summary statistics
- Any errors or warnings

**Use for**: Overall test status, configuration verification, error detection

---

### 2. `frames_TIMESTAMP.txt`
**Purpose**: Detailed per-frame information

**Format**:
```
frame_idx | n_candidates | n_tracks | track_details | srp_max | proc_time_ms
```

**Example**:
```
     123 | cands= 2 | tracks= 1 | ID1:θ=  45.2° age= 10 hits=  8 misses= 2 conf=0.75 | srp_max= 0.234 | proc= 2.45ms
     124 | cands= 2 | tracks= 1 | ID1:θ=  45.5° age= 11 hits=  9 misses= 0 conf=0.82 | srp_max= 0.256 | proc= 2.38ms
     125 | cands= 0 | tracks= 1 | ID1:θ=  45.8° age= 12 hits=  9 misses= 1 conf=0.75 | srp_max= 0.089 | proc= 2.41ms
```

**Fields**:
- `frame_idx`: STFT frame index
- `cands`: Number of DOA candidates from peak extractor
- `tracks`: Number of active tracks
- `track_details`: For each track:
  - `ID#`: Track identifier
  - `θ=`: Azimuth angle in degrees
  - `age=`: Track age (frames since creation)
  - `hits=`: Number of detections assigned to track
  - `misses=`: Consecutive frames without detection
  - `conf=`: Track confidence (0.0-1.0)
- `srp_max`: Maximum SRP-PHAT power value
- `proc`: Processing time in milliseconds

**Use for**: 
- Detailed frame-by-frame analysis
- Track behavior analysis
- Performance profiling
- Debugging specific issues

---

### 3. `summary_TIMESTAMP.yaml`
**Purpose**: Summary statistics in YAML format

**Contains**:
```yaml
total_frames: 1500
frames_with_detections: 1200
frames_with_tracks: 1100
frames_silent: 300
detection_rate: 0.8
track_rate: 0.733
total_tracks_created: 5
total_tracks_removed: 2
max_tracks_simultaneous: 2
avg_track_age: 45.2
max_track_age: 120
avg_confidence: 0.78
min_confidence: 0.45
max_confidence: 0.95
avg_srp_power: 0.234
max_srp_power: 0.567
avg_processing_time_ms: 2.45
max_processing_time_ms: 5.23
config:
  sample_rate: 16000
  stft_frame_size: 320
  # ... full configuration
```

**Use for**: 
- Quick performance assessment
- Comparing different test runs
- Automated analysis
- Configuration impact analysis

---

### 4. `doa_log_TIMESTAMP.jsonl`
**Purpose**: Standard DOA log in JSONL format (same as run_realtime.py)

**Use for**: Integration with other analysis tools

---

## What to Look For

### ✅ Good Signs

1. **Stable Tracking**
   - Track IDs remain constant (no swapping)
   - Track confidence increases over time
   - Tracks have high hit rates (hits/age > 0.7)

2. **Performance**
   - FPS > 100 (ideally 150-200)
   - Processing time < 10ms per frame
   - No frame drops

3. **Detection Quality**
   - Detection rate > 0.5 (at least 50% of frames have detections when sound present)
   - SRP power > 0.1 for active sources
   - Reasonable number of tracks (1-3 for typical scenarios)

4. **Track Lifecycle**
   - Tracks created when sources appear
   - Tracks removed when sources disappear
   - Track lifetimes match source durations

### ❌ Warning Signs

1. **Track Instability**
   - Track IDs changing frequently (ID swapping)
   - Tracks disappearing/reappearing rapidly
   - Low confidence values (< 0.3)

2. **Performance Issues**
   - FPS < 50
   - Processing time > 20ms
   - Frame drops or buffer underruns

3. **Detection Problems**
   - Very low detection rate (< 0.2) when sound is present
   - Many false tracks (tracks in silence)
   - SRP power always very low (< 0.01)

4. **Configuration Issues**
   - Too many tracks created (check max_sources, min_power)
   - Tracks not created (check birth_frames, pending_track_power_threshold)
   - Tracks die too quickly (check death_frames)

---

## Diagnostic Scenarios

### Scenario 1: No Tracks Created
**Symptoms**: `frames_with_tracks = 0` or very low

**Check**:
1. Are there detections? (`frames_with_detections`)
2. SRP power values (`avg_srp_power`, `max_srp_power`)
3. Configuration:
   - `min_power` too high?
   - `birth_frames` too high?
   - `pending_track_power_threshold` too high?

**Fix**: Lower thresholds in `config/ssl.yaml` and `config/tracker.yaml`

---

### Scenario 2: Too Many False Tracks
**Symptoms**: Many tracks created, low confidence, tracks in silence

**Check**:
1. `total_tracks_created` vs actual sources
2. Track confidence values
3. SRP power in silent frames

**Fix**: 
- Increase `min_power` in `config/ssl.yaml`
- Increase `pending_track_power_threshold` in `config/tracker.yaml`
- Increase `birth_frames` in `config/tracker.yaml`

---

### Scenario 3: Track ID Swapping
**Symptoms**: Track IDs change when sources are stable

**Check**:
- Look at `frames_TIMESTAMP.txt` - do track IDs change?
- Are tracks crossing paths?

**Fix**:
- Increase `gate_deg` in `config/tracker.yaml`
- Check if sources are too close together
- Verify array geometry is correct

---

### Scenario 4: Poor DOA Accuracy
**Symptoms**: Tracks at wrong angles

**Check**:
1. Array geometry (`config/array_geometry.yaml`)
2. Orientation offset (`config/ssl.yaml` → `orientation_offset_deg`)
3. Speed of sound (temperature dependent)

**Fix**:
- Verify mic positions match physical array
- Adjust `orientation_offset_deg` to match physical mounting
- Calibrate speed of sound if needed

---

### Scenario 5: Performance Issues
**Symptoms**: Low FPS, high processing time

**Check**:
- `avg_processing_time_ms` and `max_processing_time_ms`
- CPU usage
- System load

**Fix**:
- Reduce `azimuth_res_deg` (coarser grid)
- Reduce `fft_size` if possible
- Check for other processes using CPU

---

## Analyzing Logs

### Quick Analysis Commands

```bash
# Count total frames
grep -c "^[[:space:]]*[0-9]" frames_*.txt

# Find frames with multiple tracks
grep "tracks=[2-9]" frames_*.txt

# Find high-confidence tracks
grep "conf=0\.[89]" frames_*.txt

# Find processing time spikes
awk -F'proc=' '{print $2}' frames_*.txt | sort -n | tail -20

# Track lifetime analysis (count unique track IDs)
grep -o "ID[0-9]*" frames_*.txt | sort -u | wc -l
```

### Python Analysis Script (Example)

```python
import re
from collections import defaultdict

# Parse frame log
track_lifetimes = defaultdict(int)
with open("frames_TIMESTAMP.txt") as f:
    for line in f:
        if "ID" in line:
            # Extract track IDs
            track_ids = re.findall(r"ID(\d+)", line)
            for tid in track_ids:
                track_lifetimes[tid] += 1

# Analyze
print(f"Total unique tracks: {len(track_lifetimes)}")
print(f"Average lifetime: {sum(track_lifetimes.values()) / len(track_lifetimes):.1f} frames")
```

---

## Test Scenarios

### Test 1: Single Static Source
```bash
# Place source at 0° (front)
python scripts/test_realtime_diagnostic.py --duration 30 --verbose
```

**Expected**:
- 1 track with stable ID
- DOA around 0° ± 5°
- High confidence (> 0.7)
- Stable angle (low variance)

---

### Test 2: Two Static Sources
```bash
# Place sources at 45° and -45°
python scripts/test_realtime_diagnostic.py --duration 30
```

**Expected**:
- 2 tracks with stable IDs
- DOAs around ±45° ± 5°
- Both tracks maintained
- No ID swapping

---

### Test 3: Moving Source
```bash
# Slowly rotate source from 0° to 90°
python scripts/test_realtime_diagnostic.py --duration 60
```

**Expected**:
- 1 track maintained throughout
- Smooth angle progression
- Track follows movement
- No track loss

---

### Test 4: Performance Test
```bash
# Run for 5 minutes, check stability
python scripts/test_realtime_diagnostic.py --duration 300
```

**Expected**:
- Stable FPS throughout
- No memory leaks (check system monitor)
- No crashes
- Consistent processing time

---

## Troubleshooting

### Audio Device Not Found
```
ERROR: Failed to open audio device 'ReSpeaker'
```
**Fix**: 
- Check device name in `config/audio.yaml`
- List devices: `python -c "import sounddevice as sd; print(sd.query_devices())"`
- Use device index instead of name

### Configuration Errors
```
ERROR: Failed to load configuration
```
**Fix**: 
- Check all YAML files in `config/` are valid
- Verify all required fields are present
- Check file paths are correct

### Low FPS
**Possible causes**:
- CPU overloaded
- Block size too small
- Azimuth resolution too fine
- Other processes running

**Fix**: 
- Close other applications
- Increase `block_size` in `config/audio.yaml`
- Reduce `azimuth_res_deg` in `config/ssl.yaml`

---

## Next Steps After Testing

1. **Review Summary Statistics**
   - Check if metrics meet expectations
   - Compare with target values

2. **Analyze Frame Logs**
   - Look for patterns
   - Identify issues
   - Verify track behavior

3. **Adjust Configuration**
   - Tune parameters based on results
   - Re-test with new settings

4. **Document Findings**
   - Record test conditions
   - Note any issues
   - Document optimal settings

---

## Sharing Logs for Diagnosis

When asking for help, provide:
1. `summary_TIMESTAMP.yaml` - Quick overview
2. Sample from `frames_TIMESTAMP.txt` - Detailed behavior
3. Relevant section from `diagnostic_TIMESTAMP.txt` - Errors/warnings
4. Configuration files (if modified)
5. Test conditions (source positions, duration, etc.)

