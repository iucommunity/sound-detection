#!/usr/bin/env python3
"""
Real-World Device Diagnostic Test Script

This script runs the DOA pipeline with a real microphone array and outputs
comprehensive diagnostic logs for analysis.

The logs include:
- Pipeline initialization details
- Per-frame processing statistics
- Track information and confidence
- Performance metrics (FPS, latency)
- Error detection and warnings
- Summary statistics

Usage:
    python scripts/test_realtime_diagnostic.py [--duration SECONDS] [--output-dir DIR]

Press Ctrl+C to stop early.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

import numpy as np
import yaml

from src.my_doa.utils.config_loader import load_pipeline_config
from src.my_doa.pipeline.doa_pipeline import DOAPipeline
from src.my_doa.audio.audio_io import AudioStream, list_input_devices
from src.my_doa.utils.doa_logger import DOALogger
from src.my_doa.dsp.filters import design_highpass, design_bandpass, apply_filter
from src.my_doa.utils.timing import FpsMeter, Stopwatch
from src.my_doa.utils.logger import get_logger
from src.my_doa.utils.math_utils import wrap_angle_deg_0_360

logger = get_logger(__name__)


# ============================================================================
# Diagnostic Statistics Collector
# ============================================================================

class DiagnosticStats:
    """Collects diagnostic statistics during test run."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.frame_count = 0
        self.total_tracks_created = 0
        self.total_tracks_removed = 0
        self.track_ages: List[int] = []
        self.track_confidences: List[float] = []
        self.doa_errors: List[float] = []  # If ground truth available
        self.frames_with_detections = 0
        self.frames_with_tracks = 0
        self.frames_silent = 0
        self.max_tracks_simultaneous = 0
        self.srp_power_stats: List[float] = []
        self.processing_times: List[float] = []
        self.track_lifetimes: Dict[int, int] = {}  # track_id -> lifetime
        self.active_track_ids: set = set()
        self.track_creation_times: Dict[int, float] = {}
        
    def update_frame(self, result: Dict, processing_time: float):
        """Update statistics from a frame result."""
        self.frame_count += 1
        self.processing_times.append(processing_time)
        
        candidates = result.get("doa_candidates", [])
        tracks = result.get("tracks", [])
        P_theta = result.get("P_theta")
        
        # Detection statistics
        if len(candidates) > 0:
            self.frames_with_detections += 1
        else:
            self.frames_silent += 1
        
        # Track statistics
        if len(tracks) > 0:
            self.frames_with_tracks += 1
            self.max_tracks_simultaneous = max(self.max_tracks_simultaneous, len(tracks))
        
        # Track details
        current_track_ids = set()
        for track in tracks:
            track_id = track.id
            current_track_ids.add(track_id)
            
            # Track lifetime tracking
            if track_id not in self.active_track_ids:
                # New track
                self.total_tracks_created += 1
                self.track_creation_times[track_id] = time.time()
                self.track_lifetimes[track_id] = 0
            else:
                # Existing track
                self.track_lifetimes[track_id] += 1
            
            # Collect statistics
            self.track_ages.append(track.age)
            conf = track.compute_confidence()
            self.track_confidences.append(conf)
        
        # Tracks that disappeared
        for track_id in self.active_track_ids - current_track_ids:
            if track_id in self.track_lifetimes:
                lifetime = self.track_lifetimes[track_id]
                if lifetime > 0:
                    self.total_tracks_removed += 1
        
        self.active_track_ids = current_track_ids
        
        # SRP power statistics
        if P_theta is not None:
            max_power = float(np.max(P_theta))
            mean_power = float(np.mean(P_theta))
            self.srp_power_stats.append(max_power)
    
    def get_summary(self) -> Dict:
        """Get summary statistics."""
        if self.frame_count == 0:
            return {}
        
        return {
            "total_frames": self.frame_count,
            "frames_with_detections": self.frames_with_detections,
            "frames_with_tracks": self.frames_with_tracks,
            "frames_silent": self.frames_silent,
            "detection_rate": self.frames_with_detections / self.frame_count,
            "track_rate": self.frames_with_tracks / self.frame_count,
            "total_tracks_created": self.total_tracks_created,
            "total_tracks_removed": self.total_tracks_removed,
            "max_tracks_simultaneous": self.max_tracks_simultaneous,
            "avg_track_age": np.mean(self.track_ages) if self.track_ages else 0.0,
            "max_track_age": max(self.track_ages) if self.track_ages else 0,
            "avg_confidence": np.mean(self.track_confidences) if self.track_confidences else 0.0,
            "min_confidence": min(self.track_confidences) if self.track_confidences else 0.0,
            "max_confidence": max(self.track_confidences) if self.track_confidences else 0.0,
            "avg_srp_power": np.mean(self.srp_power_stats) if self.srp_power_stats else 0.0,
            "max_srp_power": max(self.srp_power_stats) if self.srp_power_stats else 0.0,
            "avg_processing_time_ms": np.mean(self.processing_times) * 1000 if self.processing_times else 0.0,
            "max_processing_time_ms": max(self.processing_times) * 1000 if self.processing_times else 0.0,
        }


# ============================================================================
# Diagnostic Logger
# ============================================================================

class DiagnosticLogger:
    """Logs diagnostic information in a structured format."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log files
        timestamp = int(time.time())
        self.diagnostic_log = self.output_dir / f"diagnostic_{timestamp}.txt"
        self.frame_log = self.output_dir / f"frames_{timestamp}.txt"
        self.summary_log = self.output_dir / f"summary_{timestamp}.yaml"
        
        self.f_frame = open(self.frame_log, "w")
        self.f_diag = open(self.diagnostic_log, "w")
        
        # Write headers
        self.f_frame.write("# Frame-by-frame diagnostic log\n")
        self.f_frame.write("# Format: frame_idx | n_candidates | n_tracks | track_details | srp_max | proc_time_ms\n")
        self.f_frame.write("#\n")
        
    def log_frame(self, frame_idx: int, result: Dict, processing_time: float):
        """Log detailed frame information."""
        candidates = result.get("doa_candidates", [])
        tracks = result.get("tracks", [])
        P_theta = result.get("P_theta")
        
        # Track details
        track_details = []
        for track in sorted(tracks, key=lambda t: t.id):
            # Convert to 0-360 range for display (tracker uses -180 to 180 internally)
            theta_display = wrap_angle_deg_0_360(track.theta_deg)
            track_details.append(
                f"ID{track.id}:θ={theta_display:6.1f}° "
                f"age={track.age:3d} hits={track.hits:3d} misses={track.misses:2d} "
                f"conf={track.compute_confidence():.2f}"
            )
        
        srp_max = float(np.max(P_theta)) if P_theta is not None else 0.0
        proc_ms = processing_time * 1000
        
        line = (
            f"{frame_idx:6d} | "
            f"cands={len(candidates):2d} | "
            f"tracks={len(tracks):2d} | "
            f"{' | '.join(track_details) if track_details else 'no tracks'} | "
            f"srp_max={srp_max:6.3f} | "
            f"proc={proc_ms:5.2f}ms"
        )
        
        self.f_frame.write(line + "\n")
        self.f_frame.flush()
    
    def log_diagnostic(self, message: str):
        """Log diagnostic message."""
        timestamp = time.strftime("%H:%M:%S")
        self.f_diag.write(f"[{timestamp}] {message}\n")
        self.f_diag.flush()
        print(f"[DIAG] {message}")
    
    def log_summary(self, stats: DiagnosticStats, config_info: Dict):
        """Log final summary."""
        summary = stats.get_summary()
        summary["config"] = config_info
        summary["test_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        with open(self.summary_log, "w") as f:
            yaml.dump(summary, f, default_flow_style=False, sort_keys=False)
        
        # Also print summary
        self.f_diag.write("\n" + "="*80 + "\n")
        self.f_diag.write("TEST SUMMARY\n")
        self.f_diag.write("="*80 + "\n")
        for key, value in summary.items():
            if key != "config":
                self.f_diag.write(f"{key:30s}: {value}\n")
        self.f_diag.write("\n")
        
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        for key, value in summary.items():
            if key != "config":
                print(f"{key:30s}: {value}")
        print("="*80)
    
    def close(self):
        """Close log files."""
        self.f_frame.close()
        self.f_diag.close()
        print(f"\nDiagnostic logs saved to: {self.output_dir}")


# ============================================================================
# Helper Functions
# ============================================================================

def load_filters(path: str | Path = "config/filters.yaml"):
    """Load optional filter configuration."""
    path = Path(path)
    if not path.exists():
        return None
    
    try:
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        logger.warning("Failed to load filters.yaml", extra={"error": str(e)})
        return None
    
    if not cfg.get("enable_pre_filter", False):
        return None
    
    return cfg


def get_config_info(pipe_cfg, audio_cfg) -> Dict:
    """Extract configuration information for logging."""
    return {
        "sample_rate": pipe_cfg.sample_rate,
        "stft_frame_size": pipe_cfg.stft.frame_size,
        "stft_hop_size": pipe_cfg.stft.hop_size,
        "stft_fft_size": pipe_cfg.stft.fft_size or pipe_cfg.stft.frame_size,
        "azimuth_resolution_deg": pipe_cfg.ssl.azimuth_res_deg,
        "max_sources": pipe_cfg.ssl.max_sources,
        "min_power": pipe_cfg.ssl.min_power,
        "bandpass_hz": f"{pipe_cfg.ssl.bandpass_low_hz}-{pipe_cfg.ssl.bandpass_high_hz}",
        "tracker_birth_frames": pipe_cfg.tracker.birth_frames,
        "tracker_death_frames": pipe_cfg.tracker.death_frames,
        "tracker_gate_deg": pipe_cfg.tracker.gate_deg,
        "audio_device": audio_cfg.get("device", "default"),
        "audio_block_size": audio_cfg.get("block_size", 512),
        "audio_channels": audio_cfg.get("channels", 4),
    }


# ============================================================================
# Main Test Function
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Real-world device diagnostic test for DOA pipeline"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Test duration in seconds (default: run until Ctrl+C)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/diagnostic_logs",
        help="Directory for diagnostic logs (default: data/diagnostic_logs)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed per-frame information",
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("REAL-WORLD DEVICE DIAGNOSTIC TEST")
    print("="*80)
    print()
    
    # ------------------------------------------------------------------------
    # 1. Load Configuration
    # ------------------------------------------------------------------------
    try:
        pipe_cfg, audio_cfg = load_pipeline_config("config/pipeline.yaml")
        config_info = get_config_info(pipe_cfg, audio_cfg)
    except Exception as e:
        print(f"ERROR: Failed to load configuration: {e}")
        sys.exit(1)
    
    print("Configuration loaded successfully")
    print(f"  Sample rate: {pipe_cfg.sample_rate} Hz")
    print(f"  STFT: frame={pipe_cfg.stft.frame_size}, hop={pipe_cfg.stft.hop_size}")
    print(f"  SSL: resolution={pipe_cfg.ssl.azimuth_res_deg}°, max_sources={pipe_cfg.ssl.max_sources}")
    print(f"  Tracker: birth={pipe_cfg.tracker.birth_frames}, death={pipe_cfg.tracker.death_frames}")
    print()
    
    # ------------------------------------------------------------------------
    # 2. Initialize Pipeline
    # ------------------------------------------------------------------------
    try:
        pipeline = DOAPipeline(pipe_cfg)
        print("Pipeline initialized successfully")
    except Exception as e:
        print(f"ERROR: Failed to initialize pipeline: {e}")
        sys.exit(1)
    
    # ------------------------------------------------------------------------
    # 3. Setup Optional Pre-filter
    # ------------------------------------------------------------------------
    sos = None
    filt_cfg = load_filters("config/filters.yaml")
    if filt_cfg is not None:
        try:
            fs = pipe_cfg.sample_rate
            if filt_cfg["type"] == "highpass":
                sos = design_highpass(
                    cutoff_hz=filt_cfg["highpass_cutoff_hz"],
                    fs=fs,
                    order=filt_cfg.get("order", 4),
                )
            elif filt_cfg["type"] == "bandpass":
                sos = design_bandpass(
                    low_hz=filt_cfg["bandpass_low_hz"],
                    high_hz=filt_cfg["bandpass_high_hz"],
                    fs=fs,
                    order=filt_cfg.get("order", 4),
                )
            print(f"Pre-filter enabled: {filt_cfg['type']}")
        except Exception as e:
            print(f"WARNING: Failed to setup pre-filter: {e}")
            sos = None
    
    # ------------------------------------------------------------------------
    # 4. Initialize Audio Stream
    # ------------------------------------------------------------------------
    device = audio_cfg.get("device", "ReSpeaker")
    fs = int(audio_cfg["sample_rate"])
    block_size = int(audio_cfg["block_size"])
    channels = int(audio_cfg["channels"])
    channel_mapping = audio_cfg.get("channel_mapping", None)
    capture_channels = audio_cfg.get("capture_channels", None)
    
    try:
        stream = AudioStream(
            device=device,
            sample_rate=fs,
            block_size=block_size,
            channels=channels,
            channel_mapping=channel_mapping,
            capture_channels=capture_channels,
        )
        print(f"Audio device opened: {device}")
    except Exception as e:
        print(f"\nERROR: Failed to open audio device '{device}'.\n")
        print("Available input devices:")
        list_input_devices()
        sys.exit(1)
    
    # ------------------------------------------------------------------------
    # 5. Initialize Diagnostic Logging
    # ------------------------------------------------------------------------
    diag_logger = DiagnosticLogger(args.output_dir)
    stats = DiagnosticStats()
    fps_meter = FpsMeter()
    stopwatch = Stopwatch()
    
    diag_logger.log_diagnostic("Test started")
    diag_logger.log_diagnostic(f"Configuration: {config_info}")
    diag_logger.log_diagnostic(f"Output directory: {args.output_dir}")
    
    # ------------------------------------------------------------------------
    # 6. Setup DOA Logger (optional, for JSONL output)
    # ------------------------------------------------------------------------
    doa_log_path = Path(args.output_dir) / f"doa_log_{int(time.time())}.jsonl"
    doa_logger = DOALogger(doa_log_path)
    
    # ------------------------------------------------------------------------
    # 7. Run Test
    # ------------------------------------------------------------------------
    stream.start()
    stopwatch.start()
    start_time = time.time()
    
    print("\n" + "-"*80)
    print("Starting test...")
    if args.duration:
        print(f"Will run for {args.duration} seconds")
    else:
        print("Press Ctrl+C to stop")
    print("-"*80)
    print()
    
    if args.verbose:
        print("Frame-by-frame output:")
        print("-"*80)
    
    try:
        frame_count = 0
        last_status_time = time.time()
        
        while True:
            # Check duration limit
            if args.duration and (time.time() - start_time) >= args.duration:
                print("\nDuration limit reached")
                break
            
            # Fetch audio block
            block = stream.read_block(timeout=1.0)
            if block is None:
                continue
            
            # Apply pre-filter if enabled
            if sos is not None:
                block = apply_filter(sos, block, mode="zero_phase")
            
            # Process block
            frame_start = time.perf_counter()
            results = pipeline.process_block(block)
            frame_end = time.perf_counter()
            
            # Process each STFT frame
            for res in results:
                frame_idx = res["frame_index"]
                processing_time = frame_end - frame_start  # Approximate per-frame time
                
                # Update statistics
                stats.update_frame(res, processing_time)
                
                # Log frame details
                diag_logger.log_frame(frame_idx, res, processing_time)
                
                # Log to DOA logger
                doa_logger.log_frame(
                    frame_index=frame_idx,
                    tracks=res["tracks"],
                    timestamp_sec=time.time(),
                )
                
                # Verbose console output
                if args.verbose:
                    tracks = res["tracks"]
                    if tracks:
                        track_str = " | ".join(
                            f"ID{t.id}:θ={wrap_angle_deg_0_360(t.theta_deg):6.1f}°(conf={t.compute_confidence():.2f})"
                            for t in sorted(tracks, key=lambda t: t.id)
                        )
                        print(f"[{frame_idx:6d}] {track_str}")
                    else:
                        print(f"[{frame_idx:6d}] no tracks")
                
                frame_count += 1
                
                # Periodic status update
                if time.time() - last_status_time >= 5.0:
                    fps = fps_meter.tick()
                    elapsed = stopwatch.elapsed()
                    print(
                        f"[Status] Frames: {frame_count:6d} | "
                        f"FPS: {fps:5.1f} | "
                        f"Elapsed: {elapsed:6.1f}s | "
                        f"Active tracks: {len(res.get('tracks', []))}"
                    )
                    last_status_time = time.time()
                
                # Update FPS meter
                fps_meter.tick()
    
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    
    except Exception as e:
        print(f"\n\nERROR during test: {e}")
        import traceback
        traceback.print_exc()
        diag_logger.log_diagnostic(f"ERROR: {e}")
        diag_logger.log_diagnostic(traceback.format_exc())
    
    finally:
        # Cleanup
        stopwatch.stop()
        stream.close()
        doa_logger.close()
        
        # Final statistics
        elapsed_time = stopwatch.elapsed()
        final_fps = frame_count / elapsed_time if elapsed_time > 0 else 0.0
        
        diag_logger.log_diagnostic(f"Test completed")
        diag_logger.log_diagnostic(f"Total frames: {frame_count}")
        diag_logger.log_diagnostic(f"Total time: {elapsed_time:.2f}s")
        diag_logger.log_diagnostic(f"Average FPS: {final_fps:.2f}")
        
        # Log summary
        diag_logger.log_summary(stats, config_info)
        diag_logger.close()
        
        print("\n" + "="*80)
        print("Test completed successfully!")
        print(f"Diagnostic logs saved to: {args.output_dir}")
        print("="*80)


if __name__ == "__main__":
    main()

