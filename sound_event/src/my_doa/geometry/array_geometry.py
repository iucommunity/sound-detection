# src/my_doa/geometry/array_geometry.py

"""
Microphone array geometry module.

Provides:
- Loading geometry from YAML
- Microphone pair generation
- Fast precomputed inter-mic distances/vectors
- Array diagnostics (aperture, spacing, aliasing check)
- TDOA bounds in seconds and samples
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import yaml

from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


class ArrayGeometry:
    """
    Represents the microphone array geometry.

    Attributes
    ----------
    mic_positions : np.ndarray (M, 3)
        XYZ positions in meters.
    fs : float
        Sampling rate (Hz).
    c : float
        Speed of sound (m/s).
    pairs : list[(i, j)]
        Microphone index pairs (GCC pairs).
    deltas : np.ndarray (num_pairs, 3)
        Vector differences r_i - r_j (meters).
    distances : np.ndarray (num_pairs,)
        Euclidean distances for each pair (meters).
    """

    # ------------------------------------------------------------------ #
    # Constructor
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        mic_positions: np.ndarray,
        fs: float,
        c: float = 343.0,
    ):
        mic_positions = np.asarray(mic_positions, dtype=np.float32)

        if mic_positions.ndim != 2 or mic_positions.shape[1] != 3:
            raise ValueError("mic_positions must be array of shape (M, 3).")

        self.mic_positions = mic_positions
        self.num_mics = mic_positions.shape[0]

        self.fs = float(fs)
        self.c = float(c)

        # Generate pairs
        self.pairs = self._generate_pairs()

        # Precompute deltas, distances
        self.deltas, self.distances = self._compute_pair_vectors()

        # Diagnostics + warnings
        self._run_diagnostics()

        logger.info(
            "ArrayGeometry initialized",
            extra={
                "num_mics": self.num_mics,
                "fs": self.fs,
                "c": self.c,
                "num_pairs": len(self.pairs),
            },
        )

    # ------------------------------------------------------------------ #
    # YAML loader
    # ------------------------------------------------------------------ #
    @classmethod
    def from_yaml(cls, path: str | Path, fs: float) -> "ArrayGeometry":
        """
        Load microphone geometry from YAML.

        YAML Example:
        -------------
        microphones:
          - id: 0
            position: [0.032, 0, 0]
          - id: 1
            position: [-0.032, 0, 0]
        speed_of_sound: 343.0
        """

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Geometry config not found: {path}")

        with open(path, "r") as f:
            config = yaml.safe_load(f)

        if "microphones" not in config:
            raise ValueError("YAML missing 'microphones' list.")

        positions = []
        ids_seen = set()

        for mic in config["microphones"]:
            if "id" not in mic or "position" not in mic:
                raise ValueError("Each microphone entry must have 'id' and 'position'.")

            mic_id = int(mic["id"])
            if mic_id in ids_seen:
                raise ValueError(f"Duplicate microphone id {mic_id}.")
            ids_seen.add(mic_id)

            pos = mic["position"]
            if len(pos) != 3:
                raise ValueError("Mic 'position' must be XYZ list of length 3.")
            positions.append((mic_id, pos))

        # Sort by id so index = id
        positions.sort(key=lambda x: x[0])
        pos_array = np.array([p[1] for p in positions], dtype=np.float32)

        c = float(config.get("speed_of_sound", 343.0))

        logger.info(
            "Loaded microphone geometry from YAML",
            extra={"path": str(path), "num_mics": len(positions), "c": c},
        )

        return cls(pos_array, fs=fs, c=c)

    # ------------------------------------------------------------------ #
    # Pair generation and precomputation
    # ------------------------------------------------------------------ #
    def _generate_pairs(self) -> List[Tuple[int, int]]:
        """Generate all (i < j) mic index pairs."""
        pairs: List[Tuple[int, int]] = []
        for i in range(self.num_mics):
            for j in range(i + 1, self.num_mics):
                pairs.append((i, j))

        logger.info(
            "Generated mic pairs",
            extra={"num_pairs": len(pairs), "pairs": pairs},
        )
        return pairs

    def _compute_pair_vectors(self):
        """
        Precompute vector differences (r_i - r_j) and distances.

        Returns
        -------
        deltas : (num_pairs, 3)
        distances : (num_pairs,)
        """
        deltas = []
        dists = []

        for (i, j) in self.pairs:
            d = self.mic_positions[i] - self.mic_positions[j]
            deltas.append(d)
            dists.append(np.linalg.norm(d))

        deltas = np.asarray(deltas, dtype=np.float32)
        dists = np.asarray(dists, dtype=np.float32)

        return deltas, dists

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #
    def _run_diagnostics(self) -> None:
        """Check common geometry mistakes and warn."""

        # Warn if array is not roughly planar (z dimension > few mm)
        z_vals = self.mic_positions[:, 2]
        if np.max(np.abs(z_vals)) > 0.005:
            logger.warning(
                "Microphone array is not planar in Z. Azimuth-only DOA may be biased.",
                extra={"max_abs_z": float(np.max(np.abs(z_vals)))},
            )

        # Warn if center of mass is too far from origin
        center = np.mean(self.mic_positions, axis=0)
        if np.linalg.norm(center) > 0.02:  # >2 cm
            logger.warning(
                "Microphone array center is offset from origin.",
                extra={"center_xyz_cm": (center * 100).tolist()},
            )

        # Aperture check
        aperture = float(np.max(self.distances))
        if aperture < 0.02:
            logger.warning(
                "Array aperture < 2 cm → resolution will be poor for DOA.",
                extra={"aperture_m": aperture},
            )

        # Spatial aliasing check
        # For 16 kHz, safe max spacing is ~4-5 cm (λ/2 at ~3.4 kHz)
        if aperture > 0.12:
            logger.warning(
                "Array aperture > 12 cm → spatial aliasing likely above ~1.4 kHz.",
                extra={"aperture_m": aperture},
            )

    # ------------------------------------------------------------------ #
    # Max TDOA calculations
    # ------------------------------------------------------------------ #
    def max_tdoa_seconds(self) -> float:
        """Maximum possible time delay among all microphone pairs."""
        return float(np.max(self.distances) / self.c)

    def max_tdoa_samples(self) -> int:
        """Maximum TDOA expressed in samples."""
        return int(math.ceil(self.max_tdoa_seconds() * self.fs))
