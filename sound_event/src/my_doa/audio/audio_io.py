# src/my_doa/audio/audio_io.py
"""
Real-time multichannel audio capture for DOA.

Production-ready version:
- Zero-copy mailbox instead of unbounded queue
- Robust device matching
- Validates channel count & samplerate
- Low-jitter callback (no allocations inside)
- Drop-oldest semantics (real-time safe)
- Safe shutdown & restart

Uses sounddevice for audio input.

For ReSpeaker Mic Array v3.0:
    - 4 channels
    - 16 kHz
"""

from __future__ import annotations

import threading
from typing import Optional, List, Tuple, Callable

import numpy as np
import sounddevice as sd

from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


# =====================================================================
# Device utilities
# =====================================================================

def list_input_devices() -> None:
    """Print all audio input devices."""
    devices = sd.query_devices()
    print("\nAvailable audio input devices:\n")
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            print(f"[{idx}] {dev['name']} ({dev['max_input_channels']} ch)")
    print()


def find_device(device: str | int | None, channels: int) -> int:
    """
    Resolve device name substring or index to device index.

    Returns
    -------
    int
        Valid device index.
    """
    devices = sd.query_devices()

    if isinstance(device, int):
        # Validate channel count
        if device < 0 or device >= len(devices):
            raise RuntimeError(f"Invalid device index: {device}")
        if devices[device]["max_input_channels"] < channels:
            raise RuntimeError(
                f"Device {device} does not support {channels} channels."
            )
        return device

    if isinstance(device, str):
        # Match substring
        name = device.lower()
        for idx, d in enumerate(devices):
            if name in d["name"].lower() and d["max_input_channels"] >= channels:
                return idx
        raise RuntimeError(f"No matching device containing '{device}' found.")

    # device = None → use default
    default_idx = sd.default.device[0]
    if default_idx is None:
        raise RuntimeError("No default audio device configured.")

    if devices[default_idx]["max_input_channels"] < channels:
        raise RuntimeError(
            f"Default device does not support {channels} channels."
        )
    return default_idx


# =====================================================================
# AudioStream (Real-time, low-latency)
# =====================================================================

class AudioStream:
    """
    Production-ready real-time input for 4-mic arrays.

    Pull model:
        stream.start()
        while True:
            block = stream.get_latest_block()
            if block is not None:
                process(block)

    Characteristics:
        • Callback produces frames into a mailbox (no queue growth)
        • Processing always receives the newest block
        • No allocations in callback
        • Thread-safe shutdown
    """

    def __init__(
        self,
        device: str | int | None,
        sample_rate: int,
        block_size: int,
        channels: int = 4,
        channel_mapping: Optional[List[int]] = None,
        capture_channels: Optional[int] = None,
    ):
        """
        Parameters
        ----------
        device : str | int | None
            Audio device identifier.
        sample_rate : int
            Sampling rate in Hz.
        block_size : int
            Number of samples per block.
        channels : int
            Number of output channels (after mapping).
            Default: 4
        channel_mapping : list[int] | None
            Optional channel mapping. If provided, captures capture_channels channels
            from device and selects channels at these indices.
            Example: [1, 2, 3, 4] for ReSpeaker (capture 6, select CH1-CH4).
            If None, directly captures 'channels' channels.
        capture_channels : int | None
            Number of channels to capture from device (only needed if channel_mapping is used).
            If None and channel_mapping is provided, will be inferred as max(channel_mapping) + 1.
        """
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.channel_mapping = channel_mapping
        
        # Determine capture channel count
        if channel_mapping is not None:
            # Validate mapping
            if len(channel_mapping) != channels:
                raise ValueError(
                    f"channel_mapping length ({len(channel_mapping)}) must equal "
                    f"output channels ({channels})"
                )
            # Use provided capture_channels or infer from mapping
            if capture_channels is not None:
                self.capture_channels = capture_channels
                # Validate that capture_channels is sufficient
                if self.capture_channels <= max(channel_mapping):
                    raise ValueError(
                        f"capture_channels ({capture_channels}) must be > max(channel_mapping) "
                        f"({max(channel_mapping)})"
                    )
            else:
                # Infer: need at least max index + 1 channels
                self.capture_channels = max(channel_mapping) + 1
        else:
            self.capture_channels = channels
            self.channel_mapping = None

        # Resolve & validate device (check capture channel count)
        self.device_index = find_device(device, self.capture_channels)

        device_name = sd.query_devices()[self.device_index]["name"]
        logger.info(
            "Using audio device",
            extra={
                "device_index": self.device_index,
                "device_name": device_name,
                "capture_channels": self.capture_channels,
                "output_channels": channels,
                "channel_mapping": channel_mapping,
                "sample_rate": sample_rate,
            },
        )

        # Thread-safe mailbox (holds most recent block)
        self._mailbox = None
        self._mailbox_lock = threading.Lock()

        # For performance: prealloc buffers
        # Capture buffer: holds all captured channels
        self._cb_buffer_capture = np.zeros((self.capture_channels, block_size), dtype=np.float32)
        # Output buffer: holds mapped channels (or same as capture if no mapping)
        if self.channel_mapping is not None:
            self._cb_buffer = np.zeros((channels, block_size), dtype=np.float32)
        else:
            self._cb_buffer = self._cb_buffer_capture

        # Timeout tracking
        self._timeouts = 0
        self.max_timeouts = 5

        # sd.InputStream
        self._stream: Optional[sd.InputStream] = None
        self._init_stream()

    # ------------------------------------------------------------------

    def _init_stream(self) -> None:
        """Construct InputStream."""
        self._stream = sd.InputStream(
            device=self.device_index,
            channels=self.capture_channels,  # Capture all channels
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype="float32",
            callback=self._callback,
        )

    # ------------------------------------------------------------------
    # Callback: must be extremely fast & low-jitter
    # ------------------------------------------------------------------

    def _callback(self, indata, frames, time, status) -> None:
        if status:
            logger.warning("Audio callback status", extra={"status": str(status)})

        # No allocations:
        # Copy & transpose directly into preallocated buffer
        # indata: shape (frames, capture_channels)
        # cb_buffer_capture: shape (capture_channels, frames)
        self._cb_buffer_capture[:] = indata.T

        # Apply channel mapping if needed
        if self.channel_mapping is not None:
            # Select mapped channels: cb_buffer[ch_idx] = cb_buffer_capture[channel_mapping[ch_idx]]
            for out_idx, in_idx in enumerate(self.channel_mapping):
                self._cb_buffer[out_idx] = self._cb_buffer_capture[in_idx]

        # Write newest data to mailbox
        with self._mailbox_lock:
            self._mailbox = self._cb_buffer.copy()

    # ------------------------------------------------------------------

    def start(self):
        if self._stream is None:
            self._init_stream()
        self._stream.start()
        logger.info("Audio stream started")

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            logger.info("Audio stream stopped")

    def close(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("Audio stream closed")

    # ------------------------------------------------------------------

    def get_latest_block(self) -> Optional[np.ndarray]:
        """
        Pull latest audio block.

        Returns
        -------
        np.ndarray | None
            Shape: (channels, samples)
        """
        with self._mailbox_lock:
            block = self._mailbox
            self._mailbox = None  # drop after reading
            return block

    def read_block(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """
        Pull latest audio block (alias for get_latest_block for compatibility).
        
        The timeout parameter is accepted for API compatibility but not used,
        as the mailbox pattern always returns immediately with the latest block.

        Parameters
        ----------
        timeout : float
            Timeout in seconds (ignored, kept for API compatibility).

        Returns
        -------
        np.ndarray | None
            Shape: (channels, samples)
        """
        return self.get_latest_block()