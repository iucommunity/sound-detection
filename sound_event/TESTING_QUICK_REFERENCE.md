# Testing Quick Reference Guide

## Quick Start Testing Commands

### 1. Check Audio Device
```bash
# List available devices
python -c "import sounddevice as sd; print(sd.query_devices())"

# Test recording (Linux)
arecord -D hw:0,0 -c 4 -r 16000 -f S16_LE -d 5 test.wav

# Test recording (Python)
python scripts/record_multichannel.py test.wav --duration 5
```

### 2. Basic Functionality Test
```bash
# Record test audio
python scripts/record_multichannel.py test_0deg.wav --duration 10
# (Place source at 0° while recording)

# Process offline
python scripts/test_offline_file.py test_0deg.wav

# Check output - should show tracks around 0°
```

### 3. Real-Time Testing
```bash
# Run real-time DOA
python scripts/run_realtime.py

# Check logs in data/logs/doa_log_*.jsonl
```

### 4. Visualization
```bash
# Real-time SRP visualization
python scripts/visualize_srp.py
```

---

## Test Scenarios (Step-by-Step)

### Scenario 1: Single Static Source
1. Place speaker/phone at 0° (front of array)
2. Play white noise or speech
3. Record: `python scripts/record_multichannel.py test_0deg.wav --duration 10`
4. Process: `python scripts/test_offline_file.py test_0deg.wav`
5. **Check**: DOA should be 0° ± 5°

### Scenario 2: Multiple Static Sources
1. Place two sources at 45° and -45°
2. Play different signals (e.g., speech + music)
3. Record: `python scripts/record_multichannel.py test_multi.wav --duration 20`
4. Process: `python scripts/test_offline_file.py test_multi.wav`
5. **Check**: Two tracks, stable IDs, correct angles

### Scenario 3: Moving Source
1. Place source at 0°, slowly rotate to 90°
2. Record: `python scripts/record_multichannel.py test_moving.wav --duration 30`
3. Process: `python scripts/test_offline_file.py test_moving.wav`
4. **Check**: Single track follows movement smoothly

### Scenario 4: Real-Time Performance
1. Run: `python scripts/run_realtime.py`
2. Monitor CPU: `top` or Task Manager
3. Check FPS output in console
4. **Check**: FPS > 100, CPU < 50%, no crashes

---

## What to Look For

### ✅ Good Signs:
- DOA estimates are stable (low variance)
- Track IDs don't change
- Confidence increases over time
- No false tracks in silence
- Smooth tracking of moving sources

### ❌ Bad Signs:
- DOA jumps around randomly
- Track IDs swap between sources
- Many false tracks
- Tracks disappear/reappear frequently
- High CPU usage (> 80%)
- Crashes or memory leaks

---

## Common Issues & Quick Fixes

### Issue: No audio device found
**Fix**: Check device name in `config/audio.yaml`, try device index instead

### Issue: Wrong DOA angles
**Fix**: Check array orientation, adjust `orientation_offset_deg` in `config/ssl.yaml`

### Issue: Too many false tracks
**Fix**: Increase `min_power` in `config/ssl.yaml` or `pending_track_power_threshold` in `config/tracker.yaml`

### Issue: Tracks disappear quickly
**Fix**: Increase `death_frames` in `config/tracker.yaml`

### Issue: Tracks not created
**Fix**: Decrease `birth_frames` or `pending_track_power_threshold`

### Issue: Poor accuracy
**Fix**: Check geometry config, verify mic positions, calibrate speed of sound

---

## Performance Benchmarks

### Target Metrics:
- **FPS**: > 100 (ideally 150-200)
- **Latency**: < 100ms end-to-end
- **CPU**: < 50% single core
- **Memory**: Stable (no growth over time)
- **Accuracy**: < 5° error for static sources

### How to Measure:
```python
# Add to run_realtime.py or check logs
# FPS is already printed
# CPU: use system monitor
# Memory: use `memory_profiler` or system monitor
```

---

## Validation Checklist

Before considering production-ready:

- [ ] Single source: DOA error < 5°
- [ ] Two sources: Both tracked correctly
- [ ] Track IDs: Stable (no swapping)
- [ ] Real-time: FPS > 100
- [ ] Stability: 30+ min run without crashes
- [ ] Memory: No leaks
- [ ] Logs: Valid JSONL format
- [ ] Config: All parameters work

---

## Next Steps After Testing

1. **Document Results**: Record test outcomes
2. **Fix Issues**: Address any problems found
3. **Tune Parameters**: Optimize for your use case
4. **Create Test Suite**: Automate regression testing
5. **Update Documentation**: Add usage examples
6. **Version Tag**: Mark as production-ready

