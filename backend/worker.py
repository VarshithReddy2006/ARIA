"""Azure Container Apps Job and Background Worker process for ARIA.

Consumes analysis job messages from an Azure Storage Queue, Azure Service Bus,
or local in-memory test queue, and drives the frozen core repository analysis pipeline.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.routers.repositories import (
    execute_repository_analysis,
    format_analysis_error,
    get_job_state,
    parse_repo_name,
    set_job_state,
)
from core.job_state import JobStatus
from infrastructure.job_executor import get_shared_local_queue

# Set line buffering for instant container logs
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="[Worker Log] %(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("aria.worker")
logger.setLevel(logging.INFO)


class AnalysisWorker:
    """Worker handling polling, deserialization, and execution of analysis jobs."""

    def __init__(
        self,
        queue_name: Optional[str] = None,
        connection_string: Optional[str] = None,
        use_memory_queue: bool = False,
        poll_interval: float = 2.0,
    ) -> None:
        self.queue_name = queue_name or os.environ.get(
            "AZURE_STORAGE_QUEUE_NAME", "aria-analysis-jobs"
        )
        self.connection_string = connection_string or os.environ.get(
            "AZURE_STORAGE_CONNECTION_STRING"
        )
        self.use_memory_queue = use_memory_queue or os.environ.get(
            "AZURE_USE_MEMORY_QUEUE", ""
        ).lower() in ("1", "true", "yes")
        self.poll_interval = poll_interval
        self._running = True
        self._client = self._init_queue_client()

    def _init_queue_client(self) -> Any:
        if self.use_memory_queue or not self.connection_string:
            print("[Worker] Initialized in-memory test queue", flush=True)
            return get_shared_local_queue()

        try:
            from azure.storage.queue import QueueClient, TextBase64DecodePolicy  # type: ignore

            client = QueueClient.from_connection_string(
                conn_str=self.connection_string,
                queue_name=self.queue_name,
                message_decode_policy=TextBase64DecodePolicy(),
            )
            print(
                f"[Worker] Initialized Azure Storage Queue client: {self.queue_name}",
                flush=True,
            )
            return client
        except ImportError as exc:
            print(f"[Worker] azure-storage-queue not available: {exc}", flush=True)
            logger.warning(
                "azure-storage-queue not available; falling back to local queue: %s",
                exc,
            )
            return get_shared_local_queue()

    def _get_queue_client(self) -> Any:
        if hasattr(self, "_client") and self._client is not None:
            return self._client
        self._client = self._init_queue_client()
        return self._client

    def process_message_payload(self, raw_payload: str) -> bool:
        """Parse payload, update job state, and execute analysis."""
        try:
            data = json.loads(raw_payload)
        except (json.JSONDecodeError, TypeError):
            try:
                import base64

                decoded = base64.b64decode(raw_payload).decode("utf-8")
                data = json.loads(decoded)
            except Exception as exc:
                print(f"[Worker] Malformed JSON payload: {exc}", flush=True)
                logger.error("Worker received malformed JSON message: %s", exc)
                return False

        job_id = data.get("job_id")
        request_id = data.get("request_id") or job_id
        repo_url = data.get("repo_url")
        branch = data.get("branch", "main")
        force_rebuild = data.get("force_rebuild", False)

        if not job_id or not repo_url:
            logger.error("Worker received incomplete job payload: %s", data)
            return False

        repo_name = parse_repo_name(repo_url)
        owner = repo_name.split("/")[0] if "/" in repo_name else "owner"
        name = repo_name.split("/")[1] if "/" in repo_name else repo_name

        logger.info(
            "Worker starting analysis for job=%s repo=%s branch=%s",
            job_id,
            repo_name,
            branch,
        )

        # Initialize/update job state to RUNNING
        job_start_time = time.time()
        current_state = get_job_state(job_id) or {
            "job_id": job_id,
            "request_id": request_id,
            "repo_url": repo_url,
            "branch": branch,
            "repo": {"owner": owner, "name": name, "full_name": repo_name},
            "created_at": job_start_time,
        }
        current_state["status"] = JobStatus.RUNNING.value
        current_state["step_id"] = "clone"
        current_state["message"] = "Worker picked up analysis job"
        current_state["progress"] = max(current_state.get("progress", 0), 5)
        current_state["started_at"] = current_state.get("started_at") or job_start_time
        current_state["phase_started_at"] = job_start_time
        current_state["updated_at"] = job_start_time
        set_job_state(job_id, current_state)

        last_step_id = "clone"
        phase_start_time = job_start_time

        def _progress(update: Dict[str, Any]) -> None:
            nonlocal last_step_id, phase_start_time
            now = time.time()
            state = get_job_state(job_id) or current_state

            new_step_id = update.get("step_id") or state.get("step_id", "clone")
            if new_step_id != last_step_id:
                last_step_id = new_step_id
                phase_start_time = now

            job_elapsed = round(
                now - float(state.get("started_at") or job_start_time), 2
            )
            phase_elapsed = round(now - phase_start_time, 2)

            merged_stats = dict(state.get("stats", {}) or {})
            if "stats" in update and isinstance(update["stats"], dict):
                merged_stats.update(update["stats"])
            merged_stats["elapsed_seconds"] = job_elapsed
            merged_stats["job_elapsed_seconds"] = job_elapsed
            merged_stats["phase_elapsed_seconds"] = phase_elapsed

            state.update(update)
            state["step_id"] = new_step_id
            state["status"] = JobStatus.RUNNING.value
            state["started_at"] = state.get("started_at") or job_start_time
            state["phase_started_at"] = phase_start_time
            state["updated_at"] = now
            state["stats"] = merged_stats
            # Monotonic progress
            new_prog = update.get("progress", 0)
            old_prog = state.get("progress", 0)
            state["progress"] = max(old_prog, new_prog)

            set_job_state(job_id, state)

        try:
            result = execute_repository_analysis(
                repo_url=repo_url,
                branch=branch,
                force_rebuild=force_rebuild,
                progress_callback=_progress,
                request_id=request_id,
                job_id=job_id,
            )

            now = time.time()
            state = get_job_state(job_id) or current_state
            total_elapsed = round(
                now - float(state.get("started_at") or job_start_time), 2
            )
            final_stats = dict(state.get("stats", {}) or {})
            final_stats["elapsed_seconds"] = total_elapsed
            final_stats["job_elapsed_seconds"] = total_elapsed

            state["status"] = JobStatus.COMPLETED.value
            state["step_id"] = "complete"
            state["progress"] = 100
            state["message"] = "Analysis completed successfully"
            state["result"] = result
            state["completed_at"] = now
            state["updated_at"] = now
            state["stats"] = final_stats
            set_job_state(job_id, state)
            logger.info(
                "Worker successfully completed analysis for job=%s repo=%s elapsed=%.1fs",
                job_id,
                repo_name,
                total_elapsed,
            )
            return True

        except Exception as exc:
            logger.error(
                "Worker failed analysis for job=%s: %s", job_id, exc, exc_info=True
            )
            state = get_job_state(job_id) or current_state
            state["status"] = JobStatus.FAILED.value
            state["error"] = format_analysis_error(exc)
            state["completed_at"] = time.time()
            set_job_state(job_id, state)
            return False

    def run_once(self) -> bool:
        """Poll queue for one message, process it, and return True if a message was processed."""
        client = self._get_queue_client()

        # Handle Azure Storage Queue Client
        if hasattr(client, "receive_messages"):
            try:
                messages = client.receive_messages(
                    messages_per_page=1, visibility_timeout=3600
                )
                for msg in messages:
                    content = msg.content
                    print(
                        f"[Worker] Received Azure queue message {msg.id} (len={len(str(content))})",
                        flush=True,
                    )
                    if isinstance(content, bytes):
                        content = content.decode("utf-8")
                    self.process_message_payload(content)
                    try:
                        client.delete_message(msg)
                        print(
                            f"[Worker] Deleted Azure queue message {msg.id}", flush=True
                        )
                    except Exception as del_exc:
                        print(
                            f"[Worker] Warning: could not delete message {msg.id}: {del_exc}",
                            flush=True,
                        )
                        logger.warning(
                            "Could not delete message from queue: %s", del_exc
                        )
                    return True
            except Exception as rx_exc:
                print(
                    f"[Worker] Error receiving messages from queue: {rx_exc}",
                    flush=True,
                )
                logger.error(
                    "Error receiving messages from queue: %s", rx_exc, exc_info=True
                )

        # Handle MemoryQueueBackend
        elif hasattr(client, "receive_message"):
            msg_str = client.receive_message(timeout=1.0)
            if msg_str is not None:
                content_str = str(msg_str)
                print(
                    f"[Worker] Received memory queue message: {content_str[:50]}...",
                    flush=True,
                )
                return self.process_message_payload(content_str)
            return False

        return False

    def run_loop(self) -> None:
        """Continuous worker polling loop for container execution."""
        print(
            f"[Worker] Starting ARIA Analysis Worker loop (queue={self.queue_name})...",
            flush=True,
        )
        logger.info("Starting ARIA Analysis Worker loop (queue=%s)...", self.queue_name)
        while self._running:
            try:
                processed = self.run_once()
                if not processed:
                    time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                print("[Worker] Received interrupt, shutting down...", flush=True)
                logger.info("Worker received interrupt, shutting down...")
                break
            except Exception as exc:
                print(f"[Worker] Error in worker loop: {exc}", flush=True)
                logger.error("Error in worker loop: %s", exc, exc_info=True)
                time.sleep(self.poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ARIA Repository Analysis Background Worker"
    )
    parser.add_argument(
        "--run-once", action="store_true", help="Process at most one job and exit"
    )
    parser.add_argument("--queue", type=str, default=None, help="Target queue name")
    parser.add_argument(
        "--poll-interval", type=float, default=2.0, help="Polling interval in seconds"
    )
    parser.add_argument(
        "--memory-queue", action="store_true", help="Use in-memory queue for testing"
    )
    args = parser.parse_args()

    print(
        f"[Worker main] Launching ARIA worker (run_once={args.run_once}, queue={args.queue})...",
        flush=True,
    )

    worker = AnalysisWorker(
        queue_name=args.queue,
        use_memory_queue=args.memory_queue,
        poll_interval=args.poll_interval,
    )

    if args.run_once:
        processed = worker.run_once()
        print(
            f"[Worker main] Run-once completed (processed_job={processed})", flush=True
        )
    else:
        worker.run_loop()


if __name__ == "__main__":
    main()
