# src/my_doa/pipeline/distance_estimation.py

from typing import Dict, List, Tuple
import numpy as np

# ----------------------------------------------------
# Class-level propagation parameters (YOU must tune)
# ----------------------------------------------------

CLASS_PARAMS: Dict[str, Dict[str, float]] = {
    # Example defaults – replace with real calibration
    "helicopter": {
        "L0_db": 110.0,      # SPL at reference distance r0 (dB)
        "sigma_L0_db": 5.0,  # not used directly yet
        "r0_m": 100.0,       # reference distance in meters
        "a_db_per_m": 0.002, # attenuation per meter
    },
    "tank": {
        "L0_db": 105.0,
        "sigma_L0_db": 5.0,
        "r0_m": 100.0,
        "a_db_per_m": 0.0015,
    },
    "vehicle": {
        "L0_db": 95.0,
        "sigma_L0_db": 5.0,
        "r0_m": 50.0,
        "a_db_per_m": 0.001,
    },
    "human": {
        "L0_db": 75.0,
        "sigma_L0_db": 6.0,
        "r0_m": 5.0,
        "a_db_per_m": 0.0005,
    },
    # add more classes / adjust names to match your USS output
}

# Global gain offset (set from calibration later)
CALIBRATION_OFFSET_DB: float = 0.0


# ----------------------------------------------------
# Propagation model inversion
# ----------------------------------------------------

def _estimate_distance_no_atten(
    L_meas_db: float,
    L0_db: float,
    r0_m: float,
) -> float:
    """
    L_meas ≈ L0 - 20 log10(r / r0)
    """
    delta = (L0_db - L_meas_db) / 20.0
    r = r0_m * (10.0 ** delta)
    return float(r)


def estimate_distance_with_atten(
    L_meas_db: float,
    L0_db: float,
    r0_m: float,
    a_db_per_m: float,
    r_min: float = 3.0,
    r_max: float = 5000.0,
    num_iter: int = 40,
) -> float:
    """
    Invert:

        L_meas ≈ L0 - 20 log10(r/r0) - a (r - r0)

    by bisection in [r_min, r_max].
    """

    def f(r: float) -> float:
        return (
            L0_db
            - 20.0 * np.log10(r / r0_m)
            - a_db_per_m * (r - r0_m)
            - L_meas_db
        )

    lo, hi = r_min, r_max
    f_lo, f_hi = f(lo), f(hi)

    if f_lo * f_hi > 0:
        # No sign change → fall back to no-atten model
        return _estimate_distance_no_atten(L_meas_db, L0_db, r0_m)

    for _ in range(num_iter):
        mid = 0.5 * (lo + hi)
        f_mid = f(mid)
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid

    return float(0.5 * (lo + hi))


# ----------------------------------------------------
# Core: per-class per-window distance
# ----------------------------------------------------

def estimate_distance_for_class_window(
    x_c_chunk: np.ndarray,
    fs: int,
    class_id: str,
    doas_deg: List[float],
    class_params: Dict[str, Dict[str, float]] = CLASS_PARAMS,
    calibration_offset_db: float = CALIBRATION_OFFSET_DB,
    r_min: float = 3.0,
    r_max: float = 5000.0,
    eps: float = 1e-12,
) -> Tuple[float, float]:
    """
    Estimate ONE distance for all same-class sources in this time window,
    using average per-source energy.

    Inputs:
        x_c_chunk: (M, N_chunk)      4-ch audio for this class in this window
        fs:        sample rate (Hz)  (not used, just for API symmetry)
        class_id:  "vehicle", "tank", "helicopter", "human", ...
        doas_deg:  list of DOA peaks (deg) for this class in this window

    Returns:
        L_per_src_db: SPL-like per-source level (dB)
        r_hat_m:      distance estimate (meters)
    """
    if class_id not in class_params:
        raise ValueError(f"No class_params defined for class_id={class_id}")

    params = class_params[class_id]
    L0_db = params["L0_db"]
    a_db_per_m = params["a_db_per_m"]
    r0_m = params["r0_m"]

    # Number of same-class sources in this window
    K = max(len(doas_deg), 1)  # avoid 0 → divide by zero

    # Total energy in this class chunk
    # x_c_chunk shape: (M, N_chunk)
    energy_total = float(np.sum(x_c_chunk ** 2))

    # Average per-source energy
    energy_per_src = energy_total / K

    # Convert to RMS per source
    M, N = x_c_chunk.shape
    rms_per_src = np.sqrt(energy_per_src / (M * N + eps))

    # SPL-like dB scale
    L_per_src_db = 20.0 * np.log10(rms_per_src + eps) + calibration_offset_db

    # Distance from propagation model
    r_hat = estimate_distance_with_atten(
        L_meas_db=L_per_src_db,
        L0_db=L0_db,
        r0_m=r0_m,
        a_db_per_m=a_db_per_m,
        r_min=r_min,
        r_max=r_max,
    )

    return float(L_per_src_db), float(r_hat)
