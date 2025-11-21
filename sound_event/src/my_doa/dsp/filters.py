# src/my_doa/dsp/filters.py

"""
High-quality filtering utilities for multichannel DOA preprocessing.

This module provides:
- design_highpass_sos()
- design_bandpass_sos()
- apply_filter()
- apply_filter_zero_phase()

Notes
-----
For DOA estimation:
    - Zero-phase filtering (filtfilt) is highly recommended.
    - SOS format ensures numerical stability on embedded hardware.
"""

from __future__ import annotations

from typing import Tuple, Literal
import numpy as np
from scipy.signal import butter, sosfilt, sosfiltfilt

from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# Filter Designers (Butterworth, stable SOS format)
# ============================================================

def design_highpass_sos(
    cutoff_hz: float,
    fs: float,
    order: int = 4,
) -> np.ndarray:
    """
    Design a Butterworth high-pass filter in SOS format.

    Parameters
    ----------
    cutoff_hz : float
        High-pass cutoff frequency.
    fs : float
        Sampling rate.
    order : int
        Filter order.

    Returns
    -------
    sos : np.ndarray
        Second-order-section coefficients.
    """
    if cutoff_hz <= 0 or cutoff_hz >= fs * 0.5:
        raise ValueError("cutoff_hz must lie within (0, Nyquist).")

    sos = butter(order, cutoff_hz / (0.5 * fs), btype="highpass", output="sos")

    logger.info(
        "Designed high-pass SOS filter",
        extra={"cutoff_hz": cutoff_hz, "fs": fs, "order": order},
    )
    return sos.astype(np.float32)


def design_bandpass_sos(
    low_hz: float,
    high_hz: float,
    fs: float,
    order: int = 4,
) -> np.ndarray:
    """
    Design a Butterworth bandpass filter in SOS format.

    Parameters
    ----------
    low_hz : float
        Lower cutoff.
    high_hz : float
        Upper cutoff.
    fs : float
        Sample rate.
    order : int
        Filter order.

    Returns
    -------
    sos : np.ndarray
        Second-order-section filter coefficients.
    """
    if not (0 < low_hz < high_hz < fs * 0.5):
        raise ValueError("Bandpass cutoff frequencies must lie within (0, Nyquist).")

    sos = butter(order, [low_hz / (0.5 * fs), high_hz / (0.5 * fs)],
                 btype="bandpass", output="sos")

    logger.info(
        "Designed band-pass SOS filter",
        extra={
            "low_hz": low_hz,
            "high_hz": high_hz,
            "fs": fs,
            "order": order,
        },
    )
    return sos.astype(np.float32)


# ============================================================
# Filtering Utilities
# ============================================================

def apply_filter(
    sos: np.ndarray,
    audio: np.ndarray,
    mode: Literal["causal", "zero_phase"] = "zero_phase",
) -> np.ndarray:
    """
    Apply an SOS filter to multichannel audio.

    Parameters
    ----------
    sos : np.ndarray
        SOS filter coefficients.
    audio : np.ndarray
        Audio array (n_mics, n_samples).
    mode : {"causal", "zero_phase"}
        - "zero_phase": uses filtfilt (recommended for DOA).
        - "causal": uses sosfilt for low-latency applications.

    Returns
    -------
    filtered : np.ndarray
        Same shape as `audio`.
    """
    audio = np.asarray(audio, dtype=np.float32)

    if audio.ndim != 2:
        raise ValueError("audio must have shape (n_mics, n_samples).")

    n_mics, n_samples = audio.shape

    # Vectorized filtering
    filtered = np.empty_like(audio)

    if mode == "zero_phase":
        # No phase distortion—best for DOA
        for m in range(n_mics):
            filtered[m] = sosfiltfilt(sos, audio[m])
    else:
        # Causal, low-latency option
        for m in range(n_mics):
            filtered[m] = sosfilt(sos, audio[m])

    return filtered


# ============================================================
# Convenience presets
# ============================================================

def design_wind_reduction_highpass(fs: float) -> np.ndarray:
    """
    Convenience function: high-pass to suppress wind/rumble noise.

    For outdoor microphones, wind energy is mostly < 150 Hz.

    Recommended cutoff:
        120 Hz for speech-oriented DOA
        80 Hz for general-purpose DOA (vehicles, etc.)

    Returns
    -------
    sos : np.ndarray
    """
    cutoff = 120.0  # tuned value
    return design_highpass_sos(cutoff_hz=cutoff, fs=fs, order=4)


# ============================================================
# Compatibility wrappers (for scripts expecting old API)
# ============================================================

def design_highpass(
    cutoff_hz: float,
    fs: float,
    order: int = 4,
) -> np.ndarray:
    """
    Compatibility wrapper for design_highpass_sos().
    
    Returns SOS filter coefficients (not (b, a) tuple).
    Scripts should use apply_filter(sos, audio) instead of apply_filter(b, a, audio).
    
    Parameters
    ----------
    cutoff_hz : float
        High-pass cutoff frequency.
    fs : float
        Sampling rate.
    order : int
        Filter order.

    Returns
    -------
    sos : np.ndarray
        Second-order-section coefficients.
    """
    return design_highpass_sos(cutoff_hz=cutoff_hz, fs=fs, order=order)


def design_bandpass(
    low_hz: float,
    high_hz: float,
    fs: float,
    order: int = 4,
) -> np.ndarray:
    """
    Compatibility wrapper for design_bandpass_sos().
    
    Returns SOS filter coefficients (not (b, a) tuple).
    Scripts should use apply_filter(sos, audio) instead of apply_filter(b, a, audio).
    
    Parameters
    ----------
    low_hz : float
        Lower cutoff.
    high_hz : float
        Upper cutoff.
    fs : float
        Sample rate.
    order : int
        Filter order.

    Returns
    -------
    sos : np.ndarray
        Second-order-section filter coefficients.
    """
    return design_bandpass_sos(low_hz=low_hz, high_hz=high_hz, fs=fs, order=order)