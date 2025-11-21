# src/my_doa/utils/config_loader.py

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from src.my_doa.pipeline.doa_pipeline import DOAPipelineConfig
from src.my_doa.pipeline.doa_pipeline import STFTConfig, MCRAConfig, SSLConfig
from src.my_doa.doa.tracker import TrackerConfig
from src.my_doa.utils.logger import get_logger


logger = get_logger(__name__)


# -------------------------------------------------------------
# YAML LOADING HELPERS
# -------------------------------------------------------------

def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise RuntimeError(f"Config file {path} is empty or invalid YAML.")
    return data


def _resolve_path(p: str | Path) -> Path:
    return Path(p).expanduser().resolve()


# -------------------------------------------------------------
# VALIDATION HELPERS
# -------------------------------------------------------------

def _validate_required_keys(cfg: dict, required: list, name: str):
    for key in required:
        if key not in cfg:
            raise KeyError(f"Missing required key '{key}' in {name} config.")


# -------------------------------------------------------------
# DEFAULT CONFIGS (robustness)
# -------------------------------------------------------------

DEFAULT_STFT = {
    "frame_size": 512,
    "hop_size": 256,
    "window_type": "hann",
    "fft_size": None,
}

DEFAULT_MCRA = {
    "alpha_s": 0.9,
    "minima_window": 40,
    "delta": 1.5,
}

DEFAULT_SSL = {
    "azimuth_res_deg": 1.0,
    "max_sources": 3,
    "min_power": 0.05,
    "suppression_deg": 25.0,
    "bandpass_low_hz": 300.0,
    "bandpass_high_hz": 4000.0,
    "orientation_offset_deg": 0.0,
    "use_snr_mask": True,
    "snr_mask_low_db": 0.0,
    "snr_mask_high_db": 20.0,
    "use_freq_weighting": True,
    "freq_weight_peak_hz": 1500.0,
    "freq_weight_width_hz": 2000.0,
    "use_pair_weighting": True,
    "use_temporal_smoothing": True,
    "temporal_smoothing_alpha": 0.8,
    "use_tracking_boost": True,
    "tracking_boost_lambda": 0.3,
    "tracking_boost_sigma_deg": 15.0,
}

DEFAULT_TRACKER = {
    "process_noise": 5.0,
    "measurement_noise": 5.0,
    "gate_deg": 20.0,
    "birth_frames": 3,
    "death_frames": 10,
    "pending_track_power_threshold": 0.03,
    "pending_track_max_age": 8,
    "min_confidence_for_promotion": 0.20,
    "min_hit_rate_for_promotion": 0.4,
    "min_confidence_to_keep": 0.10,
    "low_confidence_frames_before_removal": 6,
    # dt auto-filled later
}


# -------------------------------------------------------------
# MAIN LOADER
# -------------------------------------------------------------

def load_pipeline_config(
    pipeline_yaml: str | Path = "sound_event/config/pipeline.yaml",
    env: str | None = None,
) -> Tuple[DOAPipelineConfig, dict]:
    """
    Load master pipeline config and construct typed config objects.

    Parameters
    ----------
    pipeline_yaml : str | Path
        Path to main pipeline YAML.
    env : str | None
        Optional environment name ("dev", "prod", etc.).

    Returns
    -------
    pipeline_config : DOAPipelineConfig
    audio_cfg : dict
    """

    pipeline_path = _resolve_path(pipeline_yaml)
    pipe_raw = _load_yaml(pipeline_path)

    #
    # Resolve all sub-config paths
    #
    geometry_path = _resolve_path(pipe_raw.get("geometry_path", "config/array_geometry.yaml"))
    audio_path = _resolve_path(pipe_raw.get("audio", "config/audio.yaml"))
    stft_path = _resolve_path(pipe_raw.get("stft", "config/stft.yaml"))
    noise_path = _resolve_path(pipe_raw.get("noise", "config/noise.yaml"))
    ssl_path = _resolve_path(pipe_raw.get("ssl", "config/ssl.yaml"))
    tracker_path = _resolve_path(pipe_raw.get("tracker", "config/tracker.yaml"))

    #
    # Load sub-configs
    #
    audio_cfg = _load_yaml(audio_path)
    stft_raw = _load_yaml(stft_path)
    noise_raw = _load_yaml(noise_path)
    ssl_raw = _load_yaml(ssl_path)
    tracker_raw = _load_yaml(tracker_path)

    # Required keys
    _validate_required_keys(audio_cfg, ["sample_rate"], "audio")

    sample_rate = float(audio_cfg["sample_rate"])
    
    # Channel mapping (optional, for ReSpeaker 6-channel firmware)
    channel_mapping = audio_cfg.get("channel_mapping", None)
    if channel_mapping is not None:
        channel_mapping = [int(x) for x in channel_mapping]  # Ensure int list
    
    # Capture channels (optional, only needed if channel_mapping is used)
    capture_channels = audio_cfg.get("capture_channels", None)
    if capture_channels is not None:
        capture_channels = int(capture_channels)

    #
    # Merge defaults → user overrides
    #
    stft_cfg = {**DEFAULT_STFT, **stft_raw}
    noise_cfg = {**DEFAULT_MCRA, **noise_raw}
    ssl_cfg = {**DEFAULT_SSL, **ssl_raw}
    tracker_cfg = {**DEFAULT_TRACKER, **tracker_raw}

    #
    # Inject dt for tracker
    #
    tracker_cfg["dt"] = float(stft_cfg["hop_size"]) / sample_rate

    #
    # Instantiate typed config objects
    #
    stft = STFTConfig(**stft_cfg)
    mcra = MCRAConfig(**noise_cfg)
    ssl = SSLConfig(**ssl_cfg)
    tracker = TrackerConfig(**tracker_cfg)

    #
    # Construct DOA pipeline config
    #
    pipe_cfg = DOAPipelineConfig(
        geometry_path=str(geometry_path),
        sample_rate=sample_rate,
        stft=stft,
        mcra=mcra,
        ssl=ssl,
        tracker=tracker,
    )

    logger.info(
        "Pipeline configuration fully loaded",
        extra={
            "pipeline_yaml": str(pipeline_path),
            "environment": env,
            "sample_rate": sample_rate,
        },
    )

    return pipe_cfg, audio_cfg
