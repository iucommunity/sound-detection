# src/my_doa/dsp/gcc_phat.py

"""
GCC-PHAT computation for multichannel audio.

Given one STFT frame X[m, k] (m = mic index, k = frequency bin),
this module computes PHAT-weighted GCC correlation sequences for each
microphone pair (i, j). Output R_ij[t] is real-valued with zero-delay
at index N//2 (fftshift format).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import numpy as np

from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Helper: infer time length from rFFT size
# --------------------------------------------------------------------------- #

def _infer_time_length(n_freq_bins: int) -> int:
    """
    Infer time-domain length N for irfft, given rFFT bin count:

        n_freq_bins = N//2 + 1  →  N = 2*(n_freq_bins - 1)
    """
    return 2 * (n_freq_bins - 1)


# --------------------------------------------------------------------------- #
# Core PHAT function for one mic pair
# --------------------------------------------------------------------------- #

def compute_gcc_phat_for_pair(
    X_i: np.ndarray,
    X_j: np.ndarray,
    band_bins: Optional[Tuple[int, int]] = None,
    freq_weights: Optional[np.ndarray] = None,
    eps: float = 1e-8,
) -> np.ndarray:
    """
    Compute GCC-PHAT correlation R_ij[t] for one microphone pair (i, j).

    Parameters
    ----------
    X_i : (n_freq_bins,) complex ndarray
        STFT of mic i.
    X_j : same shape
        STFT of mic j.
    band_bins : (k_min, k_max) or None
        Optional band-limiting in frequency domain.
    eps : float
        Small constant to avoid division by zero.

    Returns
    -------
    r_shifted : (N,) float32 ndarray
        Real correlation sequence with zero delay at index N//2.
    """
    X_i = np.asarray(X_i, dtype=np.complex64)
    X_j = np.asarray(X_j, dtype=np.complex64)

    if X_i.shape != X_j.shape:
        raise ValueError("X_i and X_j must have identical shapes.")

    n_freq_bins = X_i.shape[0]
    N_time = _infer_time_length(n_freq_bins)

    # Cross power
    C_ij = X_i * np.conj(X_j)

    # ------------------------------------------------------------------ #
    # Band-limiting (robust)
    # ------------------------------------------------------------------ #
    if band_bins is not None:
        k_min, k_max = band_bins
        if k_min < 0 or k_max > n_freq_bins or k_min >= k_max:
            raise ValueError(
                f"Invalid band_bins={band_bins} for n_freq_bins={n_freq_bins}"
            )
        mask = np.zeros_like(C_ij, dtype=bool)
        mask[k_min:k_max] = True
        C_ij = np.where(mask, C_ij, 0.0 + 0.0j)

    # ------------------------------------------------------------------ #
    # PHAT weighting (robust against noise + silent bins)
    # ------------------------------------------------------------------ #
    mag = np.abs(C_ij)
    # Avoid NaN for zero-magnitude bins
    C_phat = C_ij / (mag + eps)

    # ------------------------------------------------------------------ #
    # Frequency weighting (w_freq * w_snr)
    # ------------------------------------------------------------------ #
    if freq_weights is not None:
        if freq_weights.shape[0] != n_freq_bins:
            raise ValueError(
                f"freq_weights length {freq_weights.shape[0]} != n_freq_bins {n_freq_bins}"
            )
        # Apply frequency weights (combines w_freq and w_snr)
        C_phat = C_phat * freq_weights.astype(np.complex64)

    # Rare case: NaN/Inf after normalization
    if not np.isfinite(C_phat).all():
        logger.warning("Non-finite values in GCC-PHAT; sanitizing.")
        C_phat = np.nan_to_num(C_phat, nan=0.0, posinf=0.0, neginf=0.0)

    # ------------------------------------------------------------------ #
    # IRFFT to obtain correlation
    # ------------------------------------------------------------------ #
    r = np.fft.irfft(C_phat, n=N_time)

    # Center zero-lag
    r_shifted = np.fft.fftshift(r)  # dtype float64 → cast below

    return r_shifted.astype(np.float32)


# --------------------------------------------------------------------------- #
# Compute GCC-PHAT for all microphone pairs
# --------------------------------------------------------------------------- #

def compute_gcc_phat_all(
    X: np.ndarray,
    mic_pairs: List[Tuple[int, int]],
    band_bins: Optional[Tuple[int, int]] = None,
    freq_weights: Optional[np.ndarray] = None,
    eps: float = 1e-8,
) -> Dict[Tuple[int, int], np.ndarray]:
    """
    Compute GCC-PHAT for all given microphone pairs.

    Parameters
    ----------
    X : ndarray (n_mics, n_freq_bins)
        STFT values for all microphones for a single frame.
    mic_pairs : list[(i, j)]
        Pairs of microphone indices with i < j.
    band_bins : (k_min, k_max) or None
        Optional band-limiting.
    eps : float
        Constant for PHAT stability.

    Returns
    -------
    dict : (i, j) → R_ij (np.ndarray, length N_time)
        Each R_ij is real-valued and fftshifted.
    """
    X = np.asarray(X, dtype=np.complex64)
    if X.ndim != 2:
        raise ValueError("X must be shaped (n_mics, n_freq_bins).")

    n_mics, n_freq_bins = X.shape
    out: Dict[Tuple[int, int], np.ndarray] = {}

    for (i, j) in mic_pairs:
        if not (0 <= i < n_mics and 0 <= j < n_mics):
            raise ValueError(
                f"Invalid mic index in pair {(i, j)} for {n_mics} microphones."
            )

        R_ij = compute_gcc_phat_for_pair(
            X_i=X[i],
            X_j=X[j],
            band_bins=band_bins,
            freq_weights=freq_weights,
            eps=eps,
        )
        out[(i, j)] = R_ij

    return out
