# Verification Plan: Pre-Production Testing

## Overview
This document outlines a comprehensive verification plan to ensure all modules work correctly in theory and practice before releasing as production-ready.

---

## Phase 1: Unit Testing & Module Verification

### 1.1 Geometry & TDOA Module
**Files to test**: `src/my_doa/geometry/array_geometry.py`, `src/my_doa/geometry/tdoa_lut.py`

**Verification Steps**:
1. **Array Geometry Loading**
   - [ ] Load `config/array_geometry.yaml` successfully
   - [ ] Verify mic positions are correct (4 mics at 45°, 135°, 225°, 315°)
   - [ ] Check inter-mic distances match expected values (~32.3mm for ReSpeaker)
   - [ ] Verify speed of sound is 343.0 m/s

2. **TDOA LUT Precomputation**
   - [ ] Verify TDOA values are symmetric: `tau_ij ≈ -tau_ji`
   - [ ] Check TDOA range is within physical limits (max delay = aperture / c)
   - [ ] Verify fractional delays are computed correctly
   - [ ] Test with different azimuth resolutions (0.5°, 1.0°, 2.0°)

3. **Edge Cases**
   - [ ] Test with invalid geometry (duplicate mic IDs, wrong dimensions)
   - [ ] Test with extreme azimuth angles (-180°, 180°)
   - [ ] Verify circular wrapping works correctly

**Expected Results**:
- All mic pairs (6 pairs for 4 mics) have valid TDOA values
- TDOA values match theoretical calculations for far-field model
- No NaN or Inf values in LUT

---

### 1.2 STFT Module
**Files to test**: `src/my_doa/dsp/stft.py`

**Verification Steps**:
1. **Basic STFT**
   - [ ] Test with known sine wave input
   - [ ] Verify frequency bins match expected frequencies
   - [ ] Check window function is applied correctly (Hann window)
   - [ ] Verify FFT size and frame size relationships

2. **Streaming Behavior**
   - [ ] Test with multiple consecutive blocks
   - [ ] Verify overlap-add behavior (50% overlap with hop_size = frame_size/2)
   - [ ] Check buffer management (no memory leaks)
   - [ ] Test with varying block sizes

3. **Multichannel Processing**
   - [ ] Verify all 4 channels are processed independently
   - [ ] Check output shape: (n_mics, n_freq_bins)
   - [ ] Test with different channel counts

4. **Edge Cases**
   - [ ] Empty blocks
   - [ ] Blocks smaller than frame_size
   - [ ] Very long continuous streams
   - [ ] Reset functionality

**Expected Results**:
- STFT output matches reference implementation (e.g., librosa)
- No phase discontinuities between frames
- Memory usage remains stable over long runs

---

### 1.3 MCRA Noise Estimation
**Files to test**: `src/my_doa/dsp/mcra.py`

**Verification Steps**:
1. **Noise Tracking**
   - [ ] Test with pure noise input (white noise)
   - [ ] Verify noise estimate converges to actual noise level
   - [ ] Check adaptation speed (alpha_s parameter)
   - [ ] Test with stationary noise

2. **Speech Presence Detection**
   - [ ] Test with speech + noise mixture
   - [ ] Verify noise estimate doesn't increase during speech
   - [ ] Check minima tracking window behavior
   - [ ] Test with varying SNR levels

3. **Initialization**
   - [ ] First frame initialization
   - [ ] Reset functionality
   - [ ] Stability with very low input levels

**Expected Results**:
- Noise estimate tracks stationary noise accurately
- Noise estimate remains stable during speech
- No NaN or Inf values
- Smooth adaptation without sudden jumps

---

### 1.4 GCC-PHAT Module
**Files to test**: `src/my_doa/dsp/gcc_phat.py`

**Verification Steps**:
1. **Basic GCC-PHAT**
   - [ ] Test with known delay between two signals
   - [ ] Verify peak location matches expected delay
   - [ ] Check PHAT weighting (magnitude normalization)
   - [ ] Verify all 6 mic pairs are computed

2. **Band-Limiting**
   - [ ] Test with band_bins parameter (300-4000 Hz)
   - [ ] Verify frequencies outside band are zeroed
   - [ ] Check edge cases (band outside valid range)

3. **Fractional Delays**
   - [ ] Test with sub-sample delays
   - [ ] Verify interpolation accuracy
   - [ ] Check fftshift behavior (zero delay at center)

4. **Edge Cases**
   - [ ] Silent input (all zeros)
   - [ ] Identical signals (zero delay)
   - [ ] Very large delays (near array limits)
   - [ ] NaN/Inf handling

**Expected Results**:
- GCC-PHAT peak location matches true TDOA within 1 sample
- All pairs produce valid correlation functions
- No artifacts or spurious peaks

---

### 1.5 SRP-PHAT Scanner
**Files to test**: `src/my_doa/doa/srp_scan.py`

**Verification Steps**:
1. **Spatial Scanning**
   - [ ] Test with single source at known angle
   - [ ] Verify SRP peak is at correct azimuth
   - [ ] Check power distribution across azimuth grid
   - [ ] Test with multiple sources (2-3 sources)

2. **TDOA Integration**
   - [ ] Verify fractional delay interpolation
   - [ ] Check all mic pairs contribute correctly
   - [ ] Test with different azimuth resolutions

3. **Edge Cases**
   - [ ] No sources (silence)
   - [ ] Sources at ±180° (wrapping)
   - [ ] Very close sources (< 10° apart)
   - [ ] Sources at array nulls

**Expected Results**:
- SRP peak location matches true source angle within ±2°
- Power distribution is smooth (no artifacts)
- Multiple sources produce multiple peaks

---

### 1.6 Peak Extractor
**Files to test**: `src/my_doa/doa/peak_extractor.py`

**Verification Steps**:
1. **Single Peak Extraction**
   - [ ] Test with single clear peak
   - [ ] Verify peak location accuracy
   - [ ] Check power threshold (min_power)

2. **Multi-Peak Extraction**
   - [ ] Test with 2-3 sources
   - [ ] Verify all peaks are found
   - [ ] Check suppression_deg parameter (no duplicate peaks)
   - [ ] Verify max_sources limit

3. **Circular Suppression**
   - [ ] Test peaks near ±180° boundary
   - [ ] Verify circular distance calculation
   - [ ] Check suppression doesn't affect distant peaks

4. **Edge Cases**
   - [ ] Flat SRP (no peaks)
   - [ ] All peaks below threshold
   - [ ] Peaks very close together (< suppression_deg)

**Expected Results**:
- All valid peaks are extracted
- No duplicate detections for same source
- Peak locations match SRP maxima within grid resolution

---

### 1.7 Tracker Module
**Files to test**: `src/my_doa/doa/tracker.py`

**Verification Steps**:
1. **Single Track**
   - [ ] Test track creation (birth_frames)
   - [ ] Verify Kalman prediction/update
   - [ ] Check angle wrapping
   - [ ] Test track death (death_frames)

2. **Multi-Track**
   - [ ] Test with 2-3 simultaneous tracks
   - [ ] Verify correct association (nearest neighbor)
   - [ ] Check track IDs remain stable
   - [ ] Test track crossing scenarios

3. **Confidence Metric**
   - [ ] Verify confidence increases with age
   - [ ] Check confidence decreases with misses
   - [ ] Test confidence range [0.0, 1.0]
   - [ ] Verify confidence in as_dict() output

4. **Pending Tracks**
   - [ ] Test pending track creation (power threshold)
   - [ ] Verify pending track aging
   - [ ] Check pending_track_max_age removal
   - [ ] Test promotion to full track

5. **Edge Cases**
   - [ ] Rapid source movement
   - [ ] Source disappearing/reappearing
   - [ ] Tracks crossing (180° → -180°)
   - [ ] Very low power detections

**Expected Results**:
- Tracks maintain stable IDs
- Track estimates are smooth (Kalman filtering works)
- Confidence reflects track quality
- No track ID swapping

---

## Phase 2: Integration Testing

### 2.1 End-to-End Pipeline
**Files to test**: `src/my_doa/pipeline/doa_pipeline.py`

**Verification Steps**:
1. **Full Pipeline Flow**
   - [ ] Test with synthetic multichannel audio
   - [ ] Verify all stages execute in correct order
   - [ ] Check output format matches specification
   - [ ] Test with different block sizes

2. **Configuration Loading**
   - [ ] Test with all config files present
   - [ ] Verify defaults are applied correctly
   - [ ] Test with missing optional configs
   - [ ] Check parameter validation

3. **State Management**
   - [ ] Test reset() functionality
   - [ ] Verify frame_index increments correctly
   - [ ] Check state persistence across blocks

4. **SNR Masking**
   - [ ] Test with use_snr_mask enabled/disabled
   - [ ] Verify frequency bin weighting
   - [ ] Check threshold parameters (low_db, high_db)

**Expected Results**:
- Pipeline processes audio without errors
- Output contains all required fields
- Performance is real-time capable (>100 FPS)

---

### 2.2 Audio I/O Integration
**Files to test**: `src/my_doa/audio/audio_io.py`, `scripts/run_realtime.py`

**Verification Steps**:
1. **Device Detection**
   - [ ] List available audio devices
   - [ ] Verify ReSpeaker device is detected
   - [ ] Test device selection (by name/index)
   - [ ] Check channel count validation

2. **Real-Time Capture**
   - [ ] Test audio stream start/stop
   - [ ] Verify block size consistency
   - [ ] Check sample rate matching (16 kHz)
   - [ ] Test with different block sizes

3. **Callback Performance**
   - [ ] Measure callback latency
   - [ ] Check for buffer underruns
   - [ ] Verify mailbox pattern works
   - [ ] Test with high CPU load

4. **Error Handling**
   - [ ] Test with invalid device
   - [ ] Test device disconnection
   - [ ] Check graceful shutdown

**Expected Results**:
- Audio capture works reliably
- No buffer underruns
- Latency < 50ms
- Graceful error handling

---

## Phase 3: Real-World Device Testing

### 3.1 Hardware Setup Verification
**Prerequisites**:
- [ ] ReSpeaker Mic Array v3.0 connected via USB
- [ ] Device recognized by OS (check `lsusb` or Device Manager)
- [ ] Test audio playback/recording works
- [ ] Verify 4 channels are available

**Initial Checks**:
```bash
# Linux
arecord -l  # List audio devices
arecord -D hw:0,0 -c 4 -r 16000 -f S16_LE test.wav  # Test recording

# Or use Python
python -c "import sounddevice as sd; print(sd.query_devices())"
```

---

### 3.2 Calibration & Geometry Verification

**Test 1: Physical Array Geometry**
- [ ] Measure actual mic positions (if possible)
- [ ] Verify mic spacing matches config (32.3mm radius)
- [ ] Check array is planar (z ≈ 0)
- [ ] Verify mic order (0,1,2,3) matches physical layout

**Test 2: Array Orientation**
- [ ] Determine physical "front" of array (mic 0 direction)
- [ ] Test with known source at 0° (front)
- [ ] Verify DOA output matches physical angle
- [ ] Adjust `orientation_offset_deg` if needed

**Test 3: Speed of Sound Calibration**
- [ ] Test in controlled environment (known temperature)
- [ ] Adjust `speed_of_sound` if needed (343 m/s at 20°C)
- [ ] Verify DOA accuracy improves

---

### 3.3 Single Source Testing

**Test Setup**:
- Place single sound source (speaker/phone) at known angle
- Use test signal: white noise, speech, or sine wave
- Record for 10-30 seconds
- Process with offline script

**Test Cases**:
1. **Static Source (0°)**
   - [ ] Source directly in front (0°)
   - [ ] Verify DOA estimate: 0° ± 5°
   - [ ] Check track stability (low variance)
   - [ ] Verify confidence > 0.7

2. **Static Source (90°)**
   - [ ] Source to the right (90°)
   - [ ] Verify DOA estimate: 90° ± 5°
   - [ ] Check all 4 quadrants (0°, 90°, 180°, -90°)

3. **Moving Source**
   - [ ] Source moves slowly (5-10°/sec)
   - [ ] Verify track follows movement
   - [ ] Check angular velocity estimate
   - [ ] Verify no track loss

4. **Distance Variation**
   - [ ] Test at 1m, 2m, 3m distances
   - [ ] Verify DOA accuracy (far-field assumption)
   - [ ] Check if near-field effects appear (< 0.5m)

**Success Criteria**:
- DOA error < 5° for static sources
- Track confidence > 0.6 for stable sources
- No false tracks (spurious detections)

---

### 3.4 Multi-Source Testing

**Test Setup**:
- Two sound sources at different angles
- Use different signals (speech, music, noise)
- Record for 20-60 seconds

**Test Cases**:
1. **Two Static Sources**
   - [ ] Sources at 45° and -45°
   - [ ] Verify both tracks are created
   - [ ] Check track IDs remain stable
   - [ ] Verify no track swapping

2. **Two Moving Sources**
   - [ ] Sources moving independently
   - [ ] Verify both tracks maintained
   - [ ] Check crossing scenarios (tracks pass each other)
   - [ ] Verify no ID swapping

3. **Three Sources**
   - [ ] Test max_sources = 3
   - [ ] Verify all three tracked
   - [ ] Check system stability

4. **Source Appearance/Disappearance**
   - [ ] Source appears mid-recording
   - [ ] Source disappears mid-recording
   - [ ] Verify track birth/death logic
   - [ ] Check pending track behavior

**Success Criteria**:
- All active sources tracked correctly
- Track IDs remain stable
- No false tracks
- Smooth track transitions

---

### 3.5 Noise & Robustness Testing

**Test Cases**:
1. **Background Noise**
   - [ ] Test with ambient room noise
   - [ ] Verify DOA still works
   - [ ] Check false positive rate
   - [ ] Test SNR masking effectiveness

2. **Reverberation**
   - [ ] Test in different room sizes
   - [ ] Check performance degradation
   - [ ] Verify track stability

3. **Interference**
   - [ ] Test with multiple speakers playing simultaneously
   - [ ] Check track separation
   - [ ] Verify no track merging

4. **Outdoor Testing**
   - [ ] Test in outdoor environment
   - [ ] Check wind noise handling
   - [ ] Verify highpass filter effectiveness

**Success Criteria**:
- System works in typical indoor environments
- False positive rate < 10%
- Track stability maintained in noise

---

### 3.6 Real-Time Performance Testing

**Test Setup**:
- Run `scripts/run_realtime.py`
- Monitor CPU usage, memory, latency
- Test for extended periods (10+ minutes)

**Metrics to Measure**:
1. **Processing Speed**
   - [ ] FPS > 100 (target: 100-200 FPS)
   - [ ] Frame processing time < 10ms
   - [ ] No frame drops

2. **Latency**
   - [ ] End-to-end latency < 100ms
   - [ ] Audio capture latency < 50ms
   - [ ] Processing latency < 50ms

3. **Resource Usage**
   - [ ] CPU usage < 50% (single core)
   - [ ] Memory usage stable (no leaks)
   - [ ] No buffer underruns

4. **Stability**
   - [ ] Run for 30+ minutes without crashes
   - [ ] No memory leaks
   - [ ] Graceful error recovery

**Success Criteria**:
- Real-time performance maintained
- No crashes or memory leaks
- Latency acceptable for interactive use

---

## Phase 4: Configuration & Parameter Tuning

### 4.1 Parameter Sensitivity Analysis

**Test Each Parameter**:
1. **STFT Parameters**
   - [ ] frame_size: 256, 320, 512
   - [ ] hop_size: 128, 160, 256
   - [ ] window_type: hann, hamming

2. **SSL Parameters**
   - [ ] azimuth_res_deg: 0.5°, 1.0°, 2.0°
   - [ ] min_power: 0.01, 0.05, 0.1
   - [ ] suppression_deg: 15°, 25°, 35°

3. **Tracker Parameters**
   - [ ] birth_frames: 2, 4, 6
   - [ ] death_frames: 8, 12, 16
   - [ ] gate_deg: 15°, 20°, 25°
   - [ ] pending_track_power_threshold: 0.01, 0.03, 0.05

4. **Noise Estimation**
   - [ ] alpha_s: 0.8, 0.85, 0.9
   - [ ] minima_window: 10, 15, 20

**Goal**: Find optimal parameter set for your use case

---

### 4.2 Configuration Validation

**Test All Config Files**:
- [ ] `config/pipeline.yaml` - master config
- [ ] `config/array_geometry.yaml` - geometry
- [ ] `config/audio.yaml` - audio settings
- [ ] `config/stft.yaml` - STFT parameters
- [ ] `config/noise.yaml` - MCRA parameters
- [ ] `config/ssl.yaml` - SSL parameters
- [ ] `config/tracker.yaml` - tracker parameters
- [ ] `config/filters.yaml` - optional filters

**Verify**:
- [ ] All required parameters present
- [ ] Parameter ranges are valid
- [ ] Defaults work correctly
- [ ] Config loading is robust

---

## Phase 5: Output Validation

### 5.1 Logging Verification

**Test DOA Logger**:
- [ ] JSONL format is valid
- [ ] All required fields present
- [ ] Timestamps are correct
- [ ] Track data is complete
- [ ] Log rotation works (if enabled)

**Check Log Structure**:
```json
{
  "type": "frame",
  "frame_index": 123,
  "timestamp_sec": 1.23,
  "tracks": [
    {
      "id": 1,
      "theta_deg": 45.0,
      "theta_dot_deg_per_sec": 2.5,
      "age": 10,
      "misses": 0,
      "hits": 10,
      "confidence": 0.85
    }
  ]
}
```

---

### 5.2 Visualization Verification

**Test Visualization Script**:
- [ ] `scripts/visualize_srp.py` runs without errors
- [ ] Polar plot updates in real-time
- [ ] SRP energy distribution looks correct
- [ ] Performance is acceptable

---

## Phase 6: Edge Cases & Error Handling

### 6.1 Error Scenarios

**Test**:
- [ ] Missing config files
- [ ] Invalid config values
- [ ] Audio device disconnection
- [ ] Corrupted audio data
- [ ] Very long recordings (> 1 hour)
- [ ] Rapid start/stop cycles
- [ ] System resource exhaustion

**Verify**:
- [ ] Graceful error messages
- [ ] No crashes
- [ ] Proper cleanup on exit
- [ ] Logging of errors

---

### 6.2 Boundary Conditions

**Test**:
- [ ] Sources at ±180° (wrapping)
- [ ] Sources very close together (< 10°)
- [ ] Very quiet sources (near noise floor)
- [ ] Very loud sources (clipping)
- [ ] Rapid source movement (> 50°/sec)
- [ ] Sources appearing/disappearing rapidly

---

## Phase 7: Documentation & Release Readiness

### 7.1 Code Documentation
- [ ] All modules have docstrings
- [ ] Function parameters documented
- [ ] Examples in docstrings
- [ ] README.md is complete
- [ ] Configuration guide written

### 7.2 Test Documentation
- [ ] Test results documented
- [ ] Known issues listed
- [ ] Performance benchmarks recorded
- [ ] Hardware requirements specified

### 7.3 Release Checklist
- [ ] All tests pass
- [ ] No critical bugs
- [ ] Performance meets requirements
- [ ] Documentation complete
- [ ] Version number set
- [ ] Changelog updated

---

## Testing Tools & Scripts Needed

### Recommended Test Scripts:
1. **Unit Test Scripts** (create these):
   - `tests/test_geometry.py` - geometry tests
   - `tests/test_stft.py` - STFT tests
   - `tests/test_gcc.py` - GCC-PHAT tests
   - `tests/test_srp.py` - SRP tests
   - `tests/test_tracker.py` - tracker tests

2. **Integration Test Scripts**:
   - `tests/test_pipeline_integration.py` - full pipeline
   - `tests/test_audio_io.py` - audio I/O

3. **Synthetic Data Generator**:
   - Script to generate test signals with known DOA
   - Multichannel audio with controlled delays

4. **Validation Scripts**:
   - `scripts/validate_doa_accuracy.py` - accuracy testing
   - `scripts/benchmark_performance.py` - performance testing

---

## Success Criteria Summary

### Must Have (Production Ready):
- ✅ All unit tests pass
- ✅ End-to-end pipeline works
- ✅ Real-time performance > 100 FPS
- ✅ DOA accuracy < 5° error
- ✅ Multi-source tracking works (2-3 sources)
- ✅ No crashes in 30+ minute runs
- ✅ No memory leaks
- ✅ Graceful error handling

### Nice to Have:
- DOA accuracy < 2° error
- Real-time performance > 200 FPS
- Works in noisy environments
- Works with 4+ sources

---

## Next Steps

1. **Start with Phase 1** - Unit testing (can use synthetic data)
2. **Move to Phase 2** - Integration testing
3. **Phase 3** - Real device testing (most important)
4. **Phase 4** - Parameter tuning based on results
5. **Phase 5-7** - Final validation and release prep

**Estimated Time**: 2-3 days for thorough testing

---

## Notes

- Test incrementally: fix issues as you find them
- Document all test results
- Keep test recordings for regression testing
- Compare results with reference implementations if available
- Consider automated testing for regression prevention

