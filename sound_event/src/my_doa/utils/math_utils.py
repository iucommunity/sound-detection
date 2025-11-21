# src/my_doa/utils/math_utils.py

"""
High-performance math utilities for DOA processing.

Features:
---------
• Vectorized angle wrapping in degrees & radians
• Stable circular mean supporting float32 or float64
• Fast 1D linear interpolation for fractional-delay GCC sampling
• NaN-safe angle operations
• Numba-safe design (no Python side-effects)

This module is performance-critical and used in:
    - GCC-PHAT fractional delay sampling
    - SRP-PHAT angle search
    - Tracker angle math
"""

from __future__ import annotations

import numpy as np
import math
from typing import Iterable, Sequence


# ================================================================
# Angle Conversions (scalar or vector)
# ================================================================

def deg2rad(x):
    """Convert degrees to radians."""
    return np.asarray(x) * (math.pi / 180.0)


def rad2deg(x):
    """Convert radians to degrees."""
    return np.asarray(x) * (180.0 / math.pi)


# ================================================================
# Angle Wrapping (Fast, Vectorized, NaN Safe)
# ================================================================

def wrap_angle_rad(angle):
    """
    Wrap to [-pi, pi). Works for scalar or array.
    """
    a = np.asarray(angle)
    return (a + np.pi) % (2.0 * np.pi) - np.pi


def wrap_angle_deg(angle):
    """
    Wrap to [-180, 180). Works for scalar or array.
    """
    a = np.asarray(angle)
    return (a + 180.0) % 360.0 - 180.0


def wrap_angle_deg_0_360(angle):
    """
    Wrap to [0, 360). Works for scalar or array.
    
    Useful for output display when mic positions are defined in 0-360 range
    (e.g., ReSpeaker mics at 45°, 135°, 225°, 315°).
    """
    a = np.asarray(angle)
    return a % 360.0


# ================================================================
# Circular Distance (Shortest signed distance)
# ================================================================

def circular_distance_rad(a, b):
    """
    Signed shortest distance a → b in radians.
    Vectorized.
    """
    a = np.asarray(a)
    b = np.asarray(b)
    return wrap_angle_rad(b - a)


def circular_distance_deg(a, b):
    """
    Signed shortest distance a → b in degrees.
    Vectorized.
    """
    a = np.asarray(a)
    b = np.asarray(b)
    return wrap_angle_deg(b - a)


# ================================================================
# Circular Mean (Deg) – Stable & Vectorized
# ================================================================

def circular_mean_deg(angles_deg: Sequence[float], weights: Sequence[float] | None = None) -> float:
    """
    Compute circular mean of angles in degrees.

    Stable even for large angle sets and near-cancelling vectors.
    """
    angles = np.asarray(angles_deg, dtype=np.float64)
    ang_rad = np.deg2rad(angles)

    if weights is None:
        w = np.ones_like(ang_rad)
    else:
        w = np.asarray(weights, dtype=np.float64)
        if w.shape != ang_rad.shape:
            raise ValueError("weights shape must match angles shape")

    C = np.sum(w * np.cos(ang_rad))
    S = np.sum(w * np.sin(ang_rad))

    # Degenerate: no direction
    if C == 0.0 and S == 0.0:
        return 0.0

    mean_rad = math.atan2(S, C)
    return float(rad2deg(mean_rad))


# ================================================================
# Interpolation (Fast fractional sampling)
# ================================================================

def linear_interp_1d(x: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """
    Fast vectorized linear interpolation.

    Designed for fractional-delay GCC sampling:
        R_hat(theta) = R_ij[ center + tau_samples(theta) ]

    Parameters
    ----------
    x : np.ndarray (N,)
        Real-valued array (GCC correlation).
    positions : np.ndarray (M,)
        Fractional indices.

    Returns
    -------
    np.ndarray (M,)
        Interpolated samples.
    """
    x = np.asarray(x, dtype=np.float32)
    pos = np.asarray(positions, dtype=np.float32)

    N = x.shape[0]
    if N == 0:
        raise ValueError("Input array x must not be empty.")

    # Clip positions into valid range
    pos_clipped = np.clip(pos, 0.0, N - 1)

    i0 = np.floor(pos_clipped).astype(np.int32)
    i1 = np.minimum(i0 + 1, N - 1)

    frac = pos_clipped - i0

    return (1.0 - frac) * x[i0] + frac * x[i1]


# ================================================================
# Utility Helpers
# ================================================================

def ensure_1d_array(x: Iterable[float] | np.ndarray, dtype=float) -> np.ndarray:
    """
    Convert input to 1D numpy array of specified dtype.
    """
    arr = np.asarray(x, dtype=dtype)
    return arr.reshape(-1)
