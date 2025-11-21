# src/my_doa/pipeline/doa_pipeline.py
"""
End-to-end DOA pipeline orchestration (production-ready).

This module integrates:
- Array geometry & TDOA LUT
- Streaming STFT front-end
- Optional MCRA noise estimation
- GCC-PHAT (with optional band-limited bins)
- SRP-PHAT azimuth scanning
- Peak extraction (multi-source)
- Multi-target Kalman tracking

This version is optimized for:
- Real-time constraints (embedded edge devices)
- ReSpeaker Mic Array v3.0 (but works with any geometry)
- 4-mic circular arrays
- Multi-target situations

Output per STFT frame:
    {
       "frame_index": int,
       "doa_candidates": [...],
       "tracks": [...],
       "P_theta": np.ndarray,
       "noise_spectrum": np.ndarray,
    }
    
Note: timestamp_sec is added by calling scripts (e.g., run_realtime.py)
since the pipeline only tracks relative frame indices.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from threading import Lock
import time

import numpy as np

from src.my_doa.geometry.array_geometry import ArrayGeometry
from src.my_doa.geometry.tdoa_lut import TDOALUT
from src.my_doa.dsp.stft import STFTProcessor
from src.my_doa.dsp.mcra import MCRA
from src.my_doa.dsp.gcc_phat import compute_gcc_phat_all
from src.my_doa.doa.srp_scan import SRPScanner
from src.my_doa.doa.peak_extractor import PeakExtractor, DOACandidate
from src.my_doa.doa.tracker import MultiTargetTracker, TrackerConfig, TrackState
from src.my_doa.utils.logger import get_logger
from src.my_doa.utils.math_utils import (
    wrap_angle_deg,
    wrap_angle_deg_0_360,
    circular_distance_deg,
)


logger = get_logger(__name__)


# ---------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------

@dataclass
class STFTConfig:
    frame_size: int
    hop_size: int
    window_type: str = "hann"
    fft_size: Optional[int] = None


@dataclass
class MCRAConfig:
    alpha_s: float = 0.85
    minima_window: int = 15
    delta: float = 1.5
    alpha_d: float = 0.1
    epsilon: float = 1e-8


@dataclass
class SSLConfig:
    azimuth_res_deg: float = 1.0        # grid resolution
    max_sources: int = 3
    min_power: float = 0.05
    suppression_deg: float = 25.0
    bandpass_low_hz: Optional[float] = 300.0
    bandpass_high_hz: Optional[float] = 4000.0

    # Orientation offset for physical mounting (e.g., array rotated on robot)
    orientation_offset_deg: float = 0.0

    # SNR-based masking of STFT bins before GCC-PHAT
    use_snr_mask: bool = True
    snr_mask_low_db: float = 0.0      # below this SNR (dB) → weight ~ 0
    snr_mask_high_db: float = 20.0    # above this SNR (dB) → weight ~ 1

    # Frequency weighting for GCC-PHAT
    use_freq_weighting: bool = True
    freq_weight_peak_hz: float = 1500.0  # Peak frequency for bell curve (Hz)
    freq_weight_width_hz: float = 2000.0  # Width of bell curve (Hz)

    # Pair weighting for SRP
    use_pair_weighting: bool = True

    # Temporal smoothing on P_theta
    use_temporal_smoothing: bool = True
    temporal_smoothing_alpha: float = 0.8  # EMA coefficient (0.7-0.9 recommended)

    # Tracking-based peak selection
    use_tracking_boost: bool = True
    tracking_boost_lambda: float = 0.3  # Boost strength (0.0 = no boost, 1.0 = strong)
    tracking_boost_sigma_deg: float = 15.0  # Gaussian width for boost (degrees)



@dataclass
class DOAPipelineConfig:
    geometry_path: str | Path
    sample_rate: int
    stft: STFTConfig
    mcra: MCRAConfig
    ssl: SSLConfig
    tracker: TrackerConfig


# ---------------------------------------------------------------------
# DOA Pipeline
# ---------------------------------------------------------------------

class DOAPipeline:
    """
    Real-time multichannel DOA pipeline.
    """

    def __init__(self, config: DOAPipelineConfig):
        self.config = config
        fs = config.sample_rate

        # ---------------------------------------------------------
        # 1) Microphone Array Geometry
        # ---------------------------------------------------------
        self.geometry = ArrayGeometry.from_yaml(config.geometry_path, fs=fs)

        # ---------------------------------------------------------
        # 2) Azimuth Grid (0-360 degrees for ReSpeaker mic positions)
        # ---------------------------------------------------------
        az_step = config.ssl.azimuth_res_deg
        # Use 0-360 range to match mic positions (45°, 135°, 225°, 315°)
        self.azimuth_grid_deg = np.arange(0.0, 360.0, az_step, dtype=np.float32)

        # ---------------------------------------------------------
        # 3) TDOA Lookup Table (fractional sample delays)
        # ---------------------------------------------------------
        self.tdoa_lut = TDOALUT(
            mic_positions=self.geometry.mic_positions,
            fs=fs,
            c=self.geometry.c,
            azimuth_grid_deg=self.azimuth_grid_deg,
            mic_pairs=self.geometry.pairs,
        )

        # ---------------------------------------------------------
        # 4) STFT Processor
        # ---------------------------------------------------------
        self.stft_proc = STFTProcessor(
            frame_size=config.stft.frame_size,
            hop_size=config.stft.hop_size,
            window_type=config.stft.window_type,
            fft_size=config.stft.fft_size,
        )

        self.fft_size = self.stft_proc.fft_size
        self.n_freq_bins = self.fft_size // 2 + 1

        # ---------------------------------------------------------
        # 5) Noise Estimator (MCRA)
        # ---------------------------------------------------------
        self.mcra = MCRA(
            n_freq=self.n_freq_bins,
            alpha_s=config.mcra.alpha_s,
            minima_window=config.mcra.minima_window,
            delta=config.mcra.delta,
            alpha_d=config.mcra.alpha_d,
            eps_floor=config.mcra.epsilon,
        )

        # ---------------------------------------------------------
        # 6) SRP Scanner
        # ---------------------------------------------------------
        self.srp_scanner = SRPScanner(self.tdoa_lut)

        # ---------------------------------------------------------
        # 7) Peak Extractor
        # ---------------------------------------------------------
        self.peak_extractor = PeakExtractor(
            azimuth_grid_deg=self.azimuth_grid_deg,
            max_sources=config.ssl.max_sources,
            min_power=config.ssl.min_power,
            suppression_deg=config.ssl.suppression_deg,
        )

        # ---------------------------------------------------------
        # 8) Multi-Target Tracker
        # ---------------------------------------------------------
        self.tracker = MultiTargetTracker(config.tracker)

        # ---------------------------------------------------------
        # 9) GCC bandpass bin mapping
        # ---------------------------------------------------------
        self.band_bins = self._compute_band_bins(
            fs=fs,
            fft_size=self.fft_size,
            low_hz=config.ssl.bandpass_low_hz,
            high_hz=config.ssl.bandpass_high_hz,
        )

        # Frame counter
        self.frame_index = 0

        # Temporal smoothing state
        self.P_smooth = None  # Will be initialized on first frame

        # Per-mic noise estimates for pair weighting
        self.mic_noise_estimates = None  # Will be initialized per mic

        # Pair reliability tracking (for pair weighting)
        self.pair_reliability = {pair: 1.0 for pair in self.geometry.pairs}

        # Snapshot mechanism for UI synchronization
        self._snapshot_lock = Lock()
        self._latest_snapshot: Optional[Dict[str, Any]] = None
        self._snapshot_frame_index = -1

        logger.info(
            "DOAPipeline initialized",
            extra={
                "fs": fs,
                "frame_size": config.stft.frame_size,
                "hop_size": config.stft.hop_size,
                "fft_size": self.fft_size,
                "az_res_deg": az_step,
                "n_angles": len(self.azimuth_grid_deg),
                "use_freq_weighting": config.ssl.use_freq_weighting,
                "use_pair_weighting": config.ssl.use_pair_weighting,
                "use_temporal_smoothing": config.ssl.use_temporal_smoothing,
                "use_tracking_boost": config.ssl.use_tracking_boost,
            },
        )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all internal state."""
        self.stft_proc.reset()
        self.mcra.reset()
        self.tracker.tracks.clear()
        self.tracker.pending.clear()
        self.tracker.next_id = 1
        self.frame_index = 0
        self.P_smooth = None
        self.mic_noise_estimates = None
        self.pair_reliability = {pair: 1.0 for pair in self.geometry.pairs}
        
        with self._snapshot_lock:
            self._latest_snapshot = None
            self._snapshot_frame_index = -1

        logger.info("DOAPipeline state reset")

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Thread-safe method to get the latest DOA snapshot.
        
        Returns None if no snapshot is available yet.
        This ensures UI always reads fully processed, consistent data.
        """
        with self._snapshot_lock:
            if self._latest_snapshot is None:
                return None
            # Return a copy to avoid race conditions
            return {
                "frame_index": self._latest_snapshot["frame_index"],
                "tracks": list(self._latest_snapshot["tracks"]),  # Copy list
                "timestamp_sec": self._latest_snapshot["timestamp_sec"],
                "P_theta": self._latest_snapshot["P_theta"].copy() if self._latest_snapshot["P_theta"] is not None else None,
            }

    def process_block(self, block: np.ndarray) -> List[Dict[str, Any]]:
        """
        Process a multichannel audio block: (n_mics, n_samples)

        Returns list of per-frame results produced by STFT.
        """
        stft_frames = self.stft_proc.process_block(block)
        results = []

        for X in stft_frames:
            out = self._process_stft_frame(X)
            results.append(out)
            self.frame_index += 1

        return results

    # ------------------------------------------------------------------
    # Internal per-STFT pipeline
    # ------------------------------------------------------------------

    def _process_stft_frame(self, X: np.ndarray) -> Dict[str, Any]:
        """
        Process a single STFT frame X(m, k) through MCRA, GCC, SRP, peaks, tracker.
        Now includes: frequency weighting, pair weighting, temporal smoothing, tracking boost.
        """
        # Sanity
        if X.ndim != 2:
            raise ValueError("STFT frame X must have shape (n_mics, n_freq_bins).")

        n_mics, n_freq = X.shape
        if n_freq != self.n_freq_bins:
            raise ValueError(
                f"STFT frame has n_freq={n_freq}, expected {self.n_freq_bins}."
            )

        # 1) Noise estimation (power averaged over mics)
        power_spectrum = np.mean(np.abs(X) ** 2, axis=0)
        N_hat = self.mcra.update(power_spectrum)

        # Per-mic noise estimates (only if pair weighting is enabled)
        mic_noise = None
        if self.config.ssl.use_pair_weighting:
            if self.mic_noise_estimates is None:
                # Initialize per-mic MCRA estimators
                from src.my_doa.dsp.mcra import MCRA
                self.mic_noise_estimates = [
                    MCRA(
                        n_freq=self.n_freq_bins,
                        alpha_s=self.config.mcra.alpha_s,
                        minima_window=self.config.mcra.minima_window,
                        delta=self.config.mcra.delta,
                        alpha_d=self.config.mcra.alpha_d,
                        eps_floor=self.config.mcra.epsilon,
                    )
                    for _ in range(n_mics)
                ]
            
            # Update per-mic noise estimates
            mic_noise = []
            for m in range(n_mics):
                mic_power = np.abs(X[m]) ** 2
                N_m = self.mic_noise_estimates[m].update(mic_power)
                mic_noise.append(N_m)

        # 2) Optional SNR-based masking before GCC-PHAT (original behavior)
        if self.config.ssl.use_snr_mask:
            eps = 1e-8
            snr = power_spectrum / (N_hat + eps)
            snr_db = 10.0 * np.log10(snr + eps)

            low_db = self.config.ssl.snr_mask_low_db
            high_db = self.config.ssl.snr_mask_high_db
            if high_db <= low_db:
                high_db = low_db + 1.0  # avoid division by zero

            # Map [low_db, high_db] → [0, 1]
            w = (snr_db - low_db) / (high_db - low_db)
            w = np.clip(w, 0.0, 1.0).astype(np.float32)

            # Apply as per-frequency weight to all microphones (original behavior)
            X = X * w[None, :]

        # 2b) Compute frequency weights for GCC-PHAT (additional weighting)
        freq_weights = None
        if self.config.ssl.use_freq_weighting:
            eps = 1e-8
            w_freq = np.ones(n_freq, dtype=np.float32)
            
            # Create bell curve centered at peak_hz
            fs = self.config.sample_rate
            freqs_hz = np.arange(n_freq) * fs / self.fft_size
            peak_hz = self.config.ssl.freq_weight_peak_hz
            width_hz = self.config.ssl.freq_weight_width_hz
            
            # Gaussian-like bell curve
            if width_hz > 0:
                w_freq = np.exp(-0.5 * ((freqs_hz - peak_hz) / (width_hz / 2.355)) ** 2)
                w_freq = w_freq.astype(np.float32)
                # Normalize so max weight is 1.0 (preserve overall power scale)
                max_w = np.max(w_freq)
                if max_w > eps:
                    w_freq = w_freq / max_w
            
            # Apply bandpass hard cut
            if self.band_bins is not None:
                k_min, k_max = self.band_bins
                mask = np.zeros_like(w_freq, dtype=bool)
                mask[k_min:k_max] = True
                w_freq = np.where(mask, w_freq, 0.0)

            freq_weights = w_freq.astype(np.float32)

        # 3) GCC-PHAT for all pairs (with frequency weighting)
        gcc_maps = compute_gcc_phat_all(
            X=X,
            mic_pairs=self.geometry.pairs,
            band_bins=self.band_bins,
            freq_weights=freq_weights,
        )

        # 4) Compute pair weights (confidence-aware)
        pair_weights = None
        if self.config.ssl.use_pair_weighting and mic_noise is not None:
            pair_weights = {}
            eps = 1e-8
            
            for (i, j) in self.geometry.pairs:
                # Pair SNR: inverse of combined noise power
                N_i_avg = np.mean(mic_noise[i])
                N_j_avg = np.mean(mic_noise[j])
                snr_ij = 1.0 / (N_i_avg + N_j_avg + eps)
                
                # Combine with reliability (could be enhanced with variance tracking)
                w_ij_raw = snr_ij * self.pair_reliability[(i, j)]
                pair_weights[(i, j)] = w_ij_raw
            
            # Normalize pair weights
            total_weight = sum(pair_weights.values())
            if total_weight > eps:
                for pair in pair_weights:
                    pair_weights[pair] /= total_weight

        # 5) SRP-PHAT scan over azimuth grid (with pair weights)
        P_raw = self.srp_scanner.compute_srp(gcc_maps, pair_weights=pair_weights)

        # 6) Temporal smoothing on P_theta
        if self.config.ssl.use_temporal_smoothing:
            if self.P_smooth is None:
                # Initialize with current P_raw (no smoothing on first frame)
                self.P_smooth = P_raw.copy()
            else:
                alpha = self.config.ssl.temporal_smoothing_alpha
                # EMA: P_smooth = α * P_smooth + (1-α) * P_raw
                # But ensure we don't suppress new strong peaks too much
                self.P_smooth = alpha * self.P_smooth + (1.0 - alpha) * P_raw
            P_theta = self.P_smooth
        else:
            P_theta = P_raw

        # 7) Tracking-based peak boost
        if self.config.ssl.use_tracking_boost and len(self.tracker.tracks) > 0:
            P_boost = self._compute_tracking_boost(P_theta)
        else:
            P_boost = P_theta

        # 8) Peak extraction: DOA candidates (on boosted P_theta)
        candidates: List[DOACandidate] = self.peak_extractor.extract(P_boost)
        
        # Debug: log max P_theta and candidate count
        if len(candidates) == 0 and self.frame_index % 100 == 0:
            max_p = float(np.max(P_boost)) if P_boost is not None else 0.0
            logger.debug(
                "No candidates extracted",
                extra={
                    "frame": self.frame_index,
                    "max_P_theta": max_p,
                    "min_power_threshold": self.config.ssl.min_power,
                },
            )

        # 9) Track-aware candidate merging
        candidates = self._merge_candidates_near_tracks(candidates)

        # 10) Tracker step with orientation offset
        # Tracker uses -180 to 180 internally, but we convert outputs to 0-360
        offset = self.config.ssl.orientation_offset_deg
        detections = [
            (wrap_angle_deg(cand.azimuth_deg + offset), cand.power)
            for cand in candidates
        ]

        tracks: List[TrackState] = self.tracker.step(
            detections=detections,
            frame_idx=self.frame_index,
        )

        # Prepare result
        result: Dict[str, Any] = {
            "frame_index": self.frame_index,
            "doa_candidates": candidates,
            "tracks": tracks,
            "P_theta": P_theta,
            "P_raw": P_raw,
            "noise_spectrum": N_hat,
        }

        # Update snapshot atomically (for UI thread-safe access)
        snapshot = {
            "frame_index": self.frame_index,
            "tracks": tracks,  # List of TrackState objects
            "timestamp_sec": time.time(),
            "P_theta": P_theta.copy() if P_theta is not None else None,
        }
        
        with self._snapshot_lock:
            self._latest_snapshot = snapshot
            self._snapshot_frame_index = self.frame_index

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_band_bins(
        fs: float,
        fft_size: int,
        low_hz: Optional[float],
        high_hz: Optional[float],
    ) -> Optional[Tuple[int, int]]:
        """Convert bandpass Hz → STFT bin indices."""
        if low_hz is None or high_hz is None:
            return None

        # Bound
        low_hz = max(0.0, float(low_hz))
        high_hz = min(float(high_hz), fs / 2)

        if high_hz <= low_hz:
            return None

        k_min = int(np.floor(low_hz * fft_size / fs))
        k_max = int(np.ceil(high_hz * fft_size / fs))

        k_min = max(0, k_min)
        k_max = min(fft_size // 2 + 1, k_max)

        if k_min >= k_max:
            logger.warning(
                "Invalid bandpass mapping: produces empty bin range",
                extra={"low_hz": low_hz, "high_hz": high_hz},
            )
            return None

        logger.info(
            "Computed band_bins",
            extra={"k_min": k_min, "k_max": k_max, "low_hz": low_hz, "high_hz": high_hz},
        )

        return (k_min, k_max)

    def _compute_tracking_boost(self, P_theta: np.ndarray) -> np.ndarray:
        """
        Compute boost map B(θ) from existing tracks and apply to P_theta.
        
        For each track, create a Gaussian boost around its predicted position.
        """
        n_angles = len(P_theta)
        boost_map = np.ones(n_angles, dtype=np.float32)
        
        lambda_boost = self.config.ssl.tracking_boost_lambda
        sigma_deg = self.config.ssl.tracking_boost_sigma_deg
        
        if lambda_boost <= 0.0 or len(self.tracker.tracks) == 0:
            return P_theta
        
        # For each active track, add Gaussian boost
        for track in self.tracker.tracks.values():
            # Get predicted angle (convert from -180 to 180 to 0-360)
            theta_pred = wrap_angle_deg_0_360(track.theta_deg)
            
            # Compute angular distance from each grid angle
            for idx, theta_grid in enumerate(self.azimuth_grid_deg):
                delta_theta = abs(circular_distance_deg(theta_pred, theta_grid))
                
                # Gaussian boost: exp(-0.5 * (delta / sigma)^2)
                g = np.exp(-0.5 * (delta_theta / sigma_deg) ** 2)
                boost_map[idx] += lambda_boost * g
        
        # Apply boost to P_theta
        P_boost = P_theta * boost_map
        return P_boost.astype(np.float32)

    def _merge_candidates_near_tracks(
        self, candidates: List[DOACandidate]
    ) -> List[DOACandidate]:
        """
        Merge candidates that are near existing tracks using circular mean.
        Also filter out weak candidates that are far from tracks.
        """
        if len(candidates) == 0 or len(self.tracker.tracks) == 0:
            return candidates
        
        # Group candidates by nearest track
        track_groups: Dict[int, List[DOACandidate]] = {}
        unassigned: List[DOACandidate] = []
        
        gate_deg = self.config.tracker.gate_deg
        
        for cand in candidates:
            # Find nearest track
            min_dist = float('inf')
            nearest_track_id = None
            
            for track_id, track in self.tracker.tracks.items():
                theta_track = wrap_angle_deg_0_360(track.theta_deg)
                dist = abs(circular_distance_deg(cand.azimuth_deg, theta_track))
                
                if dist < min_dist:
                    min_dist = dist
                    nearest_track_id = track_id
            
            # Assign to track if within gate
            if nearest_track_id is not None and min_dist <= gate_deg:
                if nearest_track_id not in track_groups:
                    track_groups[nearest_track_id] = []
                track_groups[nearest_track_id].append(cand)
            else:
                # Unassigned - require higher power threshold
                # (This is handled by min_power in peak extractor, but we can be more strict)
                unassigned.append(cand)
        
        # Merge candidates within each track group using circular mean
        merged: List[DOACandidate] = []
        
        for track_id, group in track_groups.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                # Circular mean of angles
                angles_rad = np.deg2rad([c.azimuth_deg for c in group])
                mean_sin = np.mean(np.sin(angles_rad))
                mean_cos = np.mean(np.cos(angles_rad))
                mean_angle_rad = np.arctan2(mean_sin, mean_cos)
                mean_angle_deg = np.rad2deg(mean_angle_rad)
                mean_angle_deg = wrap_angle_deg_0_360(mean_angle_deg)
                
                # Sum of powers
                total_power = sum(c.power for c in group)
                
                # Use index from strongest candidate
                strongest = max(group, key=lambda c: c.power)
                
                merged.append(
                    DOACandidate(
                        azimuth_deg=mean_angle_deg,
                        power=total_power,
                        index=strongest.index,
                    )
                )
        
        # Add unassigned candidates (they passed the peak extractor threshold)
        merged.extend(unassigned)
        
        return merged
