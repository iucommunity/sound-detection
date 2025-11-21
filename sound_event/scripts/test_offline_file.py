#!/usr/bin/env python3
# scripts/test_offline_file.py

"""
Offline DOA test on a multichannel WAV file using the full production pipeline.

Usage:
    python scripts/test_offline_file.py path/to/recording.wav

This script:
    - Loads DOA pipeline + all nested configs (array_geometry.yaml, stft.yaml, noise.yaml, ...)
    - Loads WAV via wav_reader (consistent with realtime)
    - Applies optional pre-filter (filters.yaml)
    - Runs end-to-end DOA + tracking
    - Prints frame-by-frame tracked DOAs
"""

from __future__ import annotations

import sys
from pathlib import Path
import time

import numpy as np
import yaml

from src.my_doa.utils.config_loader import load_pipeline_config
from src.my_doa.pipeline.doa_pipeline import DOAPipeline
from src.my_doa.audio.wav_reader import load_multichannel_wav, block_generator
from src.my_doa.utils.timing import FpsMeter
from src.my_doa.utils.logger import get_logger
from src.my_doa.dsp.filters import design_highpass, design_bandpass, apply_filter
from src.my_doa.utils.math_utils import wrap_angle_deg_0_360


logger = get_logger(__name__)


# ---------------------------------------------------------------------
# Load optional filtering configuration
# ---------------------------------------------------------------------

def _load_filters(path: str | Path = "config/filters.yaml"):
    path = Path(path)
    if not path.exists():
        logger.info("No filters.yaml found; pre-filter disabled for offline.")
        return None

    try:
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        logger.warning("Failed to load filters.yaml", extra={"error": str(e)})
        return None

    if not cfg.get("enable_pre_filter", False):
        logger.info("Pre-filter disabled via filters.yaml")
        return None

    return cfg


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_offline_file.py path/to/recording.wav")
        sys.exit(1)

    wav_path = Path(sys.argv[1])
    if not wav_path.exists():
        print(f"File not found: {wav_path}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 1) Load pipeline config (YAML-driven)
    # ------------------------------------------------------------------

    try:
        pipe_cfg, audio_cfg = load_pipeline_config("config/pipeline.yaml")
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)

    pipeline = DOAPipeline(pipe_cfg)
    fs = pipe_cfg.sample_rate

    print("\n=== Offline DOA Test ===")
    print(f"Using config from: config/pipeline.yaml")
    print(f"Sample rate (expected): {fs} Hz")
    print(f"WAV to load: {wav_path}")

    # ------------------------------------------------------------------
    # 2) Load WAV (using our unified reader)
    # ------------------------------------------------------------------

    audio, fs_wav = load_multichannel_wav(
        wav_path,
        expected_channels=audio_cfg.get("channels", None)
    )

    if fs_wav != fs:
        print(f"WARNING: WAV fs={fs_wav} differs from config fs={fs}.")
        print("Resampling is NOT performed automatically.")
        print("Please provide WAV with matching sample rate.")
        sys.exit(1)

    n_mics, n_samples = audio.shape
    print(f"WAV Loaded: {n_mics} ch, {n_samples} samples\n")

    # ------------------------------------------------------------------
    # 3) Optional pre-filter
    # ------------------------------------------------------------------

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
            logger.info("Enabled pre-filter", extra={"filter_type": filt_cfg["type"]})
            print(f"Pre-filter enabled: {filt_cfg['type']}")
        except Exception as e:
            logger.warning("Failed to construct pre-filter", extra={"error": str(e)})
            print("Pre-filter disabled due to error.")
            sos = None

    # ------------------------------------------------------------------
    # 4) Process in blocks
    # ------------------------------------------------------------------

    block_size = audio_cfg.get("block_size", 1024)
    print(f"Block size: {block_size}")
    print("\n--- Running offline DOA ---\n")

    fps_meter = FpsMeter()
    total_frames = 0

    for block in block_generator(audio, block_size):
        # Optional pre-filter
        if sos is not None:
            block = apply_filter(sos, block, mode="zero_phase")

        results = pipeline.process_block(block)

        for res in results:
            frame_idx = res["frame_index"]
            tracks = res["tracks"]

            if not tracks:
                print(f"[Frame {frame_idx:5d}] No tracks")
            else:
                tracks_sorted = sorted(tracks, key=lambda t: t.id)
                line = f"[Frame {frame_idx:5d}]"
                # Convert to 0-360 range for display (mics are at 45°, 135°, 225°, 315°)
                for tr in tracks_sorted:
                    theta_0_360 = wrap_angle_deg_0_360(tr.theta_deg)
                    line += f"  ID {tr.id:2d}: θ={theta_0_360:7.2f}°"
                print(line)

            fps = fps_meter.tick()
            if fps > 0:
                print(f"  Pipeline FPS: {fps:5.1f}", end="\r")

            total_frames += 1

    print(f"\n\nFinished. Total STFT frames processed: {total_frames}")


if __name__ == "__main__":
    main()
