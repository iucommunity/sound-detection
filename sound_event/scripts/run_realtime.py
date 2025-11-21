#!/usr/bin/env python3
# scripts/run_realtime.py

"""
Real-time DOA estimation + Multi-target tracking
for ReSpeaker Mic Array v3.0 (or any 4-ch device).

Uses:
- config/pipeline.yaml + nested configs
- DOAPipeline
- AudioStream
- Optional pre-filter (from filters.yaml)
- Logs DOA tracks to JSONL

Run:
    python scripts/run_realtime.py
"""

from __future__ import annotations

import time
from pathlib import Path
import sys

import numpy as np
import yaml

from src.my_doa.utils.config_loader import load_pipeline_config
from src.my_doa.pipeline.doa_pipeline import DOAPipeline
from src.my_doa.audio.audio_io import AudioStream, list_input_devices
from src.my_doa.utils.math_utils import wrap_angle_deg_0_360
from src.my_doa.utils.doa_logger import DOALogger
from src.my_doa.dsp.filters import design_highpass, design_bandpass, apply_filter
from src.my_doa.utils.timing import FpsMeter
from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------
# Load optional filtering configuration
# ---------------------------------------------------------------------

def _load_filters(path: str | Path = "config/filters.yaml"):
    path = Path(path)
    if not path.exists():
        logger.info("No filters.yaml found; pre-filter disabled.")
        return None

    try:
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        logger.warning("Failed to load filters.yaml", extra={"error": str(e)})
        return None

    if not cfg.get("enable_pre_filter", False):
        logger.info("Pre-filter disabled via config.")
        return None

    return cfg


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------

def main():
    print("\n=== Real-Time DOA + Tracking ===")

    # 1) Load pipeline + audio config
    try:
        pipe_cfg, audio_cfg = load_pipeline_config("config/pipeline.yaml")
    except Exception as e:
        print(f"Failed to load config: {e}")
        sys.exit(1)

    pipeline = DOAPipeline(pipe_cfg)

    # Audio settings
    device = audio_cfg.get("device", "ReSpeaker")
    fs = int(audio_cfg["sample_rate"])
    block_size = int(audio_cfg["block_size"])
    channels = int(audio_cfg["channels"])
    channel_mapping = audio_cfg.get("channel_mapping", None)
    capture_channels = audio_cfg.get("capture_channels", None)

    print(f"Using device: {device}")
    print(f"Sample rate: {fs} Hz | Block size: {block_size} | Channels: {channels}")
    if channel_mapping:
        print(f"Channel mapping: {channel_mapping} (capturing {capture_channels or 'auto'} channels)")

    # 2) Optional pre-filter
    filt_cfg = _load_filters("config/filters.yaml")
    sos = None
    if filt_cfg is not None:
        try:
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
            else:
                logger.warning("Unknown filter type", extra={"type": filt_cfg["type"]})
                sos = None
        except Exception as e:
            logger.warning("Failed to build pre-filter", extra={"error": str(e)})
            sos = None

        if sos is not None:
            logger.info("Pre-filter enabled", extra={"filter_type": filt_cfg["type"]})
            print(f"Pre-filter enabled: {filt_cfg['type']}")

    # 3) Audio stream
    try:
        stream = AudioStream(
            device=device,
            sample_rate=fs,
            block_size=block_size,
            channels=channels,
            channel_mapping=channel_mapping,
            capture_channels=capture_channels,
        )
    except Exception as e:
        print(f"\nERROR: Failed to open audio device '{device}'.\n")
        print("Available input devices:\n")
        list_input_devices()
        raise e

    # 4) DOA logger
    log_path = Path("data/logs") / f"doa_log_{int(time.time())}.jsonl"
    doa_logger = DOALogger(log_path)
    fps_meter = FpsMeter()

    stream.start()
    print("\n>>> Press Ctrl+C to stop.\n")

    try:
        while True:
            # Fetch audio
            block = stream.read_block(timeout=1.0)
            if block is None:
                continue

            # Optional filtering
            if sos is not None:
                block = apply_filter(sos, block, mode="zero_phase")

            results = pipeline.process_block(block)

            # Process each STFT frame from this audio block
            for res in results:
                frame_idx = res["frame_index"]
                tracks = res["tracks"]

                # Log DOA
                doa_logger.log_frame(
                    frame_index=frame_idx,
                    tracks=tracks,
                    timestamp_sec=time.time(),
                )

                # Console visualization
                if tracks:
                    tracks_sorted = sorted(tracks, key=lambda t: t.id)
                    # Convert to 0-360 range for display (mics are at 45°, 135°, 225°, 315°)
                    angles = "  ".join(f"ID {t.id:02d}: θ={wrap_angle_deg_0_360(t.theta_deg):7.2f}°"
                                       for t in tracks_sorted)
                    print(f"[Frame {frame_idx:6d}]  {angles}")
                else:
                    print(f"[Frame {frame_idx:6d}]  no tracks")

                # FPS meter
                fps = fps_meter.tick()
                if fps > 0:
                    print(f"  Pipeline FPS: {fps:5.1f}", end="\r")

    except KeyboardInterrupt:
        print("\nStopping...")

    except Exception as e:
        logger.error("Realtime loop crashed", extra={"error": str(e)})
        print("\nERROR:", e)

    finally:
        stream.close()
        doa_logger.close()
        print(f"\nLog saved to: {log_path}")


if __name__ == "__main__":
    main()
