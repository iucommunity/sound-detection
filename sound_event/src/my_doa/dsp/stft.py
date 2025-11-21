# src/my_doa/dsp/stft.py

"""
High-performance STFT utilities for multichannel DOA processing.

This file provides:
- STFTProcessor  → real-time streaming multichannel STFT
- stft_frame()   → single-frame helper

Designed for:
- 16 kHz audio
- 4-channel circular arrays (but works with N-mics)
- low-latency real-time DOA estimation
"""

from __future__ import annotations

from typing import List, Optional
import numpy as np

from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Window factory
# --------------------------------------------------------------------------- #

def create_window(window_type: str, frame_size: int) -> np.ndarray:
    """
    Create analysis window.

    Parameters
    ----------
    window_type : {'hann', 'hamming', 'rect'}
    frame_size : int

    Returns
    -------
    np.ndarray (float32)
    """
    win_type = window_type.lower()

    if win_type == "hann":
        w = np.hanning(frame_size)
    elif win_type == "hamming":
        w = np.hamming(frame_size)
    elif win_type == "rect":
        w = np.ones(frame_size)
    else:
        raise ValueError(f"Unsupported window type: {window_type}")

    return w.astype(np.float32)


# --------------------------------------------------------------------------- #
# Streaming STFT processor
# --------------------------------------------------------------------------- #

class STFTProcessor:
    """
    Streaming multichannel STFT processor.

    Accepts audio blocks of shape (n_mics, n_samples).
    Produces 0 or more STFT frames per call.

    Output each frame:
        shape = (n_mics, n_freq_bins)
        n_freq_bins = fft_size // 2 + 1

    Process:
        - maintain internal buffer
        - append new audio
        - extract as many overlapping frames as possible
    """

    def __init__(
        self,
        frame_size: int,
        hop_size: int,
        window_type: str = "hann",
        fft_size: Optional[int] = None,
    ):
        if not (0 < hop_size <= frame_size):
            raise ValueError("hop_size must be 0 < hop_size ≤ frame_size")

        self.frame_size = int(frame_size)
        self.hop_size = int(hop_size)
        self.fft_size = int(fft_size) if fft_size is not None else frame_size

        self.window = create_window(window_type, frame_size)
        self._buffer: Optional[np.ndarray] = None  # shape (n_mics, T)
        self._num_mics: Optional[int] = None

        logger.info(
            "STFTProcessor initialized",
            extra={
                "frame_size": self.frame_size,
                "hop_size": self.hop_size,
                "fft_size": self.fft_size,
                "window_type": window_type,
            },
        )

    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Reset internal buffer (e.g., on device restart)."""
        self._buffer = None
        self._num_mics = None
        logger.info("STFTProcessor reset")

    # ------------------------------------------------------------------ #

    def process_block(self, block: np.ndarray) -> List[np.ndarray]:
        """
        Consume new audio block and emit zero or more STFT frames.

        Parameters
        ----------
        block : np.ndarray (n_mics, n_samples)

        Returns
        -------
        list[np.ndarray]
            Each STFT frame of shape (n_mics, n_freq_bins)
        """
        block = np.asarray(block, dtype=np.float32)

        if block.ndim != 2:
            raise ValueError("block must be shaped (n_mics, n_samples)")

        n_mics, n_samples = block.shape

        if n_mics == 0 or n_samples == 0:
            return []

        # Initialize buffer
        if self._buffer is None:
            self._num_mics = n_mics
            self._buffer = block
        else:
            if n_mics != self._num_mics:
                raise ValueError(
                    f"Channel count changed: prev={self._num_mics}, new={n_mics}"
                )
            # Concatenate along time axis
            self._buffer = np.concatenate([self._buffer, block], axis=1)

        frames: List[np.ndarray] = []

        # ------------------------------------------------------------------ #
        # Extract STFT frames as long as buffer is large enough
        # ------------------------------------------------------------------ #
        while self._buffer.shape[1] >= self.frame_size:

            # Select frame (no copy)
            frame = self._buffer[:, : self.frame_size]

            # Apply analysis window
            windowed = frame * self.window[None, :]

            # FFT along time axis
            X = np.fft.rfft(windowed, n=self.fft_size, axis=1)
            X = X.astype(np.complex64, copy=False)

            frames.append(X)

            # Remove hop_size samples (soft ring-buffer behavior)
            self._buffer = self._buffer[:, self.hop_size :]

        return frames


# --------------------------------------------------------------------------- #
# Single-frame STFT helper
# --------------------------------------------------------------------------- #

def stft_frame(
    frame: np.ndarray,
    window_type: str = "hann",
    fft_size: Optional[int] = None,
) -> np.ndarray:
    """
    Compute STFT (rFFT) of a single multichannel time-domain frame.

    Parameters
    ----------
    frame : np.ndarray (n_mics, frame_size)
    window_type : str
    fft_size : int or None

    Returns
    -------
    np.ndarray (n_mics, n_freq_bins)
    """
    frame = np.asarray(frame, dtype=np.float32)
    if frame.ndim != 2:
        raise ValueError("frame must be shaped (n_mics, frame_size)")

    n_mics, frame_size = frame.shape
    fft_size = int(fft_size) if fft_size is not None else frame_size

    window = create_window(window_type, frame_size)
    windowed = frame * window[None, :]

    X = np.fft.rfft(windowed, n=fft_size, axis=1)
    return X.astype(np.complex64, copy=False)
