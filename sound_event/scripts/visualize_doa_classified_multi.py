#!/usr/bin/env python3
# scripts/visualize_doa_classified.py

"""
Real-time DOA track visualization with class labels.

This script:
    - Receives 4-channel audio segments (1.5s) with class labels from another project
    - Processes each classified audio segment through the DOA pipeline
    - Associates class labels with detected tracks
    - Visualizes tracked sound sources on a polar plot with arrows from center
    - Shows track ID, azimuth, confidence, and class label for each active track
    - Updates in real-time using matplotlib animation

Input format:
    - Audio: numpy array of shape (4, n_samples) - 4-channel audio, 1.5s length
    - Class label: string (e.g., "human", "tank", "vehicle", etc.)

Usage:
    # From another project, call:
    from scripts.visualize_doa_classified import ClassifiedDOAVisualizer
    
    visualizer = ClassifiedDOAVisualizer()
    visualizer.start()
    
    # Then push audio segments:
    audio_segment = np.array(...)  # shape: (4, n_samples), 1.5s at 16kHz = 24000 samples
    class_label = "human"
    visualizer.process_classified_audio(audio_segment, class_label)
"""

from __future__ import annotations

import numpy as np
import yaml
import time
import threading
import queue
from typing import Dict, Optional, Tuple
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.text import Text
from collections import deque
from dataclasses import dataclass, field

from pathlib import Path

from src.my_doa.utils.config_loader import load_pipeline_config
from src.my_doa.pipeline.doa_pipeline import DOAPipeline
from src.my_doa.utils.logger import get_logger
from src.my_doa.dsp.filters import design_highpass, design_bandpass, apply_filter
from src.my_doa.utils.math_utils import wrap_angle_deg_0_360, circular_distance_deg
from copy import deepcopy
logger = get_logger(__name__)


# ---------------------------------------------------------------------
# Visualization configuration
# ---------------------------------------------------------------------

# Filtering thresholds for showing only valid tracks
MIN_CONFIDENCE_TO_DISPLAY = 0.25  # Only show tracks with confidence >= 25%
MIN_AGE_TO_DISPLAY = 5  # Only show tracks that are at least 5 frames old
MAX_TIME_SINCE_UPDATE_MS = 500  # Drop tracks not updated within 500ms

# UI timing
UI_FPS = 20  # Fixed UI refresh rate (50ms per frame)
UI_SMOOTHING_FRAMES = 3  # Number of frames for UI-level smoothing
TRACK_HOLD_FRAMES = 3  # Keep disappearing tracks visible for 3 frames with fade


# ---------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------

@dataclass
class ClassifiedTrack:
    """Track with associated class label."""
    track_id: int
    theta_deg: float
    confidence: float
    age: int
    class_label: str
    last_update_frame: int
    hold_frames: int = 0
    is_active: bool = True
    
    # Smoothing history
    theta_history: deque = field(default_factory=lambda: deque(maxlen=UI_SMOOTHING_FRAMES))
    confidence_history: deque = field(default_factory=lambda: deque(maxlen=UI_SMOOTHING_FRAMES))
    
    def __post_init__(self):
        if len(self.theta_history) == 0:
            self.theta_history.append(self.theta_deg)
        if len(self.confidence_history) == 0:
            self.confidence_history.append(self.confidence)


# Fallback colors for unknown classes
FALLBACK_COLORS = [
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
]



# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------

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


def _merge_close_tracks(track_data: list, merge_threshold_deg: float = 40.0) -> list:
    """
    Merge tracks that are visually close (within threshold degrees).
    Merges tracks with the same class label only.
    Uses confidence-weighted circular mean for merged angle.
    """
    if len(track_data) <= 1:
        return track_data
    
    # Group by class label first
    by_class: Dict[str, list] = {}
    for track in track_data:
        class_label = track.get("class_label", "unknown")
        if class_label not in by_class:
            by_class[class_label] = []
        by_class[class_label].append(track)
    
    merged = []
    
    # Merge within each class
    for class_label, class_tracks in by_class.items():
        if len(class_tracks) <= 1:
            merged.extend(class_tracks)
            continue
        
        # Sort by confidence (descending)
        sorted_tracks = sorted(class_tracks, key=lambda t: t["confidence"], reverse=True)
        
        used = [False] * len(sorted_tracks)
        
        for i, track in enumerate(sorted_tracks):
            if used[i]:
                continue
            
            # Find all tracks close to this one (transitive)
            close_tracks = [track]
            used[i] = True
            
            changed = True
            while changed:
                changed = False
                for j, other_track in enumerate(sorted_tracks):
                    if used[j]:
                        continue
                    
                    for close_track in close_tracks:
                        dist = abs(circular_distance_deg(close_track["theta_deg"], other_track["theta_deg"]))
                        if dist <= merge_threshold_deg:
                            close_tracks.append(other_track)
                            used[j] = True
                            changed = True
                            break
            
            # Merge close tracks
            if len(close_tracks) == 1:
                merged.append(track)
            else:
                # Confidence-weighted circular mean
                angles_rad = np.deg2rad([t["theta_deg"] for t in close_tracks])
                confidences = np.array([t["confidence"] for t in close_tracks])
                
                weights = confidences / (np.sum(confidences) + 1e-8)
                mean_sin = np.sum(weights * np.sin(angles_rad))
                mean_cos = np.sum(weights * np.cos(angles_rad))
                mean_angle_rad = np.arctan2(mean_sin, mean_cos)
                mean_angle_deg = wrap_angle_deg_0_360(np.rad2deg(mean_angle_rad))
                
                best_track = max(close_tracks, key=lambda t: t["confidence"])
                avg_confidence = np.mean(confidences)
                
                merged.append({
                    "id": best_track["id"],
                    "theta_deg": mean_angle_deg,
                    "confidence": avg_confidence,
                    "age": best_track["age"],
                    "class_label": class_label,
                    "is_active": best_track.get("is_active", True),
                })
    
    return merged


# ---------------------------------------------------------------------
# Main visualization class
# ---------------------------------------------------------------------

class ClassifiedDOAVisualizer:
    """
    Real-time DOA visualization with class labels.
    
    Receives classified audio segments from another project and displays
    DOA tracks with their associated class labels.
    """
    
    def __init__(self):
        """Initialize the visualizer."""
        print("\n=== Classified DOA Track Visualization ===\n")
        
        # Load pipeline config
        self.pipe_cfg, self.audio_cfg = load_pipeline_config("sound_event/config/pipeline.yaml")
        self.fs = self.pipe_cfg.sample_rate
        
        # Create pipeline (will be reset per segment)
        self.pipeline = DOAPipeline(self.pipe_cfg)
        
        # Load optional pre-filter
        self.sos = self._load_pre_filter()
        
        # Queue for receiving audio segments with class labels
        self.audio_queue: queue.Queue[Tuple[np.ndarray, str]] = queue.Queue(maxsize=10)
        
        # Latest snapshot with class labels
        self._snapshot_lock = threading.Lock()
        self._latest_snapshots: Optional[list[Dict]] = None
        
        # UI state
        self.ui_tracks: Dict[int, ClassifiedTrack] = {}
        self.current_frame = 0
        self.stop_processing = threading.Event()
        
        # Processing thread
        self.processing_thread: Optional[threading.Thread] = None
        
        print(f"Sample rate: {self.fs} Hz")
        print(f"Expected audio shape: (4, n_samples) where n_samples = {int(1.5 * self.fs)} for 1.5s")
        print("\nReady to receive classified audio segments...")
    
    def _load_pre_filter(self):
        """Load optional pre-filter from config."""
        filt_cfg_path = Path("config/filters.yaml")
        if not filt_cfg_path.exists():
            return None
        
        try:
            with open(filt_cfg_path, "r") as f:
                filt_cfg = yaml.safe_load(f)
            
            if not filt_cfg.get("enable_pre_filter", False):
                return None
            
            if filt_cfg["type"] == "highpass":
                sos = design_highpass(
                    cutoff_hz=filt_cfg["highpass_cutoff_hz"],
                    fs=self.fs,
                    order=filt_cfg.get("order", 4),
                )
            elif filt_cfg["type"] == "bandpass":
                sos = design_bandpass(
                    low_hz=filt_cfg["bandpass_low_hz"],
                    high_hz=filt_cfg["bandpass_high_hz"],
                    fs=self.fs,
                    order=filt_cfg.get("order", 4),
                )
            else:
                return None
            
            print(f"Pre-filter enabled: {filt_cfg['type']}")
            return sos
        except Exception as e:
            logger.warning("Failed to load pre-filter", extra={"error": str(e)})
            return None
    
    def process_classified_audio(self, audios: list):
        # Add to queue (non-blocking, drop if queue is full)
        try:
            self.audio_queue.put_nowait(audios)
        except queue.Full:
            logger.warning("Audio queue full, dropping segment")
    def _processing_loop(self):
        """Process audio segments from queue."""
        while not self.stop_processing.is_set():
            try:
                # Get audio segment with timeout
                sep_audios = self.audio_queue.get(timeout=0.1)

                # Reset pipeline for new segment (fresh tracking)
                self.pipeline.reset()
                
                for sep_audio in sep_audios:    
                    # Apply pre-filter if enabled
                    if self.sos is not None:
                        sep_audio["audio"] = apply_filter(self.sos, sep_audio["audio"], mode="zero_phase")
                        
                audio_samples = sep_audios[0]["audio"].shape[1]
                for i in range(0, audio_samples, self.audio_cfg["block_size"]):
                    snapshots = []
                    for sep_audio in sep_audios:
                        results = self.pipeline.process_block(sep_audio["audio"][:,i:i+self.audio_cfg["block_size"]])
                        # Get final tracks from the segment
                        if results:
                            # Get tracks from the last frame (most stable)
                            last_result = results[-1]
                            tracks = last_result["tracks"]
                            
                            # Associate class label with tracks
                            classified_tracks = []
                            for track in tracks:
                                track_dict = track.as_dict()
                                track_dict["class_label"] = sep_audio["class_name"]
                                classified_tracks.append(track_dict)
                            
                            # Update snapshot
                            snapshot = {
                                "frame_index": self.pipeline.frame_index,
                                "tracks": classified_tracks,
                                "timestamp_sec": time.time(),
                                "class_label": sep_audio["class_name"],
                                "active_labels": sep_audio["active_names"],
                                "color":sep_audio["color"]
                            }
                            snapshots.append(snapshot)
                    with self._snapshot_lock:
                        self._latest_snapshots = snapshots
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing audio segment {e}", extra={"error": str(e)})
    
    def get_latest_snapshot(self) -> Optional[Dict]:
        """Get latest snapshot (thread-safe)."""
        with self._snapshot_lock:
            if self._latest_snapshots is None:
                return None
            return deepcopy(self._latest_snapshots)
    
    def start(self):
        """Start the visualization UI and processing thread."""
        # Start processing thread
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.processing_thread.start()
        
        # Setup matplotlib
        plt.style.use("default")
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection="polar")
        
        # Polar plot configuration
        ax.set_theta_zero_location("E")   # 0° = east (right)
        ax.set_theta_direction(1)         # counterclockwise
        ax.set_title("DOA Tracks with Class Labels (Live)", fontsize=16, pad=20)
        ax.set_ylim(0, 1.0)
        ax.set_rticks([0.25, 0.5, 0.75, 1.0])
        ax.set_rlabel_position(22.5)
        
        # Store plot elements
        arrow_objects: list = []
        text_objects: list[Text] = []
        last_snapshot_frame = -1
        
        def update(_):
            nonlocal arrow_objects, text_objects, last_snapshot_frame
            self.current_frame += 1
            
            # Get latest snapshot
            snapshots = self.get_latest_snapshot()
            if snapshots is None or len(snapshots) == 0:
                # Clear display
                for arrow_obj in arrow_objects:
                    arrow_obj.remove()
                arrow_objects.clear()
                for text_obj in text_objects:
                    text_obj.remove()
                text_objects.clear()
                if self.current_frame % 100 == 0:
                    ax.set_title("DOA Tracks with Class Labels - Waiting for audio...", fontsize=16, pad=20)
                return []
            current_time = time.time()
            for snapshot in snapshots:
                snapshot_frame = snapshot["frame_index"]
                if snapshot_frame != last_snapshot_frame:
                    last_snapshot_frame = snapshot_frame
                
                tracks = snapshot["tracks"]
                snapshot_time = snapshot["timestamp_sec"]
                
                # Update UI track states
                active_valid_track_ids = set()
                
                for track_dict in tracks:
                    track_id = track_dict["id"]
                    
                    if not is_valid_track(track_dict):
                        continue
                    
                    time_since_snapshot_ms = (current_time - snapshot_time) * 1000
                    if time_since_snapshot_ms > MAX_TIME_SINCE_UPDATE_MS:
                        continue
                    
                    theta_deg = track_dict["theta_deg"]
                    confidence = track_dict["confidence"]
                    age = track_dict["age"]
                    class_label = track_dict.get("class_label", "unknown")
                    
                    active_valid_track_ids.add(track_id)
                    
                    # Update or create UI track state
                    if track_id in self.ui_tracks:
                        ui_track = self.ui_tracks[track_id]
                        ui_track.is_active = True
                        ui_track.hold_frames = 0
                        ui_track.theta_history.append(theta_deg)
                        ui_track.confidence_history.append(confidence)
                        ui_track.age = age
                        ui_track.class_label = class_label  # Update class label
                    else:
                        ui_track = ClassifiedTrack(
                            track_id=track_id,
                            theta_deg=theta_deg,
                            confidence=confidence,
                            age=age,
                            class_label=class_label,
                            last_update_frame=self.current_frame,
                        )
                        self.ui_tracks[track_id] = ui_track
                
                # Mark disappeared tracks
                for track_id, ui_track in list(self.ui_tracks.items()):
                    if track_id not in active_valid_track_ids:
                        if ui_track.is_active:
                            ui_track.is_active = False
                            ui_track.hold_frames = TRACK_HOLD_FRAMES
                        else:
                            ui_track.hold_frames -= 1
                            if ui_track.hold_frames <= 0:
                                del self.ui_tracks[track_id]
                                continue
                
                # Clear previous arrows and text
                for arrow_obj in arrow_objects:
                    arrow_obj.remove()
                arrow_objects.clear()
                for text_obj in text_objects:
                    text_obj.remove()
                text_objects.clear()
                
                if not self.ui_tracks:
                    ax.set_title("DOA Tracks with Class Labels - No valid tracks", fontsize=16, pad=20)
                    return []
                
                # Prepare track data with UI smoothing
                track_data = []
                for ui_track in self.ui_tracks.values():
                    # Apply UI-level smoothing
                    if len(ui_track.theta_history) > 0:
                        smoothed_theta = _compute_circular_mean(list(ui_track.theta_history))
                    else:
                        smoothed_theta = ui_track.theta_deg
                    
                    if len(ui_track.confidence_history) > 1:
                        prev_mean = np.mean(list(ui_track.confidence_history)[:-1])
                        smoothed_conf = 0.6 * ui_track.confidence_history[-1] + 0.4 * prev_mean
                    elif len(ui_track.confidence_history) == 1:
                        smoothed_conf = ui_track.confidence_history[0]
                    else:
                        smoothed_conf = ui_track.confidence
                    
                    if not ui_track.is_active:
                        fade_factor = ui_track.hold_frames / TRACK_HOLD_FRAMES
                        smoothed_conf *= fade_factor * 0.5
                    
                    if np.isnan(smoothed_theta) or np.isnan(smoothed_conf) or np.isinf(smoothed_theta) or np.isinf(smoothed_conf):
                        continue
                    
                    smoothed_conf = np.clip(smoothed_conf, 0.0, 1.0)
                    
                    track_data.append({
                        "id": ui_track.track_id,
                        "theta_deg": smoothed_theta,
                        "confidence": smoothed_conf,
                        "age": ui_track.age,
                        "class_label": ui_track.class_label,
                        "is_active": ui_track.is_active,
                    })
                
                # Merge visually close tracks (within same class)
                if len(track_data) > 1:
                    prev_len = len(track_data)
                    track_data = _merge_close_tracks(track_data, merge_threshold_deg=40.0)
                    if len(track_data) < prev_len and len(track_data) > 1:
                        track_data = _merge_close_tracks(track_data, merge_threshold_deg=40.0)
                
                if not track_data or len(track_data) == 0:
                    ax.set_title("DOA Tracks with Class Labels - No valid tracks", fontsize=16, pad=20)
                    return []
                
                # Convert to radians and validate
                theta_rad = []
                radii = []
                colors = []
                valid_tracks = []
                
                min_radius = 0.4
                max_radius = 0.85
                
                for track in track_data:
                    theta_deg = track["theta_deg"]
                    confidence = track["confidence"]
                    
                    if np.isnan(theta_deg) or np.isnan(confidence) or np.isinf(theta_deg) or np.isinf(confidence):
                        continue
                    
                    theta_rad_val = np.deg2rad(theta_deg)
                    radius_val = min_radius + (max_radius - min_radius) * confidence
                    
                    if np.isnan(theta_rad_val) or np.isnan(radius_val):
                        continue
                    
                    theta_rad.append(theta_rad_val)
                    radii.append(radius_val)
                    colors.append(snapshot["color"])
                    valid_tracks.append(track)
                
                track_data = valid_tracks
                
                if not track_data or len(track_data) == 0:
                    ax.set_title("DOA Tracks with Class Labels - No valid tracks", fontsize=16, pad=20)
                    return []
                
                # Draw arrows and markers
                for i, track in enumerate(track_data):
                    theta_rad_i = theta_rad[i]
                    radius_i = radii[i]
                    color_i = colors[i]
                    confidence_i = track["confidence"]
                    class_label = track["class_label"]
                    
                    arrow_width = 2.0 + 3.0 * confidence_i
                    alpha = 0.8 if track.get("is_active", True) else 0.4
                    
                    try:
                        arrow_obj = ax.annotate(
                            '',
                            xy=(theta_rad_i, radius_i),
                            xytext=(0, 0),
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
                        logger.debug(f"Failed to create arrow: {e}")
                        continue
                    
                    try:
                        marker_obj = ax.scatter(
                            [theta_rad_i],
                            [radius_i],
                            s=[100 + 200 * confidence_i],
                            c=[color_i],
                            alpha=alpha * 0.9,
                            edgecolors='black',
                            linewidths=1.5,
                            zorder=11,
                        )
                        arrow_objects.append(marker_obj)
                    except Exception as e:
                        logger.debug(f"Failed to create marker: {e}")
                        continue
                
                # Add text labels with class information
                label_offset_radius = 0.12
                for i, track in enumerate(track_data):
                    try:
                        theta_rad_i = theta_rad[i]
                        radius_i = radii[i]
                        color_i = colors[i]
                        class_label = track["class_label"]
                        
                        if np.isnan(theta_rad_i) or np.isnan(radius_i):
                            continue
                        
                        label_radius = min(0.95, radius_i + label_offset_radius)
                        # Format label: "ID1: 154° (87%) [human]"
                        label = f"ID{track['id']}: {track['theta_deg']:.0f}° ({track['confidence']*100:.0f}%) [{class_label}]"
                        
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
                        logger.debug(f"Failed to create text label: {e}")
                        continue
                
                # Update title
                ax.set_title(
                    f"DOA Tracks with Class Labels - {len(track_data)} valid source(s)",
                    fontsize=16,
                    pad=20,
                    weight='bold',
                )
                
            return arrow_objects + text_objects
        
        # Start animation
        try:
            interval_ms = int(1000 / UI_FPS)
            ani = animation.FuncAnimation(
                fig,
                update,
                interval=interval_ms,
                blit=False,
            )
            print("Opening polar plot window...")
            plt.show()
        except KeyboardInterrupt:
            print("\nStopping visualization...")
        except Exception as e:
            print(f"Error in visualization: {e}")
        finally:
            self.stop_processing.set()
            print("Visualization stopped.")
    
    def stop(self):
        """Stop the visualizer."""
        self.stop_processing.set()
        if self.processing_thread is not None:
            self.processing_thread.join(timeout=1.0)


# ---------------------------------------------------------------------
# Standalone test/demo
# ---------------------------------------------------------------------

def main():
    """Standalone test function."""
    visualizer = ClassifiedDOAVisualizer()
    import librosa
    audio, fs = librosa.load("record_20250826_185208.wav", sr=None, mono=False)
    print(audio.shape)
    visualizer.process_classified_audio([
        {
            'class_name': 'xxx',
            'color': '#030293',
            'active_names': [],
            'audio': audio
        }
    ])
    visualizer.start()


if __name__ == "__main__":
    main()

