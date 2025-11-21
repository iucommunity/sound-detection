#!/usr/bin/env python3
# scripts/visualize_srp.py

"""
Real-time SRP-PHAT azimuth visualization.

This script:
    - Uses the full production pipeline (loaded via config_loader)
    - Grabs SRP energy P(theta) from each STFT frame
    - Visualizes SRP in a polar plot in real time
    - Optionally applies pre-filter (filters.yaml)
    - Matches behavior/config of realtime + offline DOA tools

Run:
    python scripts/visualize_srp.py
"""

from __future__ import annotations

import numpy as np
import yaml
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from pathlib import Path

from src.my_doa.utils.config_loader import load_pipeline_config
from src.my_doa.pipeline.doa_pipeline import DOAPipeline
from src.my_doa.audio.audio_io import AudioStream
from src.my_doa.utils.logger import get_logger
from src.my_doa.dsp.filters import design_highpass, design_bandpass, apply_filter

logger = get_logger(__name__)


# ---------------------------------------------------------------------
# Load optional pre-filter
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
        logger.info("Pre-filter disabled via filters.yaml.")
        return None

    return cfg


# ---------------------------------------------------------------------
# Main visualization
# ---------------------------------------------------------------------

def main():
    print("\n=== Live SRP-PHAT Visualization ===\n")

    # --------------------------------------------------------------
    # 1) Load pipeline configs
    # --------------------------------------------------------------
    pipe_cfg, audio_cfg = load_pipeline_config("sound_event/config/pipeline.yaml")
    pipeline = DOAPipeline(pipe_cfg)

    device = audio_cfg.get("device", "ReSpeaker")
    fs = audio_cfg["sample_rate"]
    block_size = audio_cfg["block_size"]
    channels = audio_cfg["channels"]

    print(f"Audio device: {device}")
    print(f"Sample rate: {fs} Hz | block size: {block_size} | channels: {channels}")

    # --------------------------------------------------------------
    # 2) Pre-filter (optional)
    # --------------------------------------------------------------
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

            print(f"Pre-filter enabled: {filt_cfg['type']}")
        except Exception as e:
            logger.warning("Failed to create pre-filter", extra={"error": str(e)})
            print("Pre-filter disabled.")
            sos = None

    # --------------------------------------------------------------
    # 3) Start audio
    # --------------------------------------------------------------
    channel_mapping = audio_cfg.get("channel_mapping", None)
    capture_channels = audio_cfg.get("capture_channels", None)
    
    stream = AudioStream(
        device=device,
        sample_rate=fs,
        block_size=block_size,
        channels=channels,
        channel_mapping=channel_mapping,
        capture_channels=capture_channels,
    )
    stream.start()

    print("\nPress Ctrl+C to stop.")
    print("Opening polar plot window...\n")

    # --------------------------------------------------------------
    # 4) Matplotlib setup
    # --------------------------------------------------------------
    plt.style.use("default")
    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(111, projection="polar")

    az_deg = pipeline.azimuth_grid_deg
    az_rad = np.deg2rad(az_deg)

    # Initial SRP values
    P = np.zeros_like(az_rad)
    line, = ax.plot(az_rad, P, linewidth=2)

    ax.set_theta_zero_location("N")   # 0° = north
    ax.set_theta_direction(-1)        # clockwise
    ax.set_title("SRP-PHAT Energy (Live)", fontsize=15)
    ax.set_ylim(0, 1.0)

    # --------------------------------------------------------------
    # 5) Animation update function
    # --------------------------------------------------------------
    def update(_):
        block = stream.read_block(timeout=0.1)
        if block is None:
            return line,

        # Optional filtering
        if sos is not None:
            block = apply_filter(sos, block, mode="zero_phase")

        # Run pipeline for this block
        results = pipeline.process_block(block)

        # Visualize SRP for the LAST STFT frame produced in this block
        for res in results:
            P_theta = res["P_theta"]
            P_norm = P_theta / (np.max(P_theta) + 1e-9)
            line.set_ydata(P_norm)
            ax.set_ylim(0, 1.0)

        return line,

    # --------------------------------------------------------------
    # 6) Start animation
    # --------------------------------------------------------------
    ani = animation.FuncAnimation(
        fig,
        update,
        interval=20,
        blit=True,
    )

    try:
        plt.show()
    except KeyboardInterrupt:
        print("\nStopping visualization...")

    finally:
        stream.close()
        print("Audio stream closed.")


if __name__ == "__main__":
    main()
