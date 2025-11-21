#!/usr/bin/env python3
# scripts/validate_doa_realtime.py

"""
Full real-time DOA system validation for ReSpeaker Mic Array v3.0
on Ubuntu / Jetson Orin Nano.

This script is meant for *engineering validation* before production:

1) Device & config sanity checks:
   - Lists audio devices
   - Verifies configured device exists & supports requested channels/fs

2) Optional channel mapping check:
   - For each recorded channel, asks you to tap near one mic
   - Measures RMS and prints which channel is hottest
   - Lets you confirm physical mic <-> channel ordering

3) Real-time DOA + tracking run:
   - Uses DOAPipeline with your YAML configs
   - Logs tracks to JSONL via DOALogger
   - Prints per-frame DOA & track summary
   - Shows pipeline FPS

4) Optional live SRP-PHAT visualization:
   - Polar plot of P(theta) over azimuth
   - Peaks should move as you move around the array

ReSpeaker 6-channel firmware mapping (fixed in this script):

    CH0 = processed audio for ASR  (NOT used)
    CH1 = mic1 raw
    CH2 = mic2 raw
    CH3 = mic3 raw
    CH4 = mic4 raw
    CH5 = merged playback (NOT used)

We:
  - capture 6 channels from the device
  - feed only CH1–CH4 into the DOA pipeline
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import sounddevice as sd

try:
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation

    _HAS_MPL = True
except Exception:
    _HAS_MPL = False

from src.my_doa.utils.config_loader import load_pipeline_config
from src.my_doa.pipeline.doa_pipeline import DOAPipeline
from src.my_doa.utils.doa_logger import DOALogger
from src.my_doa.utils.timing import FpsMeter
from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------
# ReSpeaker-specific constants
# ---------------------------------------------------------------------

# We expect 6 captured channels from the USB device
RESPEAKER_CAPTURE_CHANNELS = 6

# Raw mic channels we want (indices into the captured audio)
# CH1–4 → mic0..3 for the pipeline
RESPEAKER_MIC_INDICES = [1, 2, 3, 4]


# ---------------------------------------------------------------------
# Device + config checks
# ---------------------------------------------------------------------


def check_device_compatibility(
    audio_cfg: dict,
    capture_channels: int,
) -> None:
    """
    Check that the configured device exists and supports the requested
    channels and sample rate. Prints diagnostics and raises on hard issues.
    """
    desired_device = audio_cfg.get("device", None)
    fs = int(audio_cfg.get("sample_rate", 16000))

    print("\n=== Audio Device Check ===")
    print(f"Configured device: {desired_device!r}")
    print(f"Configured sample_rate: {fs} Hz")
    print(f"Capture channels (ReSpeaker USB): {capture_channels}\n")

    devices = sd.query_devices()
    print("Available input devices:")
    selected_idx: Optional[int] = None
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            print(
                f"  [{idx:2d}] {dev['name']}  "
                f"({dev['max_input_channels']} in / {dev['max_output_channels']} out)"
            )
        # Try to match configured device by substring
        if isinstance(desired_device, str) and dev["max_input_channels"] > 0:
            if desired_device.lower() in dev["name"].lower():
                selected_idx = idx

    if isinstance(desired_device, int):
        selected_idx = desired_device

    print("")

    if selected_idx is None:
        print("WARNING: Could not auto-resolve configured device.")
        print("         sounddevice will still try to use it,")
        print("         but you may need to adjust 'device' in config/audio.yaml.\n")
    else:
        dev = devices[selected_idx]
        print(f"Selected device index: {selected_idx} ({dev['name']})")
        if dev["max_input_channels"] < capture_channels:
            raise RuntimeError(
                f"Device {dev['name']} supports only {dev['max_input_channels']} "
                f"input channels, but we want to capture {capture_channels}."
            )

    print("Device check completed.\n")


# ---------------------------------------------------------------------
# Channel mapping check
# ---------------------------------------------------------------------


def run_channel_mapping_check(
    fs: int,
    block_size: int,
    device: Optional[str | int],
    duration_per_step: float = 3.0,
) -> None:
    """
    ReSpeaker v3.0 channel mapping verification for RAW mics only.

    Firmware layout (6ch):
        CH0 = processed audio     (ignore)
        CH1 = mic1 raw  <-- real mic
        CH2 = mic2 raw  <-- real mic
        CH3 = mic3 raw  <-- real mic
        CH4 = mic4 raw  <-- real mic
        CH5 = playback            (ignore)

    We check only the useful mic channels: CH1–CH4.
    """

    mic_channels = [1, 2, 3, 4]   # Only real raw microphones
    n = len(mic_channels)

    print("\n=== Channel Mapping Check (ReSpeaker RAW mics only: CH1–CH4) ===")
    print("For each step, tap near the expected physical microphone.\n")

    stream = sd.InputStream(
        device=device,
        samplerate=fs,
        blocksize=block_size,
        channels=6,               # Always capture 6 channels
        dtype="float32",
    )

    stream.start()
    try:
        for idx, ch in enumerate(mic_channels):
            input(
                f"\n>>> Step {idx+1}/{n}: Tap/rub near PHYSICAL MIC {idx+1} (expected CH{ch}). "
                "Press Enter when ready..."
            )

            t_start = time.time()
            rms_accum = np.zeros(6, dtype=np.float64)
            n_blocks = 0

            while time.time() - t_start < duration_per_step:
                data, _ = stream.read(block_size)  # (frames, 6)
                block = data.T  # (6, samples)

                rms = np.sqrt(np.mean(block**2, axis=1))
                rms_accum += rms
                n_blocks += 1

            if n_blocks == 0:
                print("  WARNING: no blocks captured.")
                continue

            avg_rms = rms_accum / n_blocks

            print(f"  Average RMS per channel: {np.round(avg_rms, 6)}")

            # Ignore CH0 and CH5 when deciding mapping – only compare raw mics CH1–CH4
            mic_channels = [1, 2, 3, 4]
            mic_rms = avg_rms[mic_channels]           # RMS for CH1–CH4 only
            local_idx = int(np.argmax(mic_rms))       # index within mic_channels
            peak_ch = mic_channels[local_idx]         # actual channel number (1–4)

            print(f"  → Loudest *raw mic* channel (CH1–CH4): CH{peak_ch}")

            if peak_ch != ch:
                print(f"  [!] MISMATCH: Expected CH{ch}, measured strongest CH{peak_ch}")
            else:
                print(f"  [OK] CH{ch} correctly mapped.")
    finally:
        stream.stop()
        stream.close()

    print("\nChannel mapping check complete.\n")


# ---------------------------------------------------------------------
# Real-time DOA + optional SRP plot
# ---------------------------------------------------------------------


def run_realtime_validation(
    pipeline: DOAPipeline,
    audio_cfg: dict,
    duration: Optional[float],
    plot_srp: bool,
    log_dir: Path,
    capture_channels: int,
    mic_indices: Sequence[int],
) -> None:
    """
    Main real-time validation loop:
    - Captures blocks from sounddevice
    - Selects raw mic channels for DOA
    - Runs DOAPipeline
    - Logs tracks to JSONL
    - Prints per-frame DOA summary
    - Optionally updates a live SRP polar plot
    """
    device = audio_cfg.get("device", None)
    fs = int(audio_cfg["sample_rate"])
    block_size = int(audio_cfg["block_size"])

    # Sanity: pipeline mic count vs mic_indices
    n_mics_pipeline = len(mic_indices)
    if n_mics_pipeline != len(pipeline.geometry.mic_positions):
        raise RuntimeError(
            f"Pipeline geometry has {len(pipeline.geometry.mic_positions)} mics, "
            f"but mic_indices length is {n_mics_pipeline}."
        )

    # Open raw capture stream from ReSpeaker
    stream = sd.InputStream(
        device=device,
        samplerate=fs,
        blocksize=block_size,
        channels=capture_channels,
        dtype="float32",
    )

    # DOA logger
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"doa_validation_{int(time.time())}.jsonl"
    doa_logger = DOALogger(log_path)

    fps_meter = FpsMeter()

    # Optional SRP plot setup
    fig = None
    line = None
    az_rad = None

    if plot_srp:
        if not _HAS_MPL:
            print("WARNING: matplotlib not available, disabling SRP plot.")
            plot_srp = False
        else:
            plt.style.use("default")
            fig = plt.figure(figsize=(7, 7))
            ax = fig.add_subplot(111, projection="polar")

            az_deg = pipeline.azimuth_grid_deg
            az_rad = np.deg2rad(az_deg)
            P0 = np.zeros_like(az_rad)
            (line,) = ax.plot(az_rad, P0)

            ax.set_theta_zero_location("N")
            ax.set_theta_direction(-1)
            ax.set_title("Live SRP-PHAT Energy", fontsize=14)
            ax.set_ylim(0, 1.0)

    print("\n=== Real-time DOA Validation ===")
    print("Press Ctrl+C to stop.\n")

    stream.start()
    start_time = time.time()

    try:
        if plot_srp and fig is not None:
            # Light-weight animation; actual data update happens in audio loop
            def _update_plot(_frame):
                return (line,)

            _ = animation.FuncAnimation(
                fig,
                _update_plot,
                interval=50,
                blit=True,
            )

        while True:
            if duration is not None and (time.time() - start_time) >= duration:
                print("\nReached requested validation duration.")
                break

            data, _ = stream.read(block_size)  # shape (frames, capture_channels)
            block_all = data.T  # (capture_channels, samples)

            if block_all.shape[0] != capture_channels:
                # should never happen, but be defensive
                logger.warning(
                    "Unexpected channel count from device",
                    extra={
                        "expected": capture_channels,
                        "got": block_all.shape[0],
                    },
                )
                continue

            # ---------------------------------------------------------
            # ReSpeaker mapping: select raw mic channels CH1–CH4
            # ---------------------------------------------------------
            block_mics = block_all[mic_indices, :]  # (n_mics_pipeline, samples)

            results = pipeline.process_block(block_mics)

            for res in results:
                frame_idx = res["frame_index"]
                P_theta = res["P_theta"]
                candidates = res.get("doa_candidates", [])
                tracks = res.get("tracks", [])

                # Log tracks
                doa_logger.log_frame(
                    frame_index=frame_idx,
                    tracks=tracks,
                    timestamp_sec=time.time(),
                )

                # Print compact summary line
                line_txt = f"[Frame {frame_idx:6d}] "

                if len(candidates) > 0:
                    best = max(candidates, key=lambda c: c.power)
                    line_txt += (
                        f"Top cand: θ={best.azimuth_deg:7.2f}°, P={best.power:6.3f}  "
                    )
                else:
                    line_txt += "No DOA candidates  "

                if tracks:
                    line_txt += "Tracks:"
                    for tr in tracks:
                        line_txt += (
                            f" (ID {tr.id:2d} θ={tr.theta_deg:7.2f}° miss={tr.misses:2d})"
                        )
                else:
                    line_txt += "Tracks: none"

                fps = fps_meter.tick()
                if fps > 0:
                    line_txt += f"  | FPS={fps:5.1f}"

                print(line_txt)

                # Update SRP plot if enabled
                if plot_srp and line is not None and az_rad is not None:
                    if np.any(P_theta):
                        P_norm = P_theta / (np.max(P_theta) + 1e-9)
                    else:
                        P_norm = P_theta
                    line.set_ydata(P_norm)

            if plot_srp and fig is not None:
                plt.pause(0.001)

    except KeyboardInterrupt:
        print("\nStopping real-time validation (Ctrl+C).")
    finally:
        stream.stop()
        stream.close()
        doa_logger.close()
        if plot_srp and fig is not None:
            plt.close(fig)

        print(f"\nValidation log saved to: {log_path}")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Real-time DOA system validation for ReSpeaker on Orin Nano."
    )
    p.add_argument(
        "--pipeline-config",
        type=str,
        default="config/pipeline.yaml",
        help="Path to main pipeline YAML (default: config/pipeline.yaml)",
    )
    p.add_argument(
        "--no-channel-check",
        action="store_true",
        help="Skip interactive channel mapping check.",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Run duration in seconds (default: run until Ctrl+C).",
    )
    p.add_argument(
        "--plot-srp",
        action="store_true",
        help="Enable live SRP-PHAT polar plot (requires matplotlib).",
    )
    p.add_argument(
        "--log-dir",
        type=str,
        default="data/logs",
        help="Directory to store DOA JSONL logs.",
    )
    p.add_argument(
        "--list-devices-only",
        action="store_true",
        help="Just list audio input devices and exit.",
    )
    return p.parse_args()


def main():
    args = parse_args()

    if args.list_devices_only:
        print("\n=== Input Devices ===\n")
        devices = sd.query_devices()
        for idx, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                print(
                    f"[{idx}] {dev['name']} "
                    f"({dev['max_input_channels']} in / {dev['max_output_channels']} out)"
                )
        print()
        return

    # 1) Load pipeline config & build pipeline
    pipe_cfg, audio_cfg = load_pipeline_config(args.pipeline_config)
    pipeline = DOAPipeline(pipe_cfg)

    # Pipeline expects 4 microphones (ReSpeaker raw mics)
    pipeline_mics = len(pipeline.geometry.mic_positions)
    if pipeline_mics != 4:
        print(
            f"WARNING: geometry defines {pipeline_mics} mics; "
            "this script assumes a 4-mic ReSpeaker array."
        )

    # We always capture 6 channels from ReSpeaker 6-ch firmware
    capture_channels = RESPEAKER_CAPTURE_CHANNELS
    mic_indices = RESPEAKER_MIC_INDICES

    # 2) Device compatibility check
    check_device_compatibility(audio_cfg, capture_channels=capture_channels)

    # 3) Optional channel mapping check (on raw 6 channels)
    if not args.no_channel_check:
        run_channel_mapping_check(
            fs=int(audio_cfg["sample_rate"]),
            block_size=int(audio_cfg["block_size"]),
            device=audio_cfg.get("device", None),
        )


    # 4) Real-time validation run (using only CH1–CH4 for DOA)
    run_realtime_validation(
        pipeline=pipeline,
        audio_cfg=audio_cfg,
        duration=args.duration,
        plot_srp=args.plot_srp,
        log_dir=Path(args.log_dir),
        capture_channels=capture_channels,
        mic_indices=mic_indices,
    )


if __name__ == "__main__":
    main()
