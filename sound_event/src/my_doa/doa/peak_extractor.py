# src/my_doa/doa/peak_extractor.py

"""
Peak extraction for SRP-PHAT azimuth maps.

Given steered response power P(theta) over an azimuth grid, this module
extracts up to max_sources peaks with circular suppression to avoid
duplicate detections for the same physical source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from src.my_doa.utils.logger import get_logger
from src.my_doa.utils.math_utils import wrap_angle_deg, wrap_angle_deg_0_360, circular_distance_deg

logger = get_logger(__name__)


# --------------------------------------------------------------------------
#  Dataclass for DOA candidates
# --------------------------------------------------------------------------

@dataclass
class DOACandidate:
    """
    Represents a pre-tracking DOA candidate.

    Attributes
    ----------
    azimuth_deg : float
        DOA azimuth in degrees, normalized to [-180, 180).
    power : float
        Steered response power at this direction.
    index : int
        Index into the azimuth grid.
    """
    azimuth_deg: float
    power: float
    index: int


# --------------------------------------------------------------------------
#  Peak extractor
# --------------------------------------------------------------------------

class PeakExtractor:
    """
    Extract DOA peaks from an SRP-PHAT azimuth power map.

    Parameters
    ----------
    azimuth_grid_deg : np.ndarray
        Array of azimuth angles (deg), shape (N,).
    max_sources : int
        Maximum number of DOA peaks to extract.
    min_power : float
        Minimum SRP power threshold for accepting peaks.
    suppression_deg : float
        Angular region in degrees to suppress around each selected peak
        to prevent duplicate detections.
    """

    def __init__(
        self,
        azimuth_grid_deg: np.ndarray,
        max_sources: int = 3,
        min_power: float = 0.1,
        suppression_deg: float = 15.0,
    ):
        self.azimuth_grid_deg = np.asarray(azimuth_grid_deg, dtype=float)
        self.max_sources = int(max_sources)
        self.min_power = float(min_power)
        self.suppression_deg = float(suppression_deg)

        if self.azimuth_grid_deg.ndim != 1:
            raise ValueError("azimuth_grid_deg must be a 1D array.")

        logger.info(
            "PeakExtractor initialized",
            extra={
                "n_angles": len(self.azimuth_grid_deg),
                "max_sources": self.max_sources,
                "min_power": self.min_power,
                "suppression_deg": self.suppression_deg,
            },
        )

    # ------------------------------------------------------------------

    def extract(self, P_theta: np.ndarray) -> List[DOACandidate]:
        """
        Extract DOA candidates from steered response power P(theta).

        Parameters
        ----------
        P_theta : np.ndarray
            SRP-PHAT power over azimuth, shape (N,).

        Returns
        -------
        List[DOACandidate]
            List of up to max_sources sorted by descending power.
        """
        P = np.asarray(P_theta, dtype=float)

        if P.ndim != 1:
            raise ValueError("P_theta must be 1D array.")

        if P.shape[0] != len(self.azimuth_grid_deg):
            raise ValueError("P_theta length does not match azimuth grid.")

        # Clean NaN/Inf (rare but can appear in degenerate FFT frames)
        if not np.isfinite(P).all():
            logger.warning("Non-finite SRP values detected; replacing with 0.")
            P = np.nan_to_num(P, nan=0.0, posinf=0.0, neginf=0.0)

        work = P.copy()
        candidates: List[DOACandidate] = []

        for _ in range(self.max_sources):

            # ---- Find strongest remaining peak ----
            idx = int(np.argmax(work))
            peak_power = float(work[idx])

            if peak_power < self.min_power:
                break  # no usable peaks left

            az = float(self.azimuth_grid_deg[idx])
            # Keep in 0-360 range (azimuth_grid is already 0-360)
            az_wrapped = wrap_angle_deg_0_360(az)

            candidates.append(
                DOACandidate(
                    azimuth_deg=az_wrapped,
                    power=peak_power,
                    index=idx,
                )
            )

            # ---- Suppress neighborhood ----
            work = self._suppress_neighborhood(work, idx)

        # Ensure descending order (just for safety)
        candidates.sort(key=lambda c: c.power, reverse=True)
        return candidates

    # ------------------------------------------------------------------

    def _suppress_neighborhood(self, P: np.ndarray, idx_center: int) -> np.ndarray:
        """
        Zero out a circular angular neighborhood around a chosen peak.

        This suppresses multiple detections of the same physical source.

        Parameters
        ----------
        P : np.ndarray
            Current SRP array.
        idx_center : int
            Index of selected peak in azimuth grid.

        Returns
        -------
        np.ndarray
            Modified SRP array with suppressed region.
        """
        center_angle = self.azimuth_grid_deg[idx_center]

        # Vectorized circular distance computation
        distances = np.abs(
            circular_distance_deg(center_angle, self.azimuth_grid_deg)
        )

        mask = distances <= self.suppression_deg

        P_new = P.copy()
        P_new[mask] = 0.0

        return P_new
