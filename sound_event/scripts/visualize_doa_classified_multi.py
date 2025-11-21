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
import json
import asyncio
import websockets
from typing import Dict, Optional, Tuple
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
        
        # Sort by confidence/intensity (descending)
        sorted_tracks = sorted(class_tracks, key=lambda t: t.get("intensity", t.get("confidence", 0)), reverse=True)
        
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
                        # Support both "theta_deg" and "direction" keys
                        theta1 = close_track.get("theta_deg", close_track.get("direction", 0))
                        theta2 = other_track.get("theta_deg", other_track.get("direction", 0))
                        dist = abs(circular_distance_deg(theta1, theta2))
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
                angles_rad = np.deg2rad([t.get("theta_deg", t.get("direction", 0)) for t in close_tracks])
                confidences = np.array([t.get("intensity", t.get("confidence", 0)) for t in close_tracks])
                
                weights = confidences / (np.sum(confidences) + 1e-8)
                mean_sin = np.sum(weights * np.sin(angles_rad))
                mean_cos = np.sum(weights * np.cos(angles_rad))
                mean_angle_rad = np.arctan2(mean_sin, mean_cos)
                mean_angle_deg = wrap_angle_deg_0_360(np.rad2deg(mean_angle_rad))
                
                best_track = max(close_tracks, key=lambda t: t.get("intensity", t.get("confidence", 0)))
                avg_confidence = np.mean(confidences)
                
                merged.append({
                    "id": best_track.get("id", 0),
                    "direction": float(mean_angle_deg),
                    "distance": float(avg_confidence),
                    "intensity": float(avg_confidence),
                    "class_label": class_label,
                    "color": best_track.get("color", "#00d9ff"),
                    "timestamp": best_track.get("timestamp", int(time.time() * 1000)),
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
        
        # Initialize pipeline (may fail, but we still want WebSocket server)
        self.pipe_cfg = None
        self.audio_cfg = None
        self.fs = 16000  # Default
        self.pipeline = None
        self.sos = None
        
        try:
            # Load pipeline config
            self.pipe_cfg, self.audio_cfg = load_pipeline_config("sound_event/config/pipeline.yaml")
            self.fs = self.pipe_cfg.sample_rate
            
            # Create pipeline (will be reset per segment)
            self.pipeline = DOAPipeline(self.pipe_cfg)
            
            # Load optional pre-filter
            self.sos = self._load_pre_filter()
            print("✓ Pipeline initialized successfully")
        except Exception as e:
            print(f"⚠ Warning: Pipeline initialization failed: {e}")
            print("  WebSocket server will still start, but audio processing will be disabled")
            import traceback
            traceback.print_exc()
        
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
        
        # WebSocket server
        self.websocket_server = None
        self.websocket_clients = set()
        self.websocket_lock = threading.Lock()
        self.websocket_port = 22222
        # Try alternative ports if 22222 is in use
        self.alternative_ports = [22223, 22224, 22225, 22226, 22227]
        self.websocket_ready = threading.Event()
        
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
        if self.pipeline is None:
            print("[Processing Thread] Pipeline not initialized, skipping audio processing")
            while not self.stop_processing.is_set():
                try:
                    # Just drain the queue without processing
                    self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
            return
        
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
                print(f"[Processing] Processing {len(sep_audios)} audio segment(s), {audio_samples} samples")
                for i in range(0, audio_samples, self.audio_cfg["block_size"]):
                    snapshots = []
                    for sep_audio in sep_audios:
                        results = self.pipeline.process_block(sep_audio["audio"][:,i:i+self.audio_cfg["block_size"]])
                        # Get final tracks from the segment
                        if results:
                            # Get tracks from the last frame (most stable)
                            last_result = results[-1]
                            tracks = last_result["tracks"]
                            print(f"[Processing] Frame {self.pipeline.frame_index}: Found {len(tracks)} track(s)")
                            
                            # Associate class label with tracks
                            classified_tracks = []
                            for track in tracks:
                                track_dict = track.as_dict()
                                track_dict["class_label"] = sep_audio["class_name"]
                                classified_tracks.append(track_dict)
                                print(f"  Track ID {track_dict['id']}: theta={track_dict['theta_deg']:.1f}°, "
                                      f"confidence={track_dict['confidence']:.2f}, age={track_dict['age']}, "
                                      f"class={track_dict['class_label']}")
                            
                            # Update snapshot
                            snapshot = {
                                "frame_index": self.pipeline.frame_index,
                                "tracks": classified_tracks,
                                "timestamp_sec": time.time(),
                                "class_label": sep_audio["class_name"],
                                "active_labels": sep_audio["active_names"],
                                "color": sep_audio["color"]
                            }
                            snapshots.append(snapshot)
                    if snapshots:
                        with self._snapshot_lock:
                            self._latest_snapshots = snapshots
                        print(f"[Processing] Updated snapshot with {len(snapshots)} snapshot(s), "
                              f"total tracks: {sum(len(s['tracks']) for s in snapshots)}")
                
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
    
    async def _websocket_handler(self, websocket, path):
        """Handle WebSocket client connections."""
        try:
            remote_addr = websocket.remote_address if hasattr(websocket, 'remote_address') else 'unknown'
            with self.websocket_lock:
                self.websocket_clients.add(websocket)
                client_count = len(self.websocket_clients)
            logger.info(f"WebSocket client connected from {remote_addr}. Total clients: {client_count}")
            print(f"✓ WebSocket client connected from {remote_addr}. Total clients: {client_count}")
            print(f"  Path: {path}")
            
            # Send initial empty data to confirm connection
            try:
                initial_message = json.dumps({
                    "points": [],
                    "timestamp": int(time.time() * 1000),
                })
                await websocket.send(initial_message)
                print(f"  ✓ Sent initial message to client")
            except Exception as e:
                logger.error(f"Error sending initial message: {e}")
                print(f"  ✗ Error sending initial message: {e}")
            
            # Keep connection alive
            await websocket.wait_closed()
        except websockets.exceptions.ConnectionClosed:
            # Normal connection close
            pass
        except Exception as e:
            logger.error(f"Error in WebSocket handler: {e}")
            print(f"✗ Error in WebSocket handler: {e}")
            import traceback
            traceback.print_exc()
        finally:
            with self.websocket_lock:
                self.websocket_clients.discard(websocket)
                client_count = len(self.websocket_clients)
            logger.info(f"WebSocket client disconnected. Total clients: {client_count}")
            print(f"WebSocket client disconnected. Total clients: {client_count}")
    
    async def _broadcast_loop(self):
        """Broadcast track data to all connected WebSocket clients."""
        while not self.stop_processing.is_set():
            try:
                self.current_frame += 1
                current_time = time.time()
                snapshots = self.get_latest_snapshot()
                
                # Prepare track data
                all_track_data = []
                
                if snapshots is not None and len(snapshots) > 0:
                    print(f"[Broadcast] Processing {len(snapshots)} snapshot(s)")
                    for snapshot in snapshots:
                        tracks = snapshot["tracks"]
                        snapshot_time = snapshot["timestamp_sec"]
                        snapshot_color = snapshot.get("color", "#00d9ff")
                        print(f"  Snapshot has {len(tracks)} track(s)")
                        
                        # Update UI track states
                        active_valid_track_ids = set()
                        
                        for track_dict in tracks:
                            track_id = track_dict["id"]
                            
                            if not is_valid_track(track_dict):
                                print(f"  Track ID {track_id} filtered out: confidence={track_dict.get('confidence', 0):.2f}, "
                                      f"age={track_dict.get('age', 0)} (min: {MIN_CONFIDENCE_TO_DISPLAY}, {MIN_AGE_TO_DISPLAY})")
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
                                ui_track.class_label = class_label
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
                                "direction": float(smoothed_theta),
                                "distance": float(smoothed_conf),  # Use confidence as distance
                                "intensity": float(smoothed_conf),
                                "class_label": ui_track.class_label,
                                "color": snapshot_color,
                                "timestamp": int(time.time() * 1000),
                            })
                        
                        # Merge visually close tracks
                        if len(track_data) > 1:
                            track_data = _merge_close_tracks(track_data, merge_threshold_deg=40.0)
                        
                        all_track_data.extend(track_data)
                
                # Convert to JSON and broadcast
                message = json.dumps({
                    "points": all_track_data,
                    "timestamp": int(time.time() * 1000),
                })
                
                if len(all_track_data) > 0:
                    print(f"[Broadcast] Sending {len(all_track_data)} point(s) to clients")
                else:
                    if self.current_frame % 100 == 0:  # Log every 100 frames to avoid spam
                        print(f"[Broadcast] No points to send (frame {self.current_frame})")
                
                # Broadcast to all connected clients
                with self.websocket_lock:
                    clients_to_send = list(self.websocket_clients)
                
                if clients_to_send:
                    disconnected = set()
                    for client in clients_to_send:
                        try:
                            await client.send(message)
                        except Exception as e:
                            logger.debug(f"Error sending to client: {e}")
                            disconnected.add(client)
                    
                    # Remove disconnected clients
                    with self.websocket_lock:
                        self.websocket_clients -= disconnected
                
                # Wait before next broadcast
                await asyncio.sleep(1.0 / UI_FPS)
                
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")
                await asyncio.sleep(0.1)
    
    def start(self):
        """Start the WebSocket server and processing thread."""
        # Start processing thread
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.processing_thread.start()
        
        # Start WebSocket server in a separate thread
        def run_websocket_server():
            try:
                print("[WebSocket Thread] Creating new event loop...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                print("[WebSocket Thread] Event loop created")
                
                async def run_server():
                    port_to_use = self.websocket_port
                    ports_tried = []
                    
                    while True:
                        try:
                            # Test if port is available by trying to bind to it
                            import socket
                            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            try:
                                test_socket.bind(('0.0.0.0', port_to_use))
                                test_socket.close()
                                # Port is available
                            except OSError:
                                # Port is in use - check if it's an HTTP server
                                test_socket.close()
                                print(f"⚠ Port {port_to_use} is already in use")
                                try:
                                    import urllib.request
                                    response = urllib.request.urlopen(f'http://localhost:{port_to_use}', timeout=1)
                                    print(f"  ⚠ Port {port_to_use} is running an HTTP server (not WebSocket)")
                                    print(f"     This will cause 404 errors when trying to connect via WebSocket")
                                except:
                                    pass  # Not an HTTP server, might be something else
                                
                                if self.alternative_ports:
                                    ports_tried.append(port_to_use)
                                    port_to_use = self.alternative_ports.pop(0)
                                    print(f"  → Trying port {port_to_use} instead...")
                                    continue
                                else:
                                    print(f"✗ ERROR: Port {port_to_use} is in use and no alternatives available")
                                    print(f"   Please stop the service using port {port_to_use} or change the port")
                                    break
                            
                            # Create server with proper configuration
                            print(f"Starting WebSocket server on port {port_to_use}...")
                            try:
                                server = await websockets.serve(
                                    self._websocket_handler, 
                                    "0.0.0.0",  # Accept connections from any interface
                                    port_to_use,
                                    ping_interval=20,
                                    ping_timeout=10,
                                    close_timeout=10
                                )
                            except Exception as bind_error:
                                # If binding fails, try next port
                                if "Address already in use" in str(bind_error) or "Only one usage" in str(bind_error):
                                    print(f"  ⚠ Failed to bind to port {port_to_use}: {bind_error}")
                                    if self.alternative_ports:
                                        ports_tried.append(port_to_use)
                                        port_to_use = self.alternative_ports.pop(0)
                                        print(f"  → Trying port {port_to_use} instead...")
                                        continue
                                    else:
                                        raise
                                else:
                                    raise
                            
                            self.websocket_port = port_to_use  # Update the port
                            logger.info(f"WebSocket server started on port {port_to_use}")
                            print(f"✓ WebSocket server started on port {port_to_use}")
                            print(f"✓ Server listening on 0.0.0.0:{port_to_use}")
                            print(f"✓ Connect from frontend: ws://localhost:{port_to_use}")
                            print(f"✓ Server is ready to accept connections")
                            self.websocket_ready.set()
                            
                            # Keep server running
                            async with server:
                                await self._broadcast_loop()
                        except OSError as e:
                            if "Address already in use" in str(e) or "Only one usage of each socket address" in str(e):
                                ports_tried.append(port_to_use)
                                # Try alternative ports
                                if self.alternative_ports:
                                    port_to_use = self.alternative_ports.pop(0)
                                    print(f"⚠ Port {ports_tried[-1]} is in use, trying port {port_to_use}...")
                                    continue
                                else:
                                    logger.error(f"All ports tried: {ports_tried}. Port {port_to_use} is already in use.")
                                    print(f"✗ ERROR: All ports {ports_tried + [port_to_use]} are in use!")
                                    print(f"   Please close any other application using these ports")
                                    break
                            else:
                                logger.error(f"Error in WebSocket server: {e}")
                                print(f"✗ Error in WebSocket server: {e}")
                                import traceback
                                traceback.print_exc()
                                break
                        except Exception as e:
                            logger.error(f"Error in WebSocket server: {e}")
                            print(f"✗ Error in WebSocket server: {e}")
                            import traceback
                            traceback.print_exc()
                            break
                
                # Run the async server
                print("[WebSocket Thread] Starting async server...")
                loop.run_until_complete(run_server())
            except KeyboardInterrupt:
                print("\n[WebSocket Thread] Stopping WebSocket server...")
            except Exception as e:
                print(f"\n✗ [WebSocket Thread] ERROR: Failed to start WebSocket server: {e}")
                logger.error(f"WebSocket server error: {e}")
                import traceback
                traceback.print_exc()
                # Clear ready event to indicate failure
                self.websocket_ready.clear()
            finally:
                try:
                    # Cancel all tasks
                    tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
                    for task in tasks:
                        task.cancel()
                    if tasks:
                        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                except:
                    pass
                try:
                    loop.close()
                except:
                    pass
                self.stop_processing.set()
                print("[WebSocket Thread] WebSocket server thread exiting.")
        
        websocket_thread = threading.Thread(target=run_websocket_server, daemon=True)
        websocket_thread.start()
        print(f"[Main Thread] WebSocket server thread started (daemon={websocket_thread.daemon}, thread_id={websocket_thread.ident})")
        
        # Wait for server to be ready (with timeout)
        print("[Main Thread] Waiting for WebSocket server to start (timeout: 10 seconds)...")
        if self.websocket_ready.wait(timeout=10.0):
            print("\n" + "="*60)
            print("✓ WebSocket server is ready and listening")
            print(f"✓ Frontend should connect to: ws://localhost:{self.websocket_port}")
            print("="*60 + "\n")
        else:
            print("\n" + "="*60)
            print("⚠ WARNING: WebSocket server may not have started properly")
            print("  Check for errors above or port conflicts")
            print("  The server thread may have encountered an error")
            print(f"  Thread alive: {websocket_thread.is_alive()}")
            print("="*60 + "\n")
        
        # Keep main thread alive
        try:
            while not self.stop_processing.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping...")
            self.stop_processing.set()
    
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
    print("\n" + "="*60)
    print("Starting ClassifiedDOAVisualizer WebSocket Server...")
    print("="*60 + "\n")
    
    try:
        visualizer = ClassifiedDOAVisualizer()
        print("\n" + "="*60)
        print("Calling visualizer.start()...")
        print("="*60 + "\n")
        visualizer.start()
        
        print("\n" + "="*60)
        print("Server startup initiated.")
        print("Keep this script running to maintain the WebSocket server.")
        print("Press Ctrl+C to stop.")
        print("="*60 + "\n")
        
        # CRITICAL: Keep the script running - otherwise daemon threads will be killed!
        try:
            while not visualizer.stop_processing.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nStopping server...")
            visualizer.stop()
            print("Server stopped.")
    except Exception as e:
        print(f"\n✗ ERROR: Failed to start visualizer: {e}")
        import traceback
        traceback.print_exc()
        return


if __name__ == "__main__":
    main()

