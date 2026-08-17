"""System Resource Monitor for collecting real-time CPU, RAM, and OS metrics during benchmarks."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import List, Optional
import psutil


@dataclass
class ResourceSample:
    timestamp: float
    cpu_percent: float
    memory_rss_mb: float
    memory_percent: float
    open_connections: int
    thread_count: int


@dataclass
class MonitorSummary:
    duration_s: float = 0.0
    samples_count: int = 0
    cpu_avg: float = 0.0
    cpu_peak: float = 0.0
    memory_rss_mb_start: float = 0.0
    memory_rss_mb_peak: float = 0.0
    memory_rss_mb_end: float = 0.0
    memory_growth_mb: float = 0.0
    peak_open_connections: int = 0
    peak_thread_count: int = 0


class SystemMonitor:
    """Monitors system and process resource utilization in a background task."""

    def __init__(
        self, target_pid: Optional[int] = None, sample_interval_s: float = 0.2
    ):
        self.target_pid = target_pid or os.getpid()
        self.sample_interval_s = sample_interval_s
        self.samples: List[ResourceSample] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._process = psutil.Process(self.target_pid)

    async def _sample_loop(self) -> None:
        while self._running:
            try:
                cpu = self._process.cpu_percent(interval=None)
                mem = self._process.memory_info()
                mem_rss_mb = mem.rss / (1024 * 1024)
                mem_pct = self._process.memory_percent()
                threads = self._process.num_threads()

                conns = 0
                try:
                    conns = len(self._process.net_connections())
                except Exception:
                    pass

                self.samples.append(
                    ResourceSample(
                        timestamp=time.time(),
                        cpu_percent=cpu,
                        memory_rss_mb=mem_rss_mb,
                        memory_percent=mem_pct,
                        open_connections=conns,
                        thread_count=threads,
                    )
                )
            except Exception:
                pass
            await asyncio.sleep(self.sample_interval_s)

    async def start(self) -> None:
        self.samples.clear()
        self._running = True
        # Prime cpu_percent
        try:
            self._process.cpu_percent(interval=None)
        except Exception:
            pass
        self._task = asyncio.create_task(self._sample_loop())

    async def stop(self) -> MonitorSummary:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        return self.get_summary()

    def get_summary(self) -> MonitorSummary:
        if not self.samples:
            return MonitorSummary()

        cpus = [s.cpu_percent for s in self.samples]
        mems = [s.memory_rss_mb for s in self.samples]
        conns = [s.open_connections for s in self.samples]
        threads = [s.thread_count for s in self.samples]

        duration = self.samples[-1].timestamp - self.samples[0].timestamp
        start_mem = mems[0]
        end_mem = mems[-1]
        peak_mem = max(mems)

        return MonitorSummary(
            duration_s=round(duration, 2),
            samples_count=len(self.samples),
            cpu_avg=round(sum(cpus) / len(cpus), 2) if cpus else 0.0,
            cpu_peak=round(max(cpus), 2) if cpus else 0.0,
            memory_rss_mb_start=round(start_mem, 2),
            memory_rss_mb_peak=round(peak_mem, 2),
            memory_rss_mb_end=round(end_mem, 2),
            memory_growth_mb=round(max(0.0, peak_mem - start_mem), 2),
            peak_open_connections=max(conns) if conns else 0,
            peak_thread_count=max(threads) if threads else 0,
        )
