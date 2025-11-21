# src/my_doa/doa/tracker.py

"""
Multi-target DOA tracker using 1D Kalman filters on azimuth.

This is a simplified, azimuth-only analogue of ODAS's M3K-style tracker.
Each track models:
    state x = [theta_deg, theta_dot_deg_per_sec]^T

And is updated with DOA candidates from the peak extractor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from src.my_doa.utils.logger import get_logger
from src.my_doa.utils.math_utils import (
    wrap_angle_deg,
    wrap_angle_deg_0_360,
    circular_distance_deg,
)


logger = get_logger(__name__)


@dataclass
class TrackState:
    """
    Represents a single DOA track.

    Attributes
    ----------
    id : int
        Unique track identifier.
    theta_deg : float
        Current estimated azimuth in degrees (wrapped to [-180, 180)).
    theta_dot_deg_per_sec : float
        Estimated angular velocity (deg/s).
    P : np.ndarray
        2x2 state covariance matrix.
    age : int
        Number of frames since track creation.
    misses : int
        Number of consecutive frames without an associated detection.
    hits : int
        Number of frames where track received an associated detection.
    last_update_frame : int
        Frame index of last update (for debugging/analysis).
    low_confidence_frames : int
        Number of consecutive frames with confidence below threshold.
    """

    id: int
    theta_deg: float
    theta_dot_deg_per_sec: float
    P: np.ndarray
    age: int = 0
    misses: int = 0
    hits: int = 0
    last_update_frame: int = 0
    low_confidence_frames: int = 0

    def compute_confidence(self) -> float:
        """
        Compute track confidence based on age, hit rate, and recent activity.
        
        Confidence formula:
        - Hit rate: hits / max(age, 1) - tracks with more hits are more confident
        - Recent activity: heavily penalize tracks with recent misses
        - Age factor: newer tracks have lower confidence initially
        
        Returns
        -------
        float
            Confidence value in [0.0, 1.0], where 1.0 is highest confidence.
        """
        if self.age == 0:
            return 0.0
        
        # Hit rate: fraction of frames where track received a detection
        hit_rate = self.hits / float(self.age)
        
        # Recent activity: heavily penalize if track has many recent misses
        # More aggressive: if misses > 2, confidence drops quickly
        # This helps remove false tracks that are consistently missing detections
        if self.misses <= 2:
            recent_activity = 1.0
        elif self.misses <= 5:
            recent_activity = 0.5  # Moderate penalty
        else:
            recent_activity = 0.1  # Heavy penalty for many misses
        
        # Age factor: tracks need time to establish confidence
        # Gradually increase confidence as track ages (up to 10 frames)
        age_factor = min(self.age / 10.0, 1.0)
        
        # Combine factors
        confidence = hit_rate * recent_activity * age_factor
        
        # Clamp to [0, 1]
        return float(np.clip(confidence, 0.0, 1.0))

    def as_dict(self) -> Dict:
        # Convert to 0-360 range for output (mics are at 45°, 135°, 225°, 315°)
        theta_deg_0_360 = wrap_angle_deg_0_360(self.theta_deg)
        return {
            "id": self.id,
            "theta_deg": theta_deg_0_360,
            "theta_dot_deg_per_sec": self.theta_dot_deg_per_sec,
            "age": self.age,
            "misses": self.misses,
            "hits": self.hits,
            "confidence": self.compute_confidence(),
        }


@dataclass
class TrackerConfig:
    """
    Configuration for the multi-target tracker.

    Parameters
    ----------
    dt : float
        Time step between frames (seconds).
    process_noise : float
        Process noise std-dev (deg/s^2) controlling how quickly
        the filter allows state to change.
    measurement_noise : float
        Measurement noise std-dev in degrees.
    gate_deg : float
        Gating threshold in degrees; detections farther than this
        from predicted track angle are ignored for that track.
    birth_frames : int
        Number of consecutive frames a candidate must be detected to
        spawn a new track.
    death_frames : int
        Number of consecutive misses before a track is removed.
    pending_track_power_threshold : float
        Minimum SRP power required to create a new pending track.
        Detections below this threshold are ignored for track birth.
        Should be <= min_power from SSL config (typically 0.03-0.05).
    pending_track_max_age : int
        Maximum age (in frames) for pending tracks before they are removed.
        Pending tracks that don't reach birth_frames within this time are discarded.
        Should be >= birth_frames * 2 (typically 6-10).
    """

    dt: float
    process_noise: float = 5.0
    measurement_noise: float = 5.0
    gate_deg: float = 20.0
    birth_frames: int = 3
    death_frames: int = 10
    pending_track_power_threshold: float = 0.03
    pending_track_max_age: int = 8
    min_confidence_for_promotion: float = 0.20
    min_hit_rate_for_promotion: float = 0.4
    min_confidence_to_keep: float = 0.10
    low_confidence_frames_before_removal: int = 6


@dataclass
class PendingTrack:
    """
    Candidate track that is not yet promoted to a full TrackState.
    Used for enforcing birth_frames before creating a real track.
    """

    theta_deg: float
    power: float
    age: int = 1  # how many consecutive frames we've seen it
    hits: int = 1  # number of frames where this pending track was matched
    misses: int = 0  # number of consecutive frames without a match
    
    def compute_confidence(self) -> float:
        """
        Compute confidence for pending track (similar to TrackState).
        Used to determine if track should be promoted.
        """
        if self.age == 0:
            return 0.0
        
        hit_rate = self.hits / float(self.age)
        recent_activity = 1.0 if self.misses <= 3 else max(0.0, 1.0 - (self.misses - 3) * 0.2)
        age_factor = min(self.age / 10.0, 1.0)
        confidence = hit_rate * recent_activity * age_factor
        return float(np.clip(confidence, 0.0, 1.0))


class MultiTargetTracker:
    """
    Multi-target DOA tracker using simple nearest-neighbor association
    and 2D Kalman filters for azimuth & angular velocity.

    Typical usage:
    --------------
        tracker = MultiTargetTracker(config)
        for frame_idx in range(...):
            detections = [(theta_deg, power), ...]
            tracks = tracker.step(detections, frame_idx)
    """

    def __init__(self, config: TrackerConfig):
        self.config = config

        # Precompute model matrices
        dt = config.dt
        self.F = np.array([[1.0, dt], [0.0, 1.0]], dtype=np.float32)
        self.H = np.array([[1.0, 0.0]], dtype=np.float32)  # measure only theta

        # Process noise (acceleration-like)
        # Here we approximate Q using process_noise on velocity
        q = (config.process_noise ** 2)
        self.Q = np.array(
            [
                [0.25 * dt * dt * q, 0.5 * dt * q],
                [0.5 * dt * q, q],
            ],
            dtype=np.float32,
        )

        r_var = config.measurement_noise ** 2
        self.R = np.array([[r_var]], dtype=np.float32)

        self.tracks: Dict[int, TrackState] = {}
        self.next_id: int = 1

        # Pending tracks before birth_frames threshold
        self.pending: List[PendingTrack] = []

        logger.info(
            "MultiTargetTracker initialized",
            extra={
                "dt": config.dt,
                "process_noise": config.process_noise,
                "measurement_noise": config.measurement_noise,
                "gate_deg": config.gate_deg,
                "birth_frames": config.birth_frames,
                "death_frames": config.death_frames,
                "pending_track_power_threshold": config.pending_track_power_threshold,
                "pending_track_max_age": config.pending_track_max_age,
                "min_confidence_for_promotion": config.min_confidence_for_promotion,
                "min_hit_rate_for_promotion": config.min_hit_rate_for_promotion,
                "min_confidence_to_keep": config.min_confidence_to_keep,
                "low_confidence_frames_before_removal": config.low_confidence_frames_before_removal,
            },
        )

    # ---------- Public API ----------

    def step(
        self,
        detections: List[tuple[float, float]],
        frame_idx: int,
    ) -> List[TrackState]:
        """
        Advance tracker by one frame.

        Parameters
        ----------
        detections : list of (theta_deg, power)
            DOA detections from peak extractor.
        frame_idx : int
            Current frame index (monotonic).

        Returns
        -------
        List[TrackState]
            List of active tracks after update.
        """
        # 1) Predict all tracks one step forward
        self._predict_all()

        # 2) Associate detections to tracks
        assignments, unassigned_dets = self._associate_detections(detections)

        # 3) Update tracks with assigned detections
        self._update_assigned(assignments, detections, frame_idx)

        # 4) Handle unassigned detections (birth logic)
        self._update_pending(unassigned_dets, detections)

        # 5) Age + miss logic, prune dead tracks
        self._age_and_prune()

        # Return a snapshot list (copy) of current tracks
        return list(self.tracks.values())

    # ---------- Kalman core ----------

    def _predict_all(self) -> None:
        """
        Kalman prediction for all existing tracks.
        """
        for track in self.tracks.values():
            x = np.array(
                [track.theta_deg, track.theta_dot_deg_per_sec], dtype=np.float32
            )

            # Prediction
            x_pred = self.F @ x
            P_pred = self.F @ track.P @ self.F.T + self.Q

            # Wrap angle
            x_pred[0] = wrap_angle_deg(float(x_pred[0]))

            track.theta_deg = float(x_pred[0])
            track.theta_dot_deg_per_sec = float(x_pred[1])
            track.P = P_pred

    def _kalman_update(
        self, track: TrackState, theta_meas_deg: float
    ) -> None:
        """
        Kalman update for a single track with one measurement.
        """
        # State vector
        x = np.array(
            [track.theta_deg, track.theta_dot_deg_per_sec], dtype=np.float32
        )
        P = track.P

        # Measurement
        z = np.array([[theta_meas_deg]], dtype=np.float32)

        # Innovation: wrap angular difference
        z_pred = self.H @ x  # shape (1,)
        y = float(z[0, 0] - z_pred[0])  # scalar
        y = circular_distance_deg(0.0, y)  # smallest signed angle

        # Innovation covariance
        S = self.H @ P @ self.H.T + self.R  # (1,1)
        # Note: S is always positive (R > 0), so inverse is safe
        # For 1x1 matrix, direct division is more efficient but np.linalg.inv works fine
        K = P @ self.H.T @ np.linalg.inv(S)  # (2,1)

        # Update state
        x_new = x + (K * y).reshape(-1)
        x_new[0] = wrap_angle_deg(float(x_new[0]))
        P_new = (np.eye(2, dtype=np.float32) - K @ self.H) @ P

        track.theta_deg = float(x_new[0])
        track.theta_dot_deg_per_sec = float(x_new[1])
        track.P = P_new

    # ---------- Association ----------

    def _associate_detections(
        self, detections: List[tuple[float, float]]
    ) -> tuple[Dict[int, int], List[int]]:
        """
        Associate detections to tracks via nearest-neighbor with gating.

        Returns
        -------
        assignments : dict
            Mapping track_id -> det_index.
        unassigned_dets : list of int
            List of detection indices that were not assigned to any track.
        """
        if not self.tracks or not detections:
            # No tracks or no detections: nothing to assign
            return {}, list(range(len(detections)))

        det_used = [False] * len(detections)
        assignments: Dict[int, int] = {}

        for track_id, track in self.tracks.items():
            best_det_idx: Optional[int] = None
            best_dist = float("inf")

            for det_idx, (theta_deg, power) in enumerate(detections):
                if det_used[det_idx]:
                    continue

                dist = abs(
                    circular_distance_deg(track.theta_deg, theta_deg)
                )

                if dist < best_dist:
                    best_dist = dist
                    best_det_idx = det_idx

            # Apply gate
            if best_det_idx is not None and best_dist <= self.config.gate_deg:
                assignments[track_id] = best_det_idx
                det_used[best_det_idx] = True

        unassigned_dets = [i for i, used in enumerate(det_used) if not used]
        return assignments, unassigned_dets

    # ---------- Updating + track mgmt ----------

    def _update_assigned(
        self,
        assignments: Dict[int, int],
        detections: List[tuple[float, float]],
        frame_idx: int,
    ) -> None:
        """
        Kalman-update tracks that got assigned detections.
        """
        for track_id, det_idx in assignments.items():
            if track_id not in self.tracks:
                continue  # safety; should not happen

            theta_deg, power = detections[det_idx]
            track = self.tracks[track_id]

            self._kalman_update(track, theta_deg)

            track.hits += 1
            track.misses = 0
            track.age += 1
            track.last_update_frame = frame_idx
            # Reset low confidence counter on successful update
            # (will be checked in _age_and_prune)

        # For tracks that didn't get an assignment, just increment age/misses
        for track_id, track in self.tracks.items():
            if track_id not in assignments:
                track.misses += 1
                track.age += 1

    def _update_pending(
        self,
        unassigned_dets: List[int],
        detections: List[tuple[float, float]],
    ) -> None:
        """
        Update pending track candidates (birth logic) with unassigned detections.
        
        Features:
        - Only creates pending tracks for detections above power threshold
        - Ages all pending tracks (matched and unmatched)
        - Removes pending tracks that are too old
        - Promotes pending tracks that reach birth_frames
        """
        # First, age all existing pending tracks (even if not matched this frame)
        for pend in self.pending:
            pend.age += 1
            pend.misses += 1  # Will be reset if matched below

        # Process unassigned detections
        new_pending: List[PendingTrack] = []

        for det_idx in unassigned_dets:
            theta_deg, power = detections[det_idx]

            # Power threshold check: only create pending tracks for high-power detections
            if power < self.config.pending_track_power_threshold:
                continue  # Skip low-power detections

            matched = False
            for pend in self.pending:
                dist = abs(circular_distance_deg(pend.theta_deg, theta_deg))
                if dist <= self.config.gate_deg:
                    # Update existing pending track with new detection
                    pend.theta_deg = theta_deg  # update to most recent
                    pend.power = max(pend.power, power)
                    pend.hits += 1
                    pend.misses = 0  # Reset misses on match
                    # Note: age was already incremented above
                    matched = True
                    break

            if not matched:
                # Check if this detection is too close to an existing active track
                # This prevents creating duplicate tracks for the same source
                too_close_to_existing = False
                for track in self.tracks.values():
                    dist = abs(circular_distance_deg(track.theta_deg, theta_deg))
                    if dist <= self.config.gate_deg * 1.5:  # Use 1.5x gate to be more conservative
                        too_close_to_existing = True
                        break
                
                if not too_close_to_existing:
                    # Create new pending track (age starts at 1, will be incremented next iteration)
                    new_pending.append(PendingTrack(theta_deg=theta_deg, power=power, age=1, hits=1, misses=0))

        # Merge new_pending with existing pending
        self.pending.extend(new_pending)

        # Process pending tracks: promote or remove
        survivors: List[PendingTrack] = []
        for pend in self.pending:
            if pend.age >= self.config.birth_frames:
                # Check confidence and hit rate before promoting
                confidence = pend.compute_confidence()
                hit_rate = pend.hits / float(pend.age) if pend.age > 0 else 0.0
                
                if (confidence >= self.config.min_confidence_for_promotion and 
                    hit_rate >= self.config.min_hit_rate_for_promotion):
                    # Promote to full track
                    self._create_track(pend.theta_deg)
                    logger.debug(
                        "Promoted pending track to full track",
                        extra={
                            "age": pend.age,
                            "theta_deg": pend.theta_deg,
                            "confidence": confidence,
                            "hit_rate": hit_rate,
                        },
                    )
                else:
                    # Not confident enough or hit rate too low, but keep trying if within age limit
                    if pend.age <= self.config.pending_track_max_age:
                        survivors.append(pend)
                    else:
                        logger.debug(
                            "Removing pending track: low confidence/hit rate and too old",
                            extra={
                                "age": pend.age,
                                "theta_deg": pend.theta_deg,
                                "confidence": confidence,
                                "hit_rate": hit_rate,
                            },
                        )
            elif pend.age > self.config.pending_track_max_age:
                # Remove: too old without reaching birth threshold
                logger.debug(
                    "Removing expired pending track",
                    extra={
                        "age": pend.age,
                        "theta_deg": pend.theta_deg,
                        "power": pend.power,
                    },
                )
            else:
                # Keep: still within age limit
                survivors.append(pend)
        
        self.pending = survivors

    def _create_track(self, theta_deg: float) -> None:
        """
        Create a new TrackState from an initial DOA estimate.
        """
        # Input is in 0-360 range, but tracker uses -180 to 180 internally
        # for circular distance calculations. Convert for internal use.
        theta_deg_wrapped = wrap_angle_deg(theta_deg)

        # Initial state: zero velocity
        x0 = np.array([theta_deg_wrapped, 0.0], dtype=np.float32)

        # Initial covariance: somewhat large uncertainty
        P0 = np.diag([self.config.measurement_noise ** 2, self.config.process_noise ** 2]).astype(
            np.float32
        )

        track = TrackState(
            id=self.next_id,
            theta_deg=float(x0[0]),
            theta_dot_deg_per_sec=float(x0[1]),
            P=P0,
            age=0,
            misses=0,
            hits=0,
            last_update_frame=0,
            low_confidence_frames=0,
        )

        self.tracks[self.next_id] = track
        logger.info(
            "Created new track",
            extra={"track_id": track.id, "theta_deg": track.theta_deg},
        )
        self.next_id += 1

    def _age_and_prune(self) -> None:
        """
        Remove tracks that have been missing for too many frames or have low confidence.
        
        More aggressive removal for tracks with poor recent performance.
        """
        to_delete = []
        for track_id, track in self.tracks.items():
            # Check for too many misses
            if track.misses > self.config.death_frames:
                to_delete.append(track_id)
                continue
            
            # More aggressive: remove tracks with many consecutive misses even if below death_frames
            # This helps remove false tracks faster
            if track.misses >= 10 and track.age > 15:
                # If track has 10+ misses and is old enough, remove it
                # (allows some tolerance for intermittent sources, but removes persistent false tracks)
                to_delete.append(track_id)
                logger.debug(
                    "Removing track: too many consecutive misses",
                    extra={
                        "track_id": track_id,
                        "misses": track.misses,
                        "age": track.age,
                    },
                )
                continue
            
            # Check confidence-based removal
            confidence = track.compute_confidence()
            if confidence < self.config.min_confidence_to_keep:
                track.low_confidence_frames += 1
                # More aggressive: remove faster if track has many misses
                removal_threshold = self.config.low_confidence_frames_before_removal
                if track.misses >= 5:
                    # If track has 5+ misses, remove after just 2 low-confidence frames
                    removal_threshold = 2
                
                if track.low_confidence_frames >= removal_threshold:
                    to_delete.append(track_id)
                    logger.debug(
                        "Removing track: low confidence",
                        extra={
                            "track_id": track_id,
                            "confidence": confidence,
                            "low_confidence_frames": track.low_confidence_frames,
                            "misses": track.misses,
                        },
                    )
            else:
                # Reset counter if confidence is good
                track.low_confidence_frames = 0

        for track_id in to_delete:
            logger.info("Removing dead track", extra={"track_id": track_id})
            del self.tracks[track_id]
