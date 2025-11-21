# src/my_doa/utils/doa_logger.py

from __future__ import annotations

import json
import threading
import uuid
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from src.my_doa.doa.tracker import TrackState
from src.my_doa.utils.logger import get_logger


logger = get_logger(__name__)


class DOALogger:
    """
    Production-grade JSONL logger for DOA tracking.

    Features:
    ---------
    • Thread-safe writes
    • Optional log rotation
    • Metadata header (session id, host, version, timestamp)
    • Automatic directory creation
    • Safe close & crash-resistant logging
    • Optional console-mode output

    JSON Lines format:
        {
          "type": "metadata",
          "session_id": "...",
          ...
        }
        {
          "type": "frame",
          "frame_index": int,
          "timestamp_sec": float,
          "tracks": [...]
        }
    """

    def __init__(
        self,
        path: str | Path,
        rotate_bytes: int = 50_000_000,
        console: bool = False,
        metadata: Optional[dict] = None,
    ):
        """
        Parameters
        ----------
        path : str | Path
            File path for logging. Ignored if console=True.
        rotate_bytes : int
            Max file size before rotating logs (~50MB default).
        console : bool
            Print logs to stdout instead of file.
        metadata : dict | None
            Additional metadata to write in header.
        """
        self.console = console
        self.rotate_bytes = int(rotate_bytes)
        self.metadata_extra = metadata or {}

        self._lock = threading.Lock()
        self._session_id = str(uuid.uuid4())
        self._start_time = time.time()
        self._hostname = socket.gethostname()

        if not self.console:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._open_log_file()
        else:
            self.path = None
            self._f = None

        self._write_metadata_record()

    # ---------------------------------------------------------
    # File handling
    # ---------------------------------------------------------
    def _open_log_file(self):
        self._f = self.path.open("w", encoding="utf-8")
        logger.info("DOALogger opened", extra={"path": str(self.path)})

    def _rotate_if_needed(self):
        if self.console:
            return  # console mode ignores rotation

        size = self.path.stat().st_size
        if size < self.rotate_bytes:
            return

        # Rotate file
        rotated_path = self.path.with_suffix(
            self.path.suffix + f".{int(time.time())}.bak"
        )
        self._f.close()
        self.path.rename(rotated_path)
        logger.info(
            "Rotated DOA log",
            extra={"old": str(self.path), "new": str(rotated_path)},
        )
        self._open_log_file()
        self._write_metadata_record()

    # ---------------------------------------------------------
    # Metadata Record
    # ---------------------------------------------------------
    def _write_metadata_record(self):
        rec = {
            "type": "metadata",
            "session_id": self._session_id,
            "hostname": self._hostname,
            "created_utc": datetime.utcnow().isoformat() + "Z",
            "metadata": self.metadata_extra,
        }
        self._write_json_line(rec)

    # ---------------------------------------------------------
    # Public API: frame logging
    # ---------------------------------------------------------
    def log_frame(
        self,
        frame_index: int,
        tracks: Iterable[TrackState],
        timestamp_sec: float | None = None,
    ) -> None:
        if timestamp_sec is None:
            timestamp_sec = time.time() - self._start_time

        # Build frame dict
        rec = {
            "type": "frame",
            "frame_index": int(frame_index),
            "timestamp_sec": float(timestamp_sec),
            "tracks": [self._validate_track_dict(t.as_dict()) for t in tracks],
        }

        self._write_json_line(rec)

    # ---------------------------------------------------------
    # JSON writing (thread-safe)
    # ---------------------------------------------------------
    def _write_json_line(self, rec: dict) -> None:
        line = json.dumps(rec, ensure_ascii=False)

        with self._lock:
            if self.console:
                print(line)
            else:
                try:
                    self._f.write(line + "\n")
                    self._f.flush()
                except Exception as e:
                    logger.error("Failed to write DOA log", extra={"error": str(e)})

                self._rotate_if_needed()

    # ---------------------------------------------------------
    # Schema validation
    # ---------------------------------------------------------
    @staticmethod
    def _validate_track_dict(d: dict) -> dict:
        required = ["id", "theta_deg", "theta_dot_deg_per_sec", "age", "misses", "hits", "confidence"]
        for k in required:
            if k not in d:
                raise KeyError(f"TrackState missing '{k}' in DOA logger.")
        return d

    # ---------------------------------------------------------
    # Close
    # ---------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            try:
                if self._f:
                    self._f.close()
            except Exception:
                pass
