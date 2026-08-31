"""Infrastructure abstraction layer for asynchronous job execution (Phase 5).

Decouples the core repository analysis pipeline from specific deployment platforms
(Local Thread/Queue, Modal, Azure Container Apps / Service Bus / Storage Queue).
"""

from __future__ import annotations

import abc
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)


class QueueMessageBackend(Protocol):
    """Protocol for abstract queue backends (Azure Storage Queue, Service Bus, or Memory)."""

    def send_message(self, content: str) -> Any: ...


class MemoryQueueBackend:
    """Thread-safe in-memory queue backend for local development and unit tests."""

    def __init__(self) -> None:
        import queue

        self._q: queue.Queue[str] = queue.Queue()

    def send_message(self, content: str) -> None:
        self._q.put(content)

    def receive_message(self, timeout: float = 0.5) -> Optional[str]:
        import queue

        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def empty(self) -> bool:
        return self._q.empty()

    def qsize(self) -> int:
        return self._q.qsize()


# Global shared in-memory queue singleton for local queue-based testing
_SHARED_LOCAL_QUEUE = MemoryQueueBackend()


def get_shared_local_queue() -> MemoryQueueBackend:
    """Get the shared in-memory queue for testing queue workflows locally."""
    return _SHARED_LOCAL_QUEUE


class JobExecutor(abc.ABC):
    """Abstract interface for background repository analysis job executors."""

    @abc.abstractmethod
    def spawn_analysis(
        self,
        job_id: str,
        repo_url: str,
        branch: str = "main",
        force_rebuild: bool = False,
        request_id: Optional[str] = None,
    ) -> bool:
        """Spawn background analysis execution. Returns True if successfully dispatched."""
        pass


class ModalJobExecutor(JobExecutor):
    """Modal serverless container function adapter."""

    def spawn_analysis(
        self,
        job_id: str,
        repo_url: str,
        branch: str = "main",
        force_rebuild: bool = False,
        request_id: Optional[str] = None,
    ) -> bool:
        try:
            import modal_app

            if hasattr(modal_app, "run_analysis_job") and hasattr(
                modal_app.run_analysis_job, "spawn"
            ):
                modal_app.run_analysis_job.spawn(
                    repo_url=repo_url,
                    branch=branch,
                    force_rebuild=force_rebuild,
                    request_id=request_id or job_id,
                    job_id=job_id,
                )
                logger.info("ModalJobExecutor: spawned job=%s for %s", job_id, repo_url)
                return True
        except Exception as exc:
            logger.warning("ModalJobExecutor spawn failed: %s", exc)
        return False


class LocalJobExecutor(JobExecutor):
    """Bounded local thread-pool background job executor for development and testing."""

    _executor: Optional[Any] = None
    _lock = threading.Lock()
    _active_jobs: set[str] = set()
    _queued_jobs: set[str] = set()

    def __init__(self, max_workers: Optional[int] = None) -> None:
        self._custom_max_workers = max_workers

    @classmethod
    def get_pool(cls, max_workers: Optional[int] = None) -> Any:
        from concurrent.futures import ThreadPoolExecutor
        from core.config import settings

        with cls._lock:
            effective = (
                max_workers
                if max_workers and max_workers > 0
                else settings.max_concurrent_analyses
            )
            if cls._executor is None:
                cls._executor = ThreadPoolExecutor(
                    max_workers=effective, thread_name_prefix="aria-analysis"
                )
                cls._max_workers_count = effective
            return cls._executor

    @classmethod
    def reset_pool(cls) -> None:
        """Helper for testing to cleanly shutdown and recreate thread pool."""
        with cls._lock:
            if cls._executor is not None:
                try:
                    cls._executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                cls._executor = None
            cls._active_jobs.clear()
            cls._queued_jobs.clear()

    @classmethod
    def active_job_count(cls) -> int:
        with cls._lock:
            return len(cls._active_jobs)

    @classmethod
    def queued_job_count(cls) -> int:
        with cls._lock:
            return len(cls._queued_jobs)

    def spawn_analysis(
        self,
        job_id: str,
        repo_url: str,
        branch: str = "main",
        force_rebuild: bool = False,
        request_id: Optional[str] = None,
    ) -> bool:
        from backend.routers.repositories import (
            execute_repository_analysis,
            format_analysis_error,
            get_job_state,
            set_job_state,
        )
        from core.config import settings
        from core.repository_target import get_analysis_target_key

        target_key = get_analysis_target_key(repo_url, branch)
        max_w = (
            self._custom_max_workers
            or getattr(self.__class__, "_max_workers_count", None)
            or settings.max_concurrent_analyses
        )
        pool = self.get_pool(self._custom_max_workers)

        enqueued_time = time.perf_counter()
        with self._lock:
            self._queued_jobs.add(job_id)
            q_len = len(self._queued_jobs)
            act_len = len(self._active_jobs)

        logger.info(
            "[ANALYSIS_QUEUE] job=%s target=%s event=queued active=%d queued=%d max_workers=%d",
            job_id,
            target_key,
            act_len,
            q_len,
            max_w,
        )

        def _run():
            q_wait_ms = (time.perf_counter() - enqueued_time) * 1000.0
            with self._lock:
                self._queued_jobs.discard(job_id)
                self._active_jobs.add(job_id)
                act_count = len(self._active_jobs)

            logger.info(
                "[ANALYSIS_QUEUE] job=%s target=%s event=started queue_wait_ms=%.2f active=%d max_workers=%d",
                job_id,
                target_key,
                q_wait_ms,
                act_count,
                max_w,
            )

            initial_state = get_job_state(job_id) or {"job_id": job_id}

            def _progress(update: Dict[str, Any]):
                curr = get_job_state(job_id) or initial_state
                curr.update(update)
                curr["status"] = "running"
                set_job_state(job_id, curr)

            try:
                initial_state["status"] = "running"
                set_job_state(job_id, initial_state)
                result = execute_repository_analysis(
                    repo_url=repo_url,
                    branch=branch,
                    force_rebuild=force_rebuild,
                    progress_callback=_progress,
                    request_id=request_id or job_id,
                    job_id=job_id,
                )
                curr = get_job_state(job_id) or initial_state
                final_status = (
                    "partial"
                    if result and result.get("status") == "partial"
                    else "completed"
                )
                curr["status"] = final_status
                curr["progress"] = 100
                curr["result"] = result
                if result:
                    curr["successful_phases"] = result.get("successful_phases", [])
                    curr["failed_phases"] = result.get("failed_phases", [])
                    curr["skipped_phases"] = result.get("skipped_phases", [])
                    curr["phase_errors"] = result.get("phase_errors", {})
                set_job_state(job_id, curr)

                with self._lock:
                    self._active_jobs.discard(job_id)
                    act_count = len(self._active_jobs)
                logger.info(
                    "[ANALYSIS_QUEUE] job=%s target=%s event=completed status=%s active=%d max_workers=%d",
                    job_id,
                    target_key,
                    final_status,
                    act_count,
                    max_w,
                )
            except Exception as exc:
                with self._lock:
                    self._active_jobs.discard(job_id)
                    act_count = len(self._active_jobs)
                logger.error(
                    "[ANALYSIS_QUEUE] job=%s target=%s event=failed error=%s active=%d max_workers=%d",
                    job_id,
                    target_key,
                    exc,
                    act_count,
                    max_w,
                    exc_info=True,
                )
                curr = get_job_state(job_id) or initial_state
                curr["status"] = "failed"
                curr["error"] = format_analysis_error(exc)
                set_job_state(job_id, curr)

        try:
            pool.submit(_run)
            return True
        except Exception as exc:
            with self._lock:
                self._queued_jobs.discard(job_id)
                self._active_jobs.discard(job_id)
            logger.error(
                "LocalJobExecutor failed to submit job=%s: %s",
                job_id,
                exc,
                exc_info=True,
            )
            return False


class AzureJobExecutor(JobExecutor):
    """Azure Queue / Service Bus adapter for asynchronous job execution.

    Pushes structured job payloads to an Azure Storage Queue, Azure Service Bus,
    or a memory queue for local testing. Does NOT execute repository analysis in-process.
    """

    def __init__(
        self,
        queue_client: Optional[QueueMessageBackend] = None,
        queue_name: Optional[str] = None,
        connection_string: Optional[str] = None,
        use_memory_queue: bool = False,
    ) -> None:
        self.queue_client = queue_client
        self.queue_name = queue_name or os.environ.get(
            "AZURE_STORAGE_QUEUE_NAME", "aria-analysis-jobs"
        )
        self.connection_string = connection_string or os.environ.get(
            "AZURE_STORAGE_CONNECTION_STRING"
        )
        self.use_memory_queue = use_memory_queue

    def _get_client(self) -> QueueMessageBackend:
        if self.queue_client is not None:
            return self.queue_client

        if self.use_memory_queue or os.environ.get(
            "AZURE_USE_MEMORY_QUEUE", ""
        ).lower() in ("1", "true", "yes"):
            return _SHARED_LOCAL_QUEUE

        if not self.connection_string:
            raise RuntimeError(
                "AzureJobExecutor: AZURE_STORAGE_CONNECTION_STRING is not configured. "
                "Set the connection string or set AZURE_USE_MEMORY_QUEUE=1 for local testing."
            )

        try:
            from azure.storage.queue import (  # type: ignore
                QueueClient,
                TextBase64EncodePolicy,
                TextBase64DecodePolicy,
            )

            client = QueueClient.from_connection_string(
                conn_str=self.connection_string,
                queue_name=self.queue_name,
                message_encode_policy=TextBase64EncodePolicy(),
                message_decode_policy=TextBase64DecodePolicy(),
            )
            # Create queue if it does not exist
            try:
                client.create_queue()
            except Exception:
                pass
            return client
        except ImportError as exc:
            raise RuntimeError(
                "azure-storage-queue is required for AzureJobExecutor. "
                "Install with 'pip install azure-storage-queue'."
            ) from exc

    def serialize_payload(
        self,
        job_id: str,
        repo_url: str,
        branch: str = "main",
        force_rebuild: bool = False,
        request_id: Optional[str] = None,
    ) -> str:
        """Create JSON payload string for queue message."""
        payload = {
            "job_id": job_id,
            "request_id": request_id or job_id,
            "repo_url": repo_url,
            "branch": branch,
            "force_rebuild": force_rebuild,
            "enqueued_at": time.time(),
        }
        return json.dumps(payload)

    def spawn_analysis(
        self,
        job_id: str,
        repo_url: str,
        branch: str = "main",
        force_rebuild: bool = False,
        request_id: Optional[str] = None,
    ) -> bool:
        payload_str = self.serialize_payload(
            job_id=job_id,
            repo_url=repo_url,
            branch=branch,
            force_rebuild=force_rebuild,
            request_id=request_id,
        )
        client = self._get_client()

        # Azure Queue client handles string or binary depending on message_encode_policy
        if hasattr(client, "send_message"):
            client.send_message(payload_str)
            logger.info(
                "AzureJobExecutor: enqueued job=%s to %s", job_id, self.queue_name
            )
            return True

        raise RuntimeError(
            f"Configured queue client {type(client)} does not implement send_message."
        )


# Retain alias for backward compatibility with initial design references
AzureJobExecutorDesign = AzureJobExecutor


def get_job_executor() -> JobExecutor:
    """Factory function resolving the active JobExecutor from environment configuration.

    Supported JOB_EXECUTOR values:
      - 'local' (default): in-process background thread
      - 'modal': Modal serverless functions
      - 'azure': Azure Queue / Container Apps Job dispatch
    """
    mode = os.environ.get("JOB_EXECUTOR", "local").strip().lower()

    if mode == "local":
        return LocalJobExecutor()
    if mode == "modal":
        return ModalJobExecutor()
    if mode == "azure":
        return AzureJobExecutor()

    raise ValueError(
        f"Unknown JOB_EXECUTOR '{mode}'. Valid options are 'local', 'modal', 'azure'."
    )
