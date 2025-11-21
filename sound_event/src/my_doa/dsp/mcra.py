# src/my_doa/dsp/mcra.py
"""
Robust MCRA (Minima-Controlled Recursive Averaging) noise estimator.

This implementation is engineered for real-time DOA preprocessing:
- stable noise floor for GCC-PHAT
- resistant to outdoor wind noise & impulsive noise
- minimal latency impact
- numerically robust

Based on Cohen & Berdugo (2002), but simplified and stabilized
for low-power embedded systems and microphone arrays.
"""

from __future__ import annotations
from typing import Optional
import numpy as np

from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


class MCRA:
    """
    Robust MCRA noise estimator.

    Parameters
    ----------
    n_freq : int
        Number of frequency bins.
    alpha_s : float
        Spectrum smoothing factor (0.7–0.98).
    minima_window : int
        Local minima tracking window length (frames).
    delta : float
        Noise floor scale factor (1.3–2.0).
    eps_floor : float
        Minimum noise floor to prevent GCC-PHAT instability.
    """

    def __init__(
        self,
        n_freq: int,
        alpha_s: float = 0.85,
        minima_window: int = 15,
        delta: float = 1.5,
        alpha_d: float = 0.1,
        eps_floor: float = 1e-8,
    ):
        self.n_freq = int(n_freq)

        if not (0 < alpha_s < 1):
            raise ValueError("alpha_s must be in (0, 1).")
        if minima_window < 1:
            raise ValueError("minima_window must be >= 1.")

        self.alpha_s = float(alpha_s)
        self.minima_window = int(minima_window)
        self.delta = float(delta)
        self.alpha_d = float(alpha_d)
        self.eps_floor = float(eps_floor)

        # State
        self.S: Optional[np.ndarray] = None
        self.N_hat: Optional[np.ndarray] = None
        self._min_buffer: Optional[np.ndarray] = None
        self._min_index: int = 0
        self._p_speech: Optional[np.ndarray] = None  # speech presence probability

        logger.info(
            "MCRA initialized",
            extra={
                "n_freq": self.n_freq,
                "alpha_s": self.alpha_s,
                "minima_window": self.minima_window,
                "delta": self.delta,
                "alpha_d": self.alpha_d,
            },
        )

    # ------------------------------------------------------------------ #
    # Reset state
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        self.S = None
        self.N_hat = None
        self._min_buffer = None
        self._min_index = 0
        self._p_speech = None
        logger.info("MCRA state reset")

    # ------------------------------------------------------------------ #
    # Core update
    # ------------------------------------------------------------------ #

    def update(self, power_spectrum: np.ndarray) -> np.ndarray:
        """
        Update noise estimate.

        Parameters
        ----------
        power_spectrum : np.ndarray (n_freq,)
            Power spectrum |X(k)|^2, typically averaged over microphones.

        Returns
        -------
        N_hat : np.ndarray (n_freq,)
        """
        P = np.asarray(power_spectrum, dtype=np.float32)
        if P.ndim != 1 or P.shape[0] != self.n_freq:
            raise ValueError("power_spectrum must be 1D of length n_freq.")

        # Safety: prevent negative or NaN inputs
        P = np.maximum(P, 0.0)
        P = np.nan_to_num(P, nan=0.0, posinf=0.0, neginf=0.0)

        # Initialize on first frame
        if self.S is None:
            self.S = P.copy()
            self.N_hat = np.maximum(self.delta * self.S, self.eps_floor)
            self._min_buffer = np.tile(self.S[None, :], (self.minima_window, 1))
            self._p_speech = np.zeros(self.n_freq, dtype=np.float32)
            logger.info("MCRA state initialized")
            return self.N_hat.copy()

        # ------------------------------------------------------------------ #
        # Step 1: Smoothed spectrum update
        # ------------------------------------------------------------------ #
        self.S = self.alpha_s * self.S + (1.0 - self.alpha_s) * P

        # ------------------------------------------------------------------ #
        # Step 2: Speech presence probability update (optional but important)
        # ------------------------------------------------------------------ #
        # Ratio test: large ratio → likely speech → do NOT update minima buffer
        R = P / (self.N_hat + self.eps_floor)
        R = np.nan_to_num(R, nan=1.0)

        p = np.clip(R - 1.0, 0.0, None)
        p = np.clip(p / (p + 1.0), 0.0, 1.0)  # normalized speech-prob signal

        self._p_speech = (
            self.alpha_d * self._p_speech + (1 - self.alpha_d) * p
        )

        # ------------------------------------------------------------------ #
        # Step 3: Conditioned minima update
        #       If speech is likely → freeze minima update
        # ------------------------------------------------------------------ #
        update_mask = self._p_speech < 0.5  # speech presence < 50%

        # Insert new S(k) only where allowed
        new_min_row = self._min_buffer[self._min_index]
        np.copyto(new_min_row, self.S, where=update_mask)

        self._min_index = (self._min_index + 1) % self.minima_window

        # ------------------------------------------------------------------ #
        # Step 4: Compute new noise estimate
        # ------------------------------------------------------------------ #
        min_vals = np.min(self._min_buffer, axis=0)
        N_new = self.delta * min_vals

        # Stabilize small bins
        N_new = np.maximum(N_new, self.eps_floor)

        # Smooth noise estimate (avoid flicker)
        self.N_hat = 0.8 * self.N_hat + 0.2 * N_new

        return self.N_hat.copy()
