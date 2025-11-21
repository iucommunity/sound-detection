# src/my_doa/doa/srp_scan.py

"""
SRP-PHAT azimuth scanning using precomputed TDOA lookup tables.

Given GCC-PHAT correlation functions R_ij[tau] for each microphone pair,
and a TDOALUT providing fractional delays (in samples) for each azimuth angle,
this module computes the SRP-PHAT steered response power P(theta).
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from src.my_doa.geometry.tdoa_lut import TDOALUT
from src.my_doa.utils.logger import get_logger
from src.my_doa.utils.math_utils import linear_interp_1d

logger = get_logger(__name__)


class SRPScanner:
    """
    SRP-PHAT scanner for azimuth-only DOA.

    Parameters
    ----------
    tdoa_lut : TDOALUT
        Precomputed lookup table of fractional TDOAs (samples) for
        each microphone pair and each azimuth angle.

    Attributes
    ----------
    azimuth_grid_deg : np.ndarray
        1D array of azimuth angles (degrees).
    mic_pairs : list of (int, int)
        Microphone index pairs used for GCC-PHAT accumulation.
    """

    def __init__(self, tdoa_lut: TDOALUT):
        self.tdoa_lut = tdoa_lut
        self.azimuth_grid_deg = tdoa_lut.azimuth_grid_deg
        self.mic_pairs = tdoa_lut.mic_pairs

        logger.info(
            "SRPScanner initialized",
            extra={
                "num_angles": len(self.azimuth_grid_deg),
                "num_pairs": len(self.mic_pairs),
            },
        )

    # ------------------------------------------------------------------

    def compute_srp(
        self,
        gcc_maps: Dict[Tuple[int, int], np.ndarray],
        pair_weights: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> np.ndarray:
        """
        Compute SRP-PHAT steered response power P(theta) over azimuth.

        Parameters
        ----------
        gcc_maps : dict
            Mapping (i, j) -> 1D GCC-PHAT array R_ij[t].
            Zero delay MUST be at index len(R_ij)//2.

        Returns
        -------
        np.ndarray
            SRP-PHAT spatial spectrum P(theta), shape (n_angles,).
        """
        # ---- Validate GCC maps ----
        for pair in self.mic_pairs:
            if pair not in gcc_maps:
                raise KeyError(f"Missing GCC map for mic pair {pair}.")

        first_pair = self.mic_pairs[0]
        R_first = np.asarray(gcc_maps[first_pair], dtype=np.float32)

        if R_first.ndim != 1:
            raise ValueError("Each GCC map must be a 1D array.")

        n_delays = R_first.shape[0]
        center_idx = n_delays // 2

        # Clean invalid values in GCC (rare but possible in silent/noisy frames)
        if not np.isfinite(R_first).all():
            logger.warning("Non-finite values detected in GCC; normalizing.")
            for pair in self.mic_pairs:
                gcc_maps[pair] = np.nan_to_num(
                    gcc_maps[pair], nan=0.0, posinf=0.0, neginf=0.0
                )

        n_angles = len(self.azimuth_grid_deg)
        P = np.zeros(n_angles, dtype=np.float32)

        # Get pair weights (default to 1.0 if not provided)
        if pair_weights is None:
            pair_weights = {pair: 1.0 for pair in self.mic_pairs}

        # ---- Main accumulation loop over microphone pairs ----
        for (i, j) in self.mic_pairs:
            R_ij = np.asarray(gcc_maps[(i, j)], dtype=np.float32)

            if R_ij.shape[0] != n_delays:
                raise ValueError(
                    f"GCC map for pair {(i, j)} has inconsistent length "
                    f"{R_ij.shape[0]} != {n_delays}"
                )

            # Get pair weight (default to 1.0 if not in dict)
            w_ij = pair_weights.get((i, j), 1.0)

            # TDOAs for all angles (samples, float)
            delays = self.tdoa_lut.get_delays(i, j).astype(np.float32)

            if delays.shape[0] != n_angles:
                raise ValueError(
                    f"TDOA array length mismatch for pair {(i, j)}: "
                    f"{delays.shape[0]} != {n_angles}"
                )

            # Compute GCC index positions
            positions = center_idx + delays

            # Optimized path if all delays ~ integer (integer delay system)
            # (not always the case, but cheap to check)
            if np.allclose(delays, np.round(delays), atol=1e-4):
                idx = positions.astype(np.int32)
                idx_clipped = np.clip(idx, 0, n_delays - 1)
                P += w_ij * R_ij[idx_clipped]
                continue

            # Fractional interpolation otherwise
            contrib = linear_interp_1d(R_ij, positions)
            P += w_ij * contrib.astype(np.float32)

        return P
