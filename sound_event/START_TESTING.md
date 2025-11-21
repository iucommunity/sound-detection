# Step-by-Step Testing Guide

## Prerequisites Check

Before starting, ensure:
- [ ] ReSpeaker 4-Mic v3.0 is connected via USB
- [ ] Device is recognized by your system
- [ ] Python environment is set up with all dependencies

---

## Phase 1: Quick Verification (5 minutes)

### Step 1.1: Verify Audio Device & Channel Mapping

```bash
# Check if device is detected
python -c "import sounddevice as sd; print(sd.query_devices())"
```

**Expected**: You should see your ReSpeaker device listed with 6+ input channels.

### Step 1.2: Test Channel Mapping (ReSpeaker 6-channel)

```bash
# Record a short test (5 seconds)
python scripts/record_multichannel.py test_channels.wav --duration 5
```

**What to check**:
- Script should start without errors
- Should capture 6 channels from device
- Should select CH1-CH4 for processing
- Output WAV file should have 4 channels

**If errors occur**:
- Check `config/audio.yaml` - verify `device` name matches your system
- Try using device index instead of name (e.g., `device: 0`)
- Verify ReSpeaker firmware provides 6 channels

### Step 1.3: Quick Real-Time Test

```bash
# Run real-time DOA (press Ctrl+C after 10 seconds)
python scripts/run_realtime.py
```

**What to check**:
- No errors on startup
- Console shows FPS > 100
- Tracks appear when you make noise
- Angles are displayed in 0-360° range

**Expected output format**:
```
[Frame    123] Track ID 1: θ=  45.2° (confidence: 0.75)
```

---

## Phase 2: Basic Functionality (15 minutes)

### Step 2.1: Single Static Source Test

**Setup**:
1. Place a speaker/phone at **0°** (front of array, aligned with mic 1 at 45°)
2. Play white noise or speech at moderate volume

**Test**:
```bash
# Record 10 seconds
python scripts/record_multichannel.py test_0deg.wav --duration 10

# Process offline
python scripts/test_offline_file.py test_0deg.wav
```

**Expected Results**:
- DOA estimates should be around **0° ± 5°** (or 360° ± 5°)
- Track should be stable (low variance)
- Confidence should increase over time

**Check output**:
- Look at the console output for DOA angles
- Verify angles are in **0-360° range** (not -180 to 180)
- Track ID should remain constant

### Step 2.2: Test at Different Angles

**Test at 90°, 180°, 270°**:

```bash
# Place source at 90° (right side)
python scripts/record_multichannel.py test_90deg.wav --duration 10
python scripts/test_offline_file.py test_90deg.wav

# Place source at 180° (back)
python scripts/record_multichannel.py test_180deg.wav --duration 10
python scripts/test_offline_file.py test_180deg.wav

# Place source at 270° (left side)
python scripts/record_multichannel.py test_270deg.wav --duration 10
python scripts/test_offline_file.py test_270deg.wav
```

**Expected Results**:
- 90° test: DOA around **90° ± 5°**
- 180° test: DOA around **180° ± 5°**
- 270° test: DOA around **270° ± 5°**

**If angles are wrong**:
- Check `config/array_geometry.yaml` - mic positions should be correct
- Verify mic orientation (which direction is "0°"?)
- Adjust `orientation_offset_deg` in `config/ssl.yaml` if needed

### Step 2.3: Verify 0-360° Range

**Check that all outputs use 0-360° range**:

```bash
# Run real-time and check console output
python scripts/run_realtime.py
```

**What to verify**:
- All displayed angles are between 0 and 360
- No negative angles (except possibly -0.0 which is fine)
- Angles wrap correctly (e.g., 359° + 2° = 1°, not -1°)

---

## Phase 3: Advanced Scenarios (30 minutes)

### Step 3.1: Multiple Static Sources

**Setup**:
1. Place two sources at different angles (e.g., 45° and 225°)
2. Play different signals (e.g., speech + music)

**Test**:
```bash
python scripts/record_multichannel.py test_multi.wav --duration 20
python scripts/test_offline_file.py test_multi.wav
```

**Expected Results**:
- Two tracks with different IDs
- Track IDs remain stable (no swapping)
- Each track corresponds to correct source angle
- Both tracks have reasonable confidence

### Step 3.2: Moving Source

**Setup**:
1. Place source at 0°
2. Slowly rotate source to 90° over 30 seconds

**Test**:
```bash
python scripts/record_multichannel.py test_moving.wav --duration 30
python scripts/test_offline_file.py test_moving.wav
```

**Expected Results**:
- Single track follows movement smoothly
- No track ID changes
- Angular velocity should be reasonable (not jumping)

### Step 3.3: Real-Time Performance

**Test**:
```bash
# Run for 5 minutes, monitor performance
python scripts/run_realtime.py
```

**Monitor**:
- **FPS**: Should be > 100 (ideally 150-200)
- **CPU**: Should be < 50% single core
- **Memory**: Should remain stable (no growth)
- **Stability**: No crashes or errors

**Check logs**:
```bash
# View latest log
ls -lt data/logs/doa_log_*.jsonl | head -1
```

---

## Phase 4: Comprehensive Diagnostic Test

### Step 4.1: Run Full Diagnostic

```bash
# Run comprehensive diagnostic (30 seconds)
python scripts/test_realtime_diagnostic.py --duration 30

# Or run with verbose output
python scripts/test_realtime_diagnostic.py --duration 30 --verbose
```

**Output files** (in `data/diagnostic_logs/`):
- `diagnostic_TIMESTAMP.txt` - Summary and status
- `frames_TIMESTAMP.txt` - Per-frame details
- `summary_TIMESTAMP.yaml` - Final statistics

**What to check**:
- All statistics are reasonable
- No errors or warnings
- FPS meets targets
- Track stability metrics are good

### Step 4.2: Visual Verification

```bash
# Run SRP visualization
python scripts/visualize_srp.py
```

**What to observe**:
- Polar plot shows energy peaks
- Peaks move as you move around the array
- Peaks should be at correct angles (0-360°)
- No artifacts or strange patterns

---

## Phase 5: Validation Checklist

Before considering production-ready, verify:

### Channel Mapping
- [ ] System captures 6 channels from ReSpeaker
- [ ] Only CH1-CH4 are used for DOA
- [ ] No errors related to channel count

### Azimuth Range (0-360°)
- [ ] All displayed angles are 0-360°
- [ ] Angles match physical source positions
- [ ] Wrapping works correctly (359° + 2° = 1°)

### Basic Functionality
- [ ] Single source: DOA error < 5°
- [ ] Multiple sources: Both tracked correctly
- [ ] Track IDs: Stable (no swapping)
- [ ] Confidence: Increases over time

### Performance
- [ ] Real-time: FPS > 100
- [ ] CPU: < 50% single core
- [ ] Memory: Stable (no leaks)
- [ ] Stability: 30+ min run without crashes

### Edge Cases
- [ ] No false tracks in silence
- [ ] Tracks handle source disappearance gracefully
- [ ] System recovers from temporary audio glitches

---

## Troubleshooting

### Issue: "No audio device found"
**Solution**:
1. Check `config/audio.yaml` - verify device name
2. Try device index: `device: 0` instead of name
3. List devices: `python -c "import sounddevice as sd; print(sd.query_devices())"`

### Issue: Wrong DOA angles
**Solution**:
1. Verify mic positions in `config/array_geometry.yaml`
2. Check physical orientation of array
3. Adjust `orientation_offset_deg` in `config/ssl.yaml`

### Issue: Too many false tracks
**Solution**:
1. Increase `min_power` in `config/ssl.yaml`
2. Increase `pending_track_power_threshold` in `config/tracker.yaml`
3. Increase `pending_track_max_age` in `config/tracker.yaml`

### Issue: Tracks disappear quickly
**Solution**:
1. Increase `death_frames` in `config/tracker.yaml`
2. Decrease `gate_deg` if source is moving

### Issue: Poor accuracy
**Solution**:
1. Verify geometry configuration
2. Check speed of sound (343.0 m/s at 20°C)
3. Ensure source is far-field (> 1m from array)
4. Reduce background noise

---

## Next Steps

After successful testing:

1. **Document Results**: Record test outcomes and any issues found
2. **Tune Parameters**: Optimize for your specific use case
3. **Create Test Suite**: Automate regression testing
4. **Update Documentation**: Add usage examples and known issues
5. **Version Tag**: Mark as production-ready

---

## Quick Command Reference

```bash
# List audio devices
python -c "import sounddevice as sd; print(sd.query_devices())"

# Record test audio
python scripts/record_multichannel.py output.wav --duration 10

# Process offline file
python scripts/test_offline_file.py input.wav

# Run real-time DOA
python scripts/run_realtime.py

# Run diagnostic test
python scripts/test_realtime_diagnostic.py --duration 30

# Visualize SRP
python scripts/visualize_srp.py

# View latest log
ls -lt data/logs/doa_log_*.jsonl | head -1
cat $(ls -t data/logs/doa_log_*.jsonl | head -1) | tail -20
```

