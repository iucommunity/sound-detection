# src/my_doa/geometry/tdoa_lut.py

"""
Precomputed TDOA lookup tables for all microphone pairs and azimuth angles.

This module:
- Precomputes fractional TDOA in samples for each (i, j) pair and azimuth
- Validates geometry consistency
- Applies far-field model (default) with optional near-field support
- Ensures float32 performance for real-time SRP-PHAT

Used directly by SRPScanner to avoid repeated geometry math per frame.
"""

from __future__ import annotations

import numpy as np
from typing import Dict, Tuple, List

from src.my_doa.utils.logger import get_logger


logger = get_logger(__name__)


class TDOALUT:
    """
    Precomputed TDOA lookup for azimuth-only DOA.

    Parameters
    ----------
    mic_positions : np.ndarray (M, 3)
        Microphone positions in meters.
    fs : float
        Sampling rate.
    c : float
        Speed of sound (m/s).
    azimuth_grid_deg : np.ndarray
        Azimuth grid (must be sorted).
    mic_pairs : list[(i, j)]
        Microphone index pairs (i < j).

    Attributes
    ----------
    delay_samples : dict[(i,j)] -> np.ndarray (num_angles,)
        Fractional delays in samples.
    delay_seconds : dict[(i,j)] -> np.ndarray (num_angles,)
        Same delays but in seconds.
    """

    def __init__(
        self,
        mic_positions: np.ndarray,
        fs: float,
        c: float,
        azimuth_grid_deg: np.ndarray,
        mic_pairs: List[Tuple[int, int]],
        near_field: bool = False,
    ):
        self.positions = np.asarray(mic_positions, dtype=np.float32)
        self.fs = float(fs)
        self.c = float(c)
        self.mic_pairs = mic_pairs
        self.near_field = bool(near_field)

        az = np.asarray(azimuth_grid_deg, dtype=np.float32)
        if az.ndim != 1:
            raise ValueError("azimuth_grid_deg must be 1D.")
        if not np.all(np.diff(az) >= 0):
            raise ValueError("Azimuth grid must be sorted ascending.")
        self.azimuth_grid_deg = az
        self.azimuth_grid_rad = np.deg2rad(az)

        # Precompute unit vectors u(theta)
        self._unit_vectors = self._compute_unit_vectors()

        # Precompute TDOAs
        self.delay_seconds, self.delay_samples = self._precompute_tdoa()

        logger.info(
            "TDOA LUT generated",
            extra={
                "num_angles": len(self.azimuth_grid_deg),
                "num_pairs": len(self.mic_pairs),
                "near_field": self.near_field,
            },
        )

    # ------------------------------------------------------------------ #
    # Unit vector generation
    # ------------------------------------------------------------------ #
    def _compute_unit_vectors(self) -> np.ndarray:
        """
        Compute unit direction vectors for each azimuth.
        
        Standard mathematical convention: 0° = +X (east), 90° = +Y (north)
        Unit vector: [cos(θ), sin(θ), 0]
        - 0° → [1, 0, 0] (east/+X)
        - 90° → [0, 1, 0] (north/+Y)
        - 180° → [-1, 0, 0] (west/-X)
        - 270° → [0, -1, 0] (south/-Y)
        """
        az = self.azimuth_grid_rad
        u = np.stack([np.cos(az), np.sin(az), np.zeros_like(az)], axis=1)
        return u.astype(np.float32)

    # ------------------------------------------------------------------ #
    # Main precomputation
    # ------------------------------------------------------------------ #
    def _precompute_tdoa(self):
        """
        Compute fractional sample delays for all (i, j) mic pairs and all angles.

        Far-field formula:
            tau = ((r_i - r_j) · u(theta)) / c

        Near-field (optional):
            tau = (||s - r_j|| - ||s - r_i||) / c
            with s at unit direction scaled far away → used for spherical correction.
        """

        u = self._unit_vectors
        positions = self.positions
        fs = self.fs
        c = self.c

        delay_seconds: Dict[Tuple[int, int], np.ndarray] = {}
        delay_samples: Dict[Tuple[int, int], np.ndarray] = {}

        for (i, j) in self.mic_pairs:
            r_i = positions[i]
            r_j = positions[j]
            rij = (r_i - r_j).astype(np.float32)  # (3,)

            if not self.near_field:
                # -------------------------
                # Far-field TDOA
                # -------------------------
                # TDOA: time delay of arrival at mic i relative to mic j
                # tau = ((r_i - r_j) · u(theta)) / c
                # 
                # For GCC-PHAT correlation R_ij[tau], the convention is:
                # R_ij[tau] peaks when tau = delay from mic j to mic i
                # If source is closer to mic i, mic i receives signal earlier,
                # so we need to negate to match GCC-PHAT indexing convention
                proj = u @ rij  # shape (num_angles,)
                tau_sec = -proj / c  # Negate to match GCC-PHAT convention

            else:
                # -------------------------
                # Near-field option
                # -------------------------
                # Spherical wavefront approximation:
                # source direction vector s = u(theta) * large_radius
                R = 100.0  # 100 m "effectively far but spherical"
                s = u * R  # (num_angles,3)

                d_i = np.linalg.norm(s - r_i[None, :], axis=1)
                d_j = np.linalg.norm(s - r_j[None, :], axis=1)

                tau_sec = (d_j - d_i) / c

            # Convert to fractional samples
            tau_samp = tau_sec * fs

            # Consistency: ensure float32
            delay_seconds[(i, j)] = tau_sec.astype(np.float32)
            delay_samples[(i, j)] = tau_samp.astype(np.float32)

        # Validate symmetric behavior (i,j) vs (j,i)
        self._validate_symmetry(delay_seconds)

        return delay_seconds, delay_samples

    # ------------------------------------------------------------------ #
    # Symmetry validation
    # ------------------------------------------------------------------ #
    def _validate_symmetry(self, delay_seconds: Dict[Tuple[int, int], np.ndarray]):
        """
        Validate that TDOA symmetry holds:
            tau_ij = -tau_ji   (approx)
        """
        tol = 1e-4  # small tolerance due to float32

        for (i, j) in self.mic_pairs:
            # If reverse pair exists
            if (j, i) in self.mic_pairs:
                tau_ij = delay_seconds[(i, j)]
                tau_ji = delay_seconds[(j, i)]
                if not np.allclose(tau_ij, -tau_ji, atol=tol):
                    logger.warning(
                        "TDOA symmetry check failed",
                        extra={
                            "pair": (i, j),
                            "max_error": float(np.max(np.abs(tau_ij + tau_ji))),
                        },
                    )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get_delays(self, i: int, j: int) -> np.ndarray:
        """Get fractional delay (in samples) for mic pair (i, j)."""
        return self.delay_samples[(i, j)]

    def get_seconds(self, i: int, j: int) -> np.ndarray:
        """Get delay (in seconds) for mic pair (i, j)."""
        return self.delay_seconds[(i, j)]
