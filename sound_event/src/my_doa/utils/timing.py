"""
High-precision timing utilities for real-time DOA pipelines.

Includes:
---------
• FpsMeter     – smoothed frames-per-second meter
• RateMeter    – general event-rate meter
• Stopwatch    – start/stop high-precision timer
• Timer        – context manager for profiling code blocks

All utilities:
• Zero allocations after init (real-time safe)
• Use monotonic clock (robust to system time changes)
• Lightweight and production-ready
"""

from __future__ import annotations
import time
from typing import Optional


# ================================================================
# FPS METER (smoothed)
# ================================================================
class FpsMeter:
    """
    Smoothed FPS estimator for continuous real-time loops.

    Example:
        fps = fps_meter.tick()
    """

    def __init__(self, smoothing: float = 0.9):
        self.smoothing = float(smoothing)
        self.last_t = time.perf_counter()
        self.fps = 0.0

    def tick(self) -> float:
        """Call once per processed frame."""
        now = time.perf_counter()
        dt = now - self.last_t
        self.last_t = now

        if dt <= 0:
            return self.fps

        instant = 1.0 / dt
        self.fps = self.smoothing * self.fps + (1 - self.smoothing) * instant
        return self.fps


# ================================================================
# RATE METER (general event rate)
# ================================================================
class RateMeter:
    """
    General smoothed event-rate meter.

    Example:
        rate = meter.tick(count=n_events)
    """

    def __init__(self, smoothing: float = 0.9):
        self.smoothing = float(smoothing)
        self.last_t = time.perf_counter()
        self.rate = 0.0

    def tick(self, count: float = 1.0) -> float:
        now = time.perf_counter()
        dt = now - self.last_t
        self.last_t = now

        if dt <= 0:
            return self.rate

        instant = count / dt
        self.rate = self.smoothing * self.rate + (1 - self.smoothing) * instant
        return self.rate


# ================================================================
# STOPWATCH (start/stop)
# ================================================================
class Stopwatch:
    """
    Simple high-precision stopwatch.

    Example:
        sw = Stopwatch()
        sw.start()
        ...
        print(sw.elapsed())
        sw.reset()
    """

    def __init__(self):
        self._start: Optional[float] = None
        self._elapsed: float = 0.0

    def start(self):
        if self._start is None:
            self._start = time.perf_counter()

    def stop(self) -> float:
        """Stop timer and return elapsed seconds."""
        if self._start is None:
            return self._elapsed
        self._elapsed += time.perf_counter() - self._start
        self._start = None
        return self._elapsed

    def reset(self):
        self._start = None
        self._elapsed = 0.0

    def elapsed(self) -> float:
        """Get elapsed time without stopping."""
        if self._start is None:
            return self._elapsed
        return self._elapsed + (time.perf_counter() - self._start)


# ================================================================
# TIMER (context manager)
# ================================================================
class Timer:
    """
    Context manager for profiling arbitrary code blocks.

    Example:
        with Timer() as t:
            heavy_stuff()
        print(t.ms)
    """

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.t1 = time.perf_counter()
        self.sec = self.t1 - self.t0
        self.ms = self.sec * 1000.0
        return False  # don't suppress exceptions
