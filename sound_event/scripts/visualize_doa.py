#!/usr/bin/env python3
# scripts/visualize_doa.py

"""
Real-time DOA track visualization.

This script:
    - Uses the full production pipeline (loaded via config_loader)
    - Visualizes tracked sound sources on a polar plot with arrows from center
    - Shows only valid, stable tracks (filters out noise and false positives)
    - Displays track ID, azimuth, and confidence for each active track
    - Updates in real-time using matplotlib animation
    - Optionally applies pre-filter (filters.yaml)

Filtering:
    - Only shows tracks with confidence >= 30% (MIN_CONFIDENCE_TO_DISPLAY)
    - Only shows tracks that are at least 5 frames old (MIN_AGE_TO_DISPLAY)
    - This ensures only stable, reliable sound sources are displayed

Run:
    python scripts/visualize_doa.py
"""

from __future__ import annotations

import numpy as np
import yaml
import time
import threading
import queue
from typing import Dict
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.text import Text
from collections import deque
from dataclasses import dataclass, field

from pathlib import Path

from src.my_doa.utils.config_loader import load_pipeline_config
from src.my_doa.pipeline.doa_pipeline import DOAPipeline
from src.my_doa.audio.audio_io import AudioStream
from src.my_doa.utils.logger import get_logger
from src.my_doa.dsp.filters import design_highpass, design_bandpass, apply_filter
from src.my_doa.utils.math_utils import wrap_angle_deg_0_360, circular_distance_deg

logger = get_logger(__name__)


# ---------------------------------------------------------------------
# Load optional pre-filter
# ---------------------------------------------------------------------

def _load_filters(path: str | Path = "config/filters.yaml"):
    path = Path(path)
    if not path.exists():
        logger.info("No filters.yaml found; pre-filter disabled.")
        return None

    try:
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        logger.warning("Failed to load filters.yaml", extra={"error": str(e)})
        return None

    if not cfg.get("enable_pre_filter", False):
        logger.info("Pre-filter disabled via filters.yaml.")
        return None

    return cfg


# ---------------------------------------------------------------------
# Visualization configuration
# ---------------------------------------------------------------------

# Filtering thresholds for showing only valid tracks
MIN_CONFIDENCE_TO_DISPLAY = 0.25  # Only show tracks with confidence >= 25% (balanced)
MIN_AGE_TO_DISPLAY = 5  # Only show tracks that are at least 5 frames old (stable)
MAX_TIME_SINCE_UPDATE_MS = 500  # Drop tracks not updated within 500ms

# UI timing
UI_FPS = 20  # Fixed UI refresh rate (50ms per frame)
UI_SMOOTHING_FRAMES = 3  # Number of frames for UI-level smoothing
TRACK_HOLD_FRAMES = 3  # Keep disappearing tracks visible for 3 frames with fade

# Track state for UI smoothing and hold
@dataclass
class UITrackState:
    """UI-level track state with smoothing and hold logic."""
    track_id: int
    theta_deg: float
    confidence: float
    age: int
    last_update_frame: int
    hold_frames: int = 0  # Frames to keep visible after disappearing
    is_active: bool = True
    
    # Smoothing history
    theta_history: deque = field(default_factory=lambda: deque(maxlen=UI_SMOOTHING_FRAMES))
    confidence_history: deque = field(default_factory=lambda: deque(maxlen=UI_SMOOTHING_FRAMES))
    
    def __post_init__(self):
        if len(self.theta_history) == 0:
            self.theta_history.append(self.theta_deg)
        if len(self.confidence_history) == 0:
            self.confidence_history.append(self.confidence)

# Distinct colors for different track IDs (up to 20 tracks)
TRACK_COLORS = [
    '#1f77b4',  # blue
    '#ff7f0e',  # orange
    '#2ca02c',  # green
    '#d62728',  # red
    '#9467bd',  # purple
    '#8c564b',  # brown
    '#e377c2',  # pink
    '#7f7f7f',  # gray
    '#bcbd22',  # olive
    '#17becf',  # cyan
    '#aec7e8',  # light blue
    '#ffbb78',  # light orange
    '#98df8a',  # light green
    '#ff9896',  # light red
    '#c5b0d5',  # light purple
    '#c49c94',  # light brown
    '#f7b6d3',  # light pink
    '#c7c7c7',  # light gray
    '#dbdb8d',  # light olive
    '#9edae5',  # light cyan
]


def get_track_color(track_id: int) -> str:
    """Get a consistent color for a track ID."""
    return TRACK_COLORS[(track_id - 1) % len(TRACK_COLORS)]


def is_valid_track(track_dict: dict) -> bool:
    """
    Check if a track is valid enough to display.
    
    Filters out:
    - Low confidence tracks (noise, false positives)
    - Very new tracks (unstable, might be false)
    """
    confidence = track_dict.get("confidence", 0.0)
    age = track_dict.get("age", 0)
    
    return confidence >= MIN_CONFIDENCE_TO_DISPLAY and age >= MIN_AGE_TO_DISPLAY


def _compute_circular_mean(angles_deg: list) -> float:
    """Compute circular mean of angles in degrees."""
    angles_rad = np.deg2rad(angles_deg)
    mean_sin = np.mean(np.sin(angles_rad))
    mean_cos = np.mean(np.cos(angles_rad))
    mean_angle_rad = np.arctan2(mean_sin, mean_cos)
    return wrap_angle_deg_0_360(np.rad2deg(mean_angle_rad))


def _merge_close_tracks(track_data: list, merge_threshold_deg: float = 30.0) -> list:
    """
    Merge tracks that are visually close (within threshold degrees).
    Uses confidence-weighted circular mean for merged angle.
    More aggressive: merges all tracks within threshold, even if they're not directly adjacent.
    """
    if len(track_data) <= 1:
        return track_data
    
    # Sort by confidence (descending) so we process best tracks first
    sorted_tracks = sorted(track_data, key=lambda t: t["confidence"], reverse=True)
    
    merged = []
    used = [False] * len(sorted_tracks)
    
    for i, track in enumerate(sorted_tracks):
        if used[i]:
            continue
        
        # Find all tracks close to this one (including transitive closeness)
        # Start with this track
        close_tracks = [track]
        used[i] = True
        
        # Iteratively find all tracks close to any track in the group
        # This ensures transitive merging (if A is close to B and B is close to C, merge all)
        changed = True
        while changed:
            changed = False
            for j, other_track in enumerate(sorted_tracks):
                if used[j]:
                    continue
                
                # Check if this track is close to any track in the close_tracks group
                for close_track in close_tracks:
                    dist = abs(circular_distance_deg(close_track["theta_deg"], other_track["theta_deg"]))
                    if dist <= merge_threshold_deg:
                        close_tracks.append(other_track)
                        used[j] = True
                        changed = True
                        break
        
        # Merge all close tracks
        if len(close_tracks) == 1:
            merged.append(track)
        else:
            # Confidence-weighted circular mean of angles
            angles_rad = np.deg2rad([t["theta_deg"] for t in close_tracks])
            confidences = np.array([t["confidence"] for t in close_tracks])
            
            # Weight by confidence
            weights = confidences / (np.sum(confidences) + 1e-8)
            
            # Weighted circular mean
            mean_sin = np.sum(weights * np.sin(angles_rad))
            mean_cos = np.sum(weights * np.cos(angles_rad))
            mean_angle_rad = np.arctan2(mean_sin, mean_cos)
            mean_angle_deg = wrap_angle_deg_0_360(np.rad2deg(mean_angle_rad))
            
            # Use highest confidence track's ID and age, but weighted average confidence
            best_track = max(close_tracks, key=lambda t: t["confidence"])
            avg_confidence = np.mean(confidences)  # Average confidence of merged tracks
            
            merged.append({
                "id": best_track["id"],
                "theta_deg": mean_angle_deg,
                "confidence": avg_confidence,  # Average confidence
                "age": best_track["age"],
                "is_active": best_track.get("is_active", True),
            })
    
    return merged


# ---------------------------------------------------------------------
# Main visualization
# ---------------------------------------------------------------------

def main():
    print("\n=== Live DOA Track Visualization ===\n")

    # --------------------------------------------------------------
    # 1) Load pipeline configs
    # --------------------------------------------------------------
    pipe_cfg, audio_cfg = load_pipeline_config("config/pipeline.yaml")
    pipeline = DOAPipeline(pipe_cfg)

    device = audio_cfg.get("device", "ReSpeaker")
    fs = audio_cfg["sample_rate"]
    block_size = audio_cfg["block_size"]
    channels = audio_cfg["channels"]

    print(f"Audio device: {device}")
    print(f"Sample rate: {fs} Hz | block size: {block_size} | channels: {channels}")

    # --------------------------------------------------------------
    # 2) Pre-filter (optional)
    # --------------------------------------------------------------
    filt_cfg = _load_filters("config/filters.yaml")
    sos = None
    if filt_cfg is not None:
        try:
            if filt_cfg["type"] == "highpass":
                sos = design_highpass(
                    cutoff_hz=filt_cfg["highpass_cutoff_hz"],
                    fs=fs,
                    order=filt_cfg.get("order", 4),
                )
            elif filt_cfg["type"] == "bandpass":
                sos = design_bandpass(
                    low_hz=filt_cfg["bandpass_low_hz"],
                    high_hz=filt_cfg["bandpass_high_hz"],
                    fs=fs,
                    order=filt_cfg.get("order", 4),
                )

            print(f"Pre-filter enabled: {filt_cfg['type']}")
        except Exception as e:
            logger.warning("Failed to create pre-filter", extra={"error": str(e)})
            print("Pre-filter disabled.")
            sos = None

    # --------------------------------------------------------------
    # 3) Start audio
    # --------------------------------------------------------------
    channel_mapping = audio_cfg.get("channel_mapping", None)
    capture_channels = audio_cfg.get("capture_channels", None)
    
    stream = AudioStream(
        device=device,
        sample_rate=fs,
        block_size=block_size,
        channels=channels,
        channel_mapping=channel_mapping,
        capture_channels=capture_channels,
    )
    stream.start()

    print("\nPress Ctrl+C to stop.")
    print("Opening polar plot window...\n")

    # --------------------------------------------------------------
    # 4) Matplotlib setup
    # --------------------------------------------------------------
    plt.style.use("default")
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111, projection="polar")

    # Polar plot configuration
    ax.set_theta_zero_location("E")   # 0° = east (right)
    ax.set_theta_direction(1)         # counterclockwise
    ax.set_title("DOA Tracks (Live)", fontsize=16, pad=20)
    ax.set_ylim(0, 1.0)
    ax.set_rticks([0.25, 0.5, 0.75, 1.0])
    ax.set_rlabel_position(22.5)  # Move radial labels

    # Store plot elements for animation
    arrow_objects: list = []  # Store arrow annotations
    text_objects: list[Text] = []
    
    # UI state: track smoothing and hold
    ui_tracks: Dict[int, UITrackState] = {}  # track_id -> UITrackState
    current_frame = 0
    last_snapshot_frame = -1  # Track last snapshot frame to detect updates
    stop_dsp_thread = threading.Event()
    
    # --------------------------------------------------------------
    # 5) DSP processing thread (runs at audio block rate)
    # --------------------------------------------------------------
    def dsp_thread():
        """Separate thread for DSP processing to avoid blocking UI."""
        while not stop_dsp_thread.is_set():
            block = stream.read_block(timeout=0.1)
            if block is None:
                continue
            
            # Optional filtering
            if sos is not None:
                block = apply_filter(sos, block, mode="zero_phase")
            
            # Process block - snapshot is updated atomically inside
            try:
                pipeline.process_block(block)
            except Exception as e:
                logger.error("DSP processing error", extra={"error": str(e)})
    
    # Start DSP thread
    dsp_thread_obj = threading.Thread(target=dsp_thread, daemon=True)
    dsp_thread_obj.start()
    
    # --------------------------------------------------------------
    # 6) UI update function (runs at fixed FPS)
    # --------------------------------------------------------------
    def update(_):
        nonlocal arrow_objects, text_objects, ui_tracks, current_frame, last_snapshot_frame
        
        current_frame += 1
        
        # Get latest snapshot (thread-safe, may be slightly behind)
        # Force a fresh read each time
        snapshot = pipeline.get_latest_snapshot()
        if snapshot is None:
            # No snapshot yet - clear display
            for arrow_obj in arrow_objects:
                arrow_obj.remove()
            arrow_objects.clear()
            for text_obj in text_objects:
                text_obj.remove()
            text_objects.clear()
            if current_frame % 100 == 0:
                ax.set_title("DOA Tracks (Live) - Waiting for snapshot...", fontsize=16, pad=20)
            return []
        
        # Check if snapshot has actually changed
        snapshot_frame = snapshot["frame_index"]
        if snapshot_frame == last_snapshot_frame:
            # Snapshot hasn't changed, but still update UI (tracks might have aged/changed internally)
            # Don't return early - continue to update display
            pass
        else:
            last_snapshot_frame = snapshot_frame
        
        tracks = snapshot["tracks"]
        snapshot_time = snapshot["timestamp_sec"]
        current_time = time.time()
        
        # Debug: log track count occasionally
        if current_frame % 50 == 0:
            num_valid = sum(1 for t in tracks if is_valid_track(t.as_dict()))
            print(f"[UI Frame {current_frame}] Snapshot: {len(tracks)} tracks, {num_valid} valid")
            if len(tracks) > 0:
                for t in tracks:
                    td = t.as_dict()
                    print(f"  Track ID{t.id}: θ={td['theta_deg']:.1f}° age={t.age} conf={td['confidence']:.2f} valid={is_valid_track(td)}")
                logger.debug(
                    "Snapshot tracks",
                    extra={
                        "frame": current_frame,
                        "num_tracks": len(tracks),
                        "num_valid": num_valid,
                        "track_ids": [t.id for t in tracks],
                        "confidences": [t.compute_confidence() for t in tracks],
                        "ages": [t.age for t in tracks],
                    },
                )
            elif current_frame % 200 == 0:
                print(f"[UI Frame {current_frame}] No tracks in snapshot")
        
        # Update UI track states from snapshot
        # Only track IDs that are both in snapshot AND valid
        active_valid_track_ids = set()
        
        for track in tracks:
            track_dict = track.as_dict()
            track_id = track_dict["id"]
            
            # Filter: only process valid, stable tracks
            if not is_valid_track(track_dict):
                continue
            
            # Check time since snapshot was created (not track update time)
            # For real-time, snapshot should be recent; for offline, this check is less critical
            time_since_snapshot_ms = (current_time - snapshot_time) * 1000
            # Only reject if snapshot is very stale (likely DSP thread stuck)
            if time_since_snapshot_ms > MAX_TIME_SINCE_UPDATE_MS:
                # Don't reject tracks, just log warning (snapshot might be from offline processing)
                if current_frame % 100 == 0:  # Log occasionally
                    logger.debug(
                        "Snapshot is stale",
                        extra={
                            "time_since_snapshot_ms": time_since_snapshot_ms,
                            "frame": current_frame,
                        },
                    )
                # Continue anyway - tracks might still be valid
            
            # This track is valid - add to active set
            active_valid_track_ids.add(track_id)
            
            theta_deg = track_dict["theta_deg"]
            confidence = track_dict["confidence"]
            age = track_dict["age"]
            last_update_frame = track_dict.get("last_update_frame", current_frame)
            
            # Update or create UI track state
            if track_id in ui_tracks:
                ui_track = ui_tracks[track_id]
                ui_track.is_active = True
                ui_track.hold_frames = 0
                ui_track.theta_history.append(theta_deg)
                ui_track.confidence_history.append(confidence)
                ui_track.age = age
                ui_track.last_update_frame = last_update_frame
            else:
                ui_track = UITrackState(
                    track_id=track_id,
                    theta_deg=theta_deg,
                    confidence=confidence,
                    age=age,
                    last_update_frame=last_update_frame,
                )
                ui_tracks[track_id] = ui_track
        
        # Mark disappeared tracks and start hold timer
        # Only mark tracks as inactive if they're not in the active valid set
        for track_id, ui_track in list(ui_tracks.items()):
            if track_id not in active_valid_track_ids:
                if ui_track.is_active:
                    ui_track.is_active = False
                    ui_track.hold_frames = TRACK_HOLD_FRAMES
                else:
                    ui_track.hold_frames -= 1
                    if ui_track.hold_frames <= 0:
                        # Remove after hold period
                        del ui_tracks[track_id]
                        continue
        
        # Clear previous arrows and text
        for arrow_obj in arrow_objects:
            arrow_obj.remove()
        arrow_objects.clear()
        for text_obj in text_objects:
            text_obj.remove()
        text_objects.clear()
        
        if not ui_tracks:
            if current_frame % 100 == 0:
                print(f"[UI Frame {current_frame}] No UI tracks to display (had {len(tracks)} tracks from snapshot)")
            ax.set_title(f"DOA Tracks (Live) - No valid tracks (snapshot: {len(tracks)} tracks)", fontsize=16, pad=20)
            return []
        
        # Prepare track data with UI smoothing
        track_data = []
        for ui_track in ui_tracks.values():
            # Apply UI-level smoothing (circular mean for angles, EMA for confidence)
            if len(ui_track.theta_history) > 0:
                smoothed_theta = _compute_circular_mean(list(ui_track.theta_history))
            else:
                smoothed_theta = ui_track.theta_deg
            
            if len(ui_track.confidence_history) > 1:
                # EMA: 0.6 * new + 0.4 * previous average
                prev_mean = np.mean(list(ui_track.confidence_history)[:-1])
                smoothed_conf = 0.6 * ui_track.confidence_history[-1] + 0.4 * prev_mean
            elif len(ui_track.confidence_history) == 1:
                # Only one value, use it directly
                smoothed_conf = ui_track.confidence_history[0]
            else:
                smoothed_conf = ui_track.confidence
            
            # Apply fade for held tracks
            if not ui_track.is_active:
                fade_factor = ui_track.hold_frames / TRACK_HOLD_FRAMES
                smoothed_conf *= fade_factor * 0.5  # Fade to 50% opacity
            
            # Validate values before adding (prevent NaN)
            if np.isnan(smoothed_theta) or np.isnan(smoothed_conf) or np.isinf(smoothed_theta) or np.isinf(smoothed_conf):
                # Skip this track if it has invalid values
                continue
            
            # Clamp confidence to valid range
            smoothed_conf = np.clip(smoothed_conf, 0.0, 1.0)
            
            track_data.append({
                "id": ui_track.track_id,
                "theta_deg": smoothed_theta,
                "confidence": smoothed_conf,
                "age": ui_track.age,
                "is_active": ui_track.is_active,
            })
        
        # Merge visually close tracks (within 30 degrees) - balanced merging to eliminate duplicates
        # Do multiple passes to ensure all close tracks are merged
        if len(track_data) > 1:
            prev_len = len(track_data)
            track_data = _merge_close_tracks(track_data, merge_threshold_deg=30.0)
            # If merging reduced the count, do another pass to catch any remaining close tracks
            if len(track_data) < prev_len and len(track_data) > 1:
                track_data = _merge_close_tracks(track_data, merge_threshold_deg=30.0)

        if not track_data or len(track_data) == 0:
            ax.set_title("DOA Tracks (Live) - No valid tracks", fontsize=16, pad=20)
            return []

        # Convert to radians for polar plot and validate
        theta_rad = []
        radii = []
        colors = []
        valid_tracks = []
        
        min_radius = 0.4
        max_radius = 0.85
        
        for track in track_data:
            theta_deg = track["theta_deg"]
            confidence = track["confidence"]
            
            # Validate before converting
            if np.isnan(theta_deg) or np.isnan(confidence) or np.isinf(theta_deg) or np.isinf(confidence):
                continue
            
            theta_rad_val = np.deg2rad(theta_deg)
            radius_val = min_radius + (max_radius - min_radius) * confidence
            
            # Double-check after conversion
            if np.isnan(theta_rad_val) or np.isnan(radius_val):
                continue
            
            theta_rad.append(theta_rad_val)
            radii.append(radius_val)
            colors.append(get_track_color(track["id"]))
            valid_tracks.append(track)
        
        # Update track_data to only valid tracks
        track_data = valid_tracks
        
        # If no valid tracks after filtering, return early
        if not track_data or len(track_data) == 0:
            ax.set_title("DOA Tracks (Live) - No valid tracks", fontsize=16, pad=20)
            return []
        
        # Draw arrows from center (0, 0) to track positions
        for i, track in enumerate(track_data):
            theta_rad_i = theta_rad[i]
            radius_i = radii[i]
            color_i = colors[i]
            confidence_i = track["confidence"]
            
            # Arrow width proportional to confidence
            arrow_width = 2.0 + 3.0 * confidence_i
            
            # Alpha based on active state (fade for held tracks)
            alpha = 0.8 if track.get("is_active", True) else 0.4
            
            # Draw arrow from center to track position
            try:
                arrow_obj = ax.annotate(
                    '',
                    xy=(theta_rad_i, radius_i),  # Arrow tip position
                    xytext=(0, 0),  # Arrow start (center)
                    arrowprops=dict(
                        arrowstyle='->',
                        lw=arrow_width,
                        color=color_i,
                        alpha=alpha,
                        zorder=10,
                    ),
                )
                arrow_objects.append(arrow_obj)
            except Exception as e:
                # Skip if arrow creation fails
                logger.debug(f"Failed to create arrow: {e}")
                continue
            
            # Add marker at arrow tip (small circle)
            try:
                marker_obj = ax.scatter(
                    [theta_rad_i],  # Wrap in list to ensure it's an array
                    [radius_i],
                    s=[100 + 200 * confidence_i],  # Wrap in list
                    c=[color_i],
                    alpha=alpha * 0.9,
                    edgecolors='black',
                    linewidths=1.5,
                    zorder=11,
                )
                arrow_objects.append(marker_obj)
            except Exception as e:
                # Skip if marker creation fails
                logger.debug(f"Failed to create marker: {e}")
                continue

        # Add text labels near arrow tips
        label_offset_radius = 0.12  # Offset from arrow tip for text
        for i, track in enumerate(track_data):
            try:
                theta_rad_i = theta_rad[i]
                radius_i = radii[i]
                color_i = colors[i]
                
                # Validate coordinates
                if np.isnan(theta_rad_i) or np.isnan(radius_i):
                    continue
                
                # Position text slightly outside the arrow tip
                label_radius = min(0.95, radius_i + label_offset_radius)
                
                # Format label: "ID1: 154° (87%)"
                label = f"ID{track['id']}: {track['theta_deg']:.0f}° ({track['confidence']*100:.0f}%)"
                
                # Add text
                text_obj = ax.text(
                    theta_rad_i,
                    label_radius,
                    label,
                    fontsize=10,
                    ha='center',
                    va='bottom',
                    bbox=dict(
                        boxstyle='round,pad=0.4',
                        facecolor=color_i,
                        alpha=0.85,
                        edgecolor='black',
                        linewidth=1.0,
                    ),
                    zorder=12,
                    weight='bold',
                )
                text_objects.append(text_obj)
            except Exception as e:
                # Skip if text creation fails
                logger.debug(f"Failed to create text label: {e}")
                continue

        # Update title with valid track count
        ax.set_title(
            f"DOA Tracks (Live) - {len(track_data)} valid source(s)",
            fontsize=16,
            pad=20,
            weight='bold',
        )

        # Return all plot elements for animation
        # FuncAnimation will handle redrawing automatically
        return arrow_objects + text_objects

    # --------------------------------------------------------------
    # 7) Start animation (fixed frame rate)
    # --------------------------------------------------------------
    try:
        interval_ms = int(1000 / UI_FPS)  # Convert FPS to milliseconds
        ani = animation.FuncAnimation(
            fig,
            update,
            interval=interval_ms,  # Fixed frame rate (20 FPS = 50ms)
            blit=False,   # Don't use blit since we're removing/adding elements
        )
        plt.show()
    except KeyboardInterrupt:
        print("\nStopping visualization...")
    finally:
        stop_dsp_thread.set()
        stream.close()
        print("Audio stream closed.")


if __name__ == "__main__":
    main()

