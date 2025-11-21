#!/usr/bin/env python3
# scripts/record_multichannel.py

"""
Record multichannel audio from a microphone array (e.g., ReSpeaker)
and save to a WAV file.

Uses the unified audio configuration from:
    config/pipeline.yaml  → via config_loader

Supports:
    - Fixed-duration capture:  --duration 10
    - Manual stop via Ctrl+C
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from src.my_doa.utils.config_loader import load_pipeline_config
from src.my_doa.audio.audio_io import AudioStream
from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


# -------------------------------------------------------------------------
# Argument parser
# -------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Record multichannel audio and save to WAV."
    )
    parser.add_argument("output", type=str, help="Output WAV filename")

    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Recording duration in seconds. If omitted, use Ctrl+C to stop.",
    )

    return parser.parse_args()


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main():
    args = parse_args()
    out_path = Path(args.output)

    # Warn about overwrite
    if out_path.exists():
        print(f"Warning: {out_path} already exists and will be overwritten.")

    # ---------------------------------------------------------------------
    # 1) Load unified config (pipeline + audio)
    # ---------------------------------------------------------------------
    pipe_cfg, audio_cfg = load_pipeline_config("config/pipeline.yaml")

    device = audio_cfg.get("device", "ReSpeaker")
    fs = audio_cfg["sample_rate"]
    block_size = audio_cfg["block_size"]
    channels = audio_cfg["channels"]

    logger.info(
        "Audio recording configuration",
        extra={
            "device": device,
            "sample_rate": fs,
            "block_size": block_size,
            "channels": channels,
        },
    )

    # ---------------------------------------------------------------------
    # 2) Create AudioStream
    # ---------------------------------------------------------------------
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

    recorded_blocks = []
    stream.start()

    print("\n=== Recording Started ===")
    if args.duration is None:
        print("Press Ctrl+C to stop.")
    else:
        print(f"Recording for {args.duration} seconds...")
    print(f"Saving to: {out_path}\n")

    start_time = time.time()

    try:
        while True:
            block = stream.read_block(timeout=1.0)
            if block is None:
                continue

            recorded_blocks.append(block)

            # Duration mode
            if args.duration is not None:
                if (time.time() - start_time) >= args.duration:
                    print("Reached target duration.")
                    break

    except KeyboardInterrupt:
        print("\nStopping recording...")

    finally:
        stream.close()

    # ---------------------------------------------------------------------
    # 3) Save to WAV
    # ---------------------------------------------------------------------
    if len(recorded_blocks) == 0:
        print("No audio captured!")
        return

    # Concatenate into one big array
    audio = np.concatenate(recorded_blocks, axis=1)   # (channels, samples)
    audio = audio.T.astype("float32")                # → (samples, channels)

    sf.write(str(out_path), audio, fs)
    print(f"\nSaved: {audio.shape[0]} samples, {audio.shape[1]} channels")
    print(f"Output file: {out_path}")
    print("Done.")


if __name__ == "__main__":
    main()
