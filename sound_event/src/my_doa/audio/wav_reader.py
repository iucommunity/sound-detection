# src/my_doa/audio/wav_reader.py
"""
WAV utilities for offline DOA testing.

Features:
- Safe loading of large WAV files
- Ensures output is (n_mics, n_samples) float32
- Consistent logging interface
- Robust block generator with optional strict mode
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator, Tuple, Optional

import numpy as np
import soundfile as sf

from src.my_doa.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------
# WAV Loader
# ---------------------------------------------------------------------

def load_multichannel_wav(
    path: str | Path,
    expected_channels: Optional[int] = None,
    mmap: bool = False,
) -> Tuple[np.ndarray, int]:
    """
    Load a multichannel WAV as (n_mics, n_samples) float32.
    Validates channel count when expected_channels is provided.
    """

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"WAV file not found: {path}")

    try:
        # mmap argument may not be supported by older soundfile versions
        data, fs = sf.read(str(path), always_2d=True, dtype="float32")
    except Exception as e:
        raise RuntimeError(f"Failed to read WAV file {path}: {e}")

    n_samples, n_channels = data.shape

    if n_samples == 0:
        raise RuntimeError(f"WAV contains zero samples: {path}")

    # ============================================================
    # HARD VALIDATION: reject audio if channel count mismatches
    # ============================================================
    if expected_channels is not None:
        if n_channels != expected_channels:
            raise ValueError(
                f"Invalid WAV: expected {expected_channels} channels, "
                f"but WAV has {n_channels} channels. File: {path}"
            )

    logger.info(
        "Loaded WAV",
        extra={
            "path": str(path),
            "sample_rate": fs,
            "n_channels": n_channels,
            "n_samples": n_samples,
        },
    )

    # Convert to (n_mics, n_samples)
    audio = np.ascontiguousarray(data.T, dtype=np.float32)
    return audio, int(fs)


# ---------------------------------------------------------------------
# Block Generator
# ---------------------------------------------------------------------

def block_generator(
    audio: np.ndarray,
    block_size: int,
    strict: bool = False,
) -> Generator[np.ndarray, None, None]:
    """
    Yield sequential blocks from multichannel audio.

    Parameters
    ----------
    audio : np.ndarray
        Array (n_mics, n_samples)
    block_size : int
        Number of samples per block.
    strict : bool
        If True, drop the final incomplete block.

    Yields
    ------
    np.ndarray
        Block (n_mics, block_len)
    """
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 2:
        raise ValueError("audio must have shape (n_mics, n_samples)")

    n_mics, n_samples = audio.shape

    if block_size <= 0:
        raise ValueError("block_size must be > 0")

    for start in range(0, n_samples, block_size):
        end = start + block_size

        if end > n_samples:
            if strict:
                return
            end = n_samples

        yield audio[:, start:end]
