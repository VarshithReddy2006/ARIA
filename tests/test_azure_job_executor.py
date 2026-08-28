"""Unit and integration tests for Azure migration and JobExecutor abstraction."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.job_state import JobStatus
from infrastructure.job_executor import (
    AzureJobExecutor,
    LocalJobExecutor,
    MemoryQueueBackend,
    ModalJobExecutor,
    get_job_executor,
    get_shared_local_queue,
)
from backend.worker import AnalysisWorker


# ---------------------------------------------------------------------------
# 1. JobExecutor Factory & Selection
# ---------------------------------------------------------------------------
class TestJobExecutorFactory:
    def test_default_executor_is_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("JOB_EXECUTOR", raising=False)
        executor = get_job_executor()
        assert isinstance(executor, LocalJobExecutor)

    def test_select_local_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JOB_EXECUTOR", "local")
        executor = get_job_executor()
        assert isinstance(executor, LocalJobExecutor)

    def test_select_modal_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JOB_EXECUTOR", "modal")
        executor = get_job_executor()
        assert isinstance(executor, ModalJobExecutor)

    def test_select_azure_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JOB_EXECUTOR", "azure")
        executor = get_job_executor()
        assert isinstance(executor, AzureJobExecutor)

    def test_invalid_executor_raises_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JOB_EXECUTOR", "unsupported_cloud")
        with pytest.raises(
            ValueError, match="Unknown JOB_EXECUTOR 'unsupported_cloud'"
        ):
            get_job_executor()


# ---------------------------------------------------------------------------
# 2. AzureJobExecutor & Queue Serialization
# ---------------------------------------------------------------------------
class TestAzureJobExecutor:
    def test_serialize_payload_preserves_ids_and_flags(self) -> None:
        executor = AzureJobExecutor(use_memory_queue=True)
        raw = executor.serialize_payload(
            job_id="job-123",
            repo_url="https://github.com/acme/widget",
            branch="feature-x",
            force_rebuild=True,
            request_id="req-999",
        )
        data = json.loads(raw)
        assert data["job_id"] == "job-123"
        assert data["request_id"] == "req-999"
        assert data["repo_url"] == "https://github.com/acme/widget"
        assert data["branch"] == "feature-x"
        assert data["force_rebuild"] is True
        assert "enqueued_at" in data

    def test_serialize_payload_defaults_request_id_to_job_id(self) -> None:
        executor = AzureJobExecutor(use_memory_queue=True)
        raw = executor.serialize_payload(
            job_id="job-abc",
            repo_url="https://github.com/acme/widget",
        )
        data = json.loads(raw)
        assert data["request_id"] == "job-abc"
        assert data["branch"] == "main"
        assert data["force_rebuild"] is False

    def test_spawn_analysis_enqueues_to_memory_queue(self) -> None:
        mock_queue = MemoryQueueBackend()
        executor = AzureJobExecutor(queue_client=mock_queue)

        dispatched = executor.spawn_analysis(
            job_id="test-job-42",
            repo_url="https://github.com/test/repo",
            branch="main",
            request_id="req-42",
        )
        assert dispatched is True
        assert mock_queue.qsize() == 1

        msg = mock_queue.receive_message()
        assert msg is not None
        payload = json.loads(msg)
        assert payload["job_id"] == "test-job-42"
        assert payload["request_id"] == "req-42"

    def test_missing_azure_credentials_raises_explicit_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
        monkeypatch.delenv("AZURE_USE_MEMORY_QUEUE", raising=False)
        executor = AzureJobExecutor()
        with pytest.raises(
            RuntimeError, match="AZURE_STORAGE_CONNECTION_STRING is not configured"
        ):
            executor.spawn_analysis("job-1", "https://github.com/test/repo")


# ---------------------------------------------------------------------------
# 3. ModalJobExecutor Regression
# ---------------------------------------------------------------------------
class TestModalJobExecutor:
    def test_modal_spawn_invokes_modal_function(self) -> None:
        mock_spawn = MagicMock()
        mock_modal_app = MagicMock()
        mock_modal_app.run_analysis_job.spawn = mock_spawn

        with patch.dict("sys.modules", {"modal_app": mock_modal_app}):
            executor = ModalJobExecutor()
            dispatched = executor.spawn_analysis(
                job_id="modal-job-1",
                repo_url="https://github.com/modal/test",
                branch="main",
                force_rebuild=False,
                request_id="modal-req-1",
            )
            assert dispatched is True
            mock_spawn.assert_called_once_with(
                repo_url="https://github.com/modal/test",
                branch="main",
                force_rebuild=False,
                request_id="modal-req-1",
                job_id="modal-job-1",
            )


# ---------------------------------------------------------------------------
# 4. AnalysisWorker Execution & State Lifecycle
# ---------------------------------------------------------------------------
class TestAnalysisWorker:
    def test_worker_success_lifecycle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_queue = MemoryQueueBackend()
        worker = AnalysisWorker(use_memory_queue=True)
        worker._get_queue_client = lambda: mock_queue

        # Enqueue job
        payload = {
            "job_id": "job-worker-success",
            "request_id": "req-worker-success",
            "repo_url": "https://github.com/owner/success-repo",
            "branch": "main",
            "force_rebuild": False,
        }
        mock_queue.send_message(json.dumps(payload))

        fake_analysis_result = {
            "status": "completed",
            "repo": "owner/success-repo",
            "summary": "all good",
        }

        with patch(
            "backend.worker.execute_repository_analysis",
            return_value=fake_analysis_result,
        ) as mock_exec:
            processed = worker.run_once()
            assert processed is True
            mock_exec.assert_called_once()

            from backend.routers.repositories import get_job_state

            state = get_job_state("job-worker-success")
            assert state is not None
            assert state["status"] == JobStatus.COMPLETED.value
            assert state["progress"] == 100
            assert state["result"] == fake_analysis_result
            assert "completed_at" in state

    def test_worker_failure_lifecycle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_queue = MemoryQueueBackend()
        worker = AnalysisWorker(use_memory_queue=True)
        worker._get_queue_client = lambda: mock_queue

        payload = {
            "job_id": "job-worker-fail",
            "request_id": "req-worker-fail",
            "repo_url": "https://github.com/owner/fail-repo",
            "branch": "main",
            "force_rebuild": False,
        }
        mock_queue.send_message(json.dumps(payload))

        with patch(
            "backend.worker.execute_repository_analysis",
            side_effect=RuntimeError("Simulated pipeline error"),
        ):
            processed = worker.run_once()
            assert processed is False

            from backend.routers.repositories import get_job_state

            state = get_job_state("job-worker-fail")
            assert state is not None
            assert state["status"] == JobStatus.FAILED.value
            assert "error" in state
            assert "completed_at" in state

    def test_worker_empty_queue_returns_false(self) -> None:
        mock_queue = MemoryQueueBackend()
        worker = AnalysisWorker(use_memory_queue=True)
        worker._get_queue_client = lambda: mock_queue
        assert worker.run_once() is False


# ---------------------------------------------------------------------------
# 5. API Dispatch Integration & No Duplicate Active Jobs
# ---------------------------------------------------------------------------
class TestApiJobDispatch:
    def test_api_dispatches_via_configured_executor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fastapi.testclient import TestClient
        from backend.api import app

        mock_queue = get_shared_local_queue()
        # Drain any existing messages
        while not mock_queue.empty():
            mock_queue.receive_message()

        monkeypatch.setenv("JOB_EXECUTOR", "azure")
        monkeypatch.setenv("AZURE_USE_MEMORY_QUEUE", "1")

        client = TestClient(app)
        res = client.post(
            "/api/v1/analyze",
            json={"url": "https://github.com/test-org/test-dispatch", "branch": "main"},
        )
        assert res.status_code == 202
        body = res.json()
        assert "job_id" in body
        assert body["status"] == "queued"
        assert mock_queue.qsize() == 1

        msg = mock_queue.receive_message()
        assert msg is not None
        payload = json.loads(msg)
        assert payload["job_id"] == body["job_id"]
        assert payload["repo_url"] == "https://github.com/test-org/test-dispatch"

    def test_api_returns_existing_job_when_active_and_no_force_rebuild(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fastapi.testclient import TestClient
        from backend.api import app
        from backend.routers.repositories import set_job_state

        client = TestClient(app)
        job_id = "existing-active-job"
        set_job_state(
            job_id,
            {
                "job_id": job_id,
                "request_id": "req-existing",
                "repo_url": "https://github.com/active/project",
                "status": "running",
                "repo": {
                    "owner": "active",
                    "name": "project",
                    "full_name": "active/project",
                },
            },
        )

        res = client.post(
            "/api/v1/analyze",
            json={"url": "https://github.com/active/project", "force_rebuild": False},
        )
        assert res.status_code == 202
        body = res.json()
        assert body["job_id"] == job_id
        assert body["status"] == "running"


# ---------------------------------------------------------------------------
# 6. Worker Container & Azure Job Deployment Configuration
# ---------------------------------------------------------------------------
class TestWorkerDeploymentConfiguration:
    def test_dockerfile_worker_cmd_is_one_shot(self) -> None:
        """Verify Dockerfile.worker explicitly defines one-shot execution by default."""
        import os

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dockerfile_path = os.path.join(root_dir, "Dockerfile.worker")
        assert os.path.exists(dockerfile_path), (
            "Dockerfile.worker must exist in project root"
        )

        with open(dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()

        expected_cmd = 'CMD ["python", "-u", "-m", "backend.worker", "--run-once"]'
        assert expected_cmd in content, (
            f"Dockerfile.worker must set '{expected_cmd}' for Azure Container Apps Job execution"
        )

    def test_container_apps_job_yaml_preserves_constraints_and_relies_on_image_cmd(
        self,
    ) -> None:
        """Verify azure/container-apps-job.yaml preserves resource constraints, ACR registry, and inherits image CMD."""
        import os
        import yaml

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        job_yaml_path = os.path.join(root_dir, "azure", "container-apps-job.yaml")
        assert os.path.exists(job_yaml_path), "azure/container-apps-job.yaml must exist"

        with open(job_yaml_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)

        props = doc["properties"]
        config = props["configuration"]
        assert config["triggerType"] == "Event"
        assert config["replicaTimeout"] == 3600
        assert config["replicaRetryLimit"] == 3

        rules = config["eventTriggerConfig"]["scale"]["rules"]
        assert len(rules) >= 1
        assert rules[0]["type"] == "azure-queue"
        assert rules[0]["metadata"]["queueName"] == "aria-analysis-jobs"
        assert rules[0]["auth"][0]["secretRef"] == "storage-conn"
        assert rules[0]["auth"][0]["triggerParameter"] == "connection"

        assert config["eventTriggerConfig"]["parallelism"] == 1
        assert config["eventTriggerConfig"]["replicaCompletionCount"] == 1

        # 1. Verify ACR registry and matching passwordSecretRef
        assert "registries" in config, "configuration.registries must be defined"
        assert len(config["registries"]) == 1
        reg = config["registries"][0]
        assert reg["server"] == "ariacr3ab8.azurecr.io"
        assert reg["username"] == "ariacr3ab8"
        assert reg["passwordSecretRef"] == "ariacr3ab8azurecrio-ariacr3ab8"

        # 2. Verify referenced secret names in configuration.secrets with placeholder values
        secrets_dict = {s["name"]: s.get("value") for s in config.get("secrets", [])}
        assert reg["passwordSecretRef"] in secrets_dict
        assert secrets_dict["storage-conn"] == "<AZURE_STORAGE_CONNECTION_STRING>"
        assert secrets_dict["gemini-key"] == "<GEMINI_API_KEY>"
        assert secrets_dict["ariacr3ab8azurecrio-ariacr3ab8"] == "<ACR_PASSWORD>"

        # 3. Verify Azure File volume
        template = props["template"]
        assert len(template["volumes"]) >= 1
        assert template["volumes"][0]["name"] == "aria-data-volume"
        assert template["volumes"][0]["storageType"] == "AzureFile"
        assert template["volumes"][0]["storageName"] == "ariadata"

        # 4. Verify container image placeholder and resources
        container = template["containers"][0]
        assert container["name"] == "aria-worker"
        assert container["image"] == "ariacr3ab8.azurecr.io/aria-worker:<IMAGE_TAG>"
        assert container["resources"]["cpu"] in (2.0, "2.0", 2)
        assert container["resources"]["memory"] in ("4.0Gi", "4Gi")

        # Command / args should not override container defaults with malformed strings
        assert "command" not in container or container["command"] is None
        assert "args" not in container or container["args"] is None

        # Verify volume mount
        assert len(container["volumeMounts"]) >= 1
        assert container["volumeMounts"][0]["volumeName"] == "aria-data-volume"
        assert container["volumeMounts"][0]["mountPath"] == "/app/data"

        # Verify environment variables
        env_dict = {
            e["name"]: e.get("value") or e.get("secretRef")
            for e in container.get("env", [])
        }
        assert env_dict.get("AZURE_STORAGE_QUEUE_NAME") == "aria-analysis-jobs"
        assert env_dict.get("AZURE_STORAGE_CONNECTION_STRING") == "storage-conn"
        assert env_dict.get("GEMINI_API_KEY") == "gemini-key"
        assert env_dict.get("SQLITE_DB_PATH") == "/tmp/repo_understanding.db"
        assert env_dict.get("ANALYSIS_STORE_PATH") == "/app/data/analysis_store.json"
        assert env_dict.get("APP_ENV") == "production"
        assert (
            env_dict.get("ALLOWED_HOSTS")
            == "aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io"
        )
        assert env_dict.get("JOB_STATE_DIR") == "/app/data/jobs"

    def test_canonical_yaml_structural_consistency_with_live_worker_job(
        self,
    ) -> None:
        """Verify canonical YAML has ACR registry, secret references, volumes, mounts, and image tag placeholders."""
        import os
        import yaml

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        job_yaml_path = os.path.join(root_dir, "azure", "container-apps-job.yaml")
        assert os.path.exists(job_yaml_path), "azure/container-apps-job.yaml must exist"

        with open(job_yaml_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)

        config = doc["properties"]["configuration"]

        # 1. ACR registry and matching passwordSecretRef
        assert "registries" in config
        reg = config["registries"][0]
        assert reg["server"] == "ariacr3ab8.azurecr.io"
        assert reg["username"] == "ariacr3ab8"
        assert reg["passwordSecretRef"] == "ariacr3ab8azurecrio-ariacr3ab8"

        # 2. Secret names present in configuration.secrets
        secret_names = [s["name"] for s in config["secrets"]]
        assert "storage-conn" in secret_names
        assert "gemini-key" in secret_names
        assert "ariacr3ab8azurecrio-ariacr3ab8" in secret_names
        assert reg["passwordSecretRef"] in secret_names

        # 3. Azure File volume and mount
        volumes = doc["properties"]["template"]["volumes"]
        assert any(
            v["name"] == "aria-data-volume"
            and v["storageType"] == "AzureFile"
            and v["storageName"] == "ariadata"
            for v in volumes
        )
        container = doc["properties"]["template"]["containers"][0]
        assert any(
            m["volumeName"] == "aria-data-volume" and m["mountPath"] == "/app/data"
            for m in container["volumeMounts"]
        )

        # 4. Image uses <IMAGE_TAG>
        assert container["image"] == "ariacr3ab8.azurecr.io/aria-worker:<IMAGE_TAG>"

        # 5. Resource constraints
        assert container["resources"]["cpu"] in (2.0, "2.0", 2)
        assert container["resources"]["memory"] in ("4.0Gi", "4Gi")

    def test_api_and_worker_share_identical_azure_file_storage_volume_and_mount(
        self,
    ) -> None:
        """Verify aria-api and aria-worker-job use the identical Azure File volume and mount path."""
        import os
        import yaml

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        api_yaml_path = os.path.join(root_dir, "azure", "container-apps-api.yaml")
        job_yaml_path = os.path.join(root_dir, "azure", "container-apps-job.yaml")

        assert os.path.exists(api_yaml_path), "container-apps-api.yaml must exist"
        assert os.path.exists(job_yaml_path), "container-apps-job.yaml must exist"

        with open(api_yaml_path, "r", encoding="utf-8") as f:
            api_doc = yaml.safe_load(f)
        with open(job_yaml_path, "r", encoding="utf-8") as f:
            job_doc = yaml.safe_load(f)

        # Volumes on both manifests
        api_vol = api_doc["properties"]["template"]["volumes"][0]
        job_vol = job_doc["properties"]["template"]["volumes"][0]

        assert api_vol["name"] == "aria-data-volume"
        assert job_vol["name"] == "aria-data-volume"
        assert api_vol["storageType"] == "AzureFile"
        assert job_vol["storageType"] == "AzureFile"
        assert api_vol["storageName"] == "ariadata"
        assert job_vol["storageName"] == "ariadata"

        # Volume mounts on both containers
        api_mount = api_doc["properties"]["template"]["containers"][0]["volumeMounts"][
            0
        ]
        job_mount = job_doc["properties"]["template"]["containers"][0]["volumeMounts"][
            0
        ]

        assert api_mount["volumeName"] == "aria-data-volume"
        assert job_mount["volumeName"] == "aria-data-volume"
        assert api_mount["mountPath"] == "/app/data"
        assert job_mount["mountPath"] == "/app/data"

        # Environment storage paths must match identically
        api_env = {
            e["name"]: e.get("value")
            for e in api_doc["properties"]["template"]["containers"][0].get("env", [])
        }
        job_env = {
            e["name"]: e.get("value")
            for e in job_doc["properties"]["template"]["containers"][0].get("env", [])
        }

        for path_key in ("SQLITE_DB_PATH", "ANALYSIS_STORE_PATH", "JOB_STATE_DIR"):
            assert api_env.get(path_key) == job_env.get(path_key), (
                f"Mismatch for {path_key}: API={api_env.get(path_key)} vs Job={job_env.get(path_key)}"
            )

    def test_deployment_scripts_declare_shared_azure_file_volume(self) -> None:
        """Verify PowerShell deployment scripts construct manifests with aria-data-volume mount and matching registry secrets."""
        import os

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p2_script = os.path.join(
            root_dir, "azure", "scripts", "deploy-worker-phase2.ps1"
        )
        mesh_script = os.path.join(
            root_dir, "azure", "scripts", "deploy-production-mesh.ps1"
        )
        api_p2_script = os.path.join(
            root_dir, "azure", "scripts", "deploy-api-phase2.ps1"
        )

        for script_path in (p2_script, mesh_script, api_p2_script):
            assert os.path.exists(script_path), f"{script_path} must exist"
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read()

            assert "name: aria-data-volume" in content
            assert "storageType: AzureFile" in content
            assert "storageName: ariadata" in content
            assert "volumeName: aria-data-volume" in content
            assert "mountPath: /app/data" in content
            assert (
                "passwordSecretRef: $($RegistryName)azurecrio-$RegistryName" in content
            )

    def test_worker_main_cli_run_once_dispatch(self) -> None:
        """Verify backend.worker.main dispatches to run_once when --run-once flag is passed."""
        import sys
        from backend.worker import main

        with (
            patch.object(
                sys, "argv", ["backend.worker", "--run-once", "--memory-queue"]
            ),
            patch("backend.worker.AnalysisWorker") as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_instance.run_once.return_value = True
            mock_worker_cls.return_value = mock_instance

            main()

            mock_worker_cls.assert_called_once()
            mock_instance.run_once.assert_called_once()
            mock_instance.run_loop.assert_not_called()

    def test_worker_main_cli_default_run_loop(self) -> None:
        """Verify backend.worker.main dispatches to run_loop when no flags are passed."""
        import sys
        from backend.worker import main

        with (
            patch.object(sys, "argv", ["backend.worker", "--memory-queue"]),
            patch("backend.worker.AnalysisWorker") as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance

            main()

            mock_worker_cls.assert_called_once()
            mock_instance.run_loop.assert_called_once()
            mock_instance.run_once.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Option C: Local SQLite + Shared Azure File Artifacts
# ---------------------------------------------------------------------------
class TestOptionCProductionArchitecture:
    """Validate Option C production architecture separating local SQLite from shared Azure File artifacts."""

    def test_production_config_resolves_container_local_sqlite_path(
        self, monkeypatch
    ) -> None:
        """Verify production configuration resolves SQLITE_DB_PATH to /tmp/repo_understanding.db."""
        from core.config import Settings

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder-key")
        monkeypatch.setenv("ALLOWED_HOSTS", '["api.test.local"]')
        monkeypatch.delenv("SQLITE_DB_PATH", raising=False)

        prod_settings = Settings()
        assert prod_settings.sqlite_db_path == "/tmp/repo_understanding.db"

        # Explicit /app/data passed in is normalized to /tmp for safety
        normalized_settings = Settings(
            SQLITE_DB_PATH="/app/data/repo_understanding.db",
        )
        assert normalized_settings.sqlite_db_path == "/tmp/repo_understanding.db"

    def test_azure_manifests_declare_local_sqlite_and_shared_data_mount(
        self,
    ) -> None:
        """Verify Azure Container Apps API and Job manifests configure local SQLite and mount Azure File."""
        import os
        import yaml

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        api_yaml_path = os.path.join(root_dir, "azure", "container-apps-api.yaml")
        job_yaml_path = os.path.join(root_dir, "azure", "container-apps-job.yaml")

        with open(api_yaml_path, "r", encoding="utf-8") as f:
            api_doc = yaml.safe_load(f)
        with open(job_yaml_path, "r", encoding="utf-8") as f:
            job_doc = yaml.safe_load(f)

        for name, doc in [("API", api_doc), ("Job", job_doc)]:
            container = doc["properties"]["template"]["containers"][0]
            env_map = {
                e["name"]: e.get("value") or e.get("secretRef")
                for e in container.get("env", [])
            }
            assert env_map.get("SQLITE_DB_PATH") == "/tmp/repo_understanding.db", (
                f"{name} manifest must set SQLITE_DB_PATH to /tmp/repo_understanding.db"
            )
            assert env_map.get("ANALYSIS_STORE_PATH") == (
                "/app/data/analysis_store.json"
            )
            assert env_map.get("JOB_STATE_DIR") == "/app/data/jobs"

            # Both still mount aria-data-volume to /app/data
            volumes = doc["properties"]["template"]["volumes"]
            assert any(
                v["name"] == "aria-data-volume"
                and v["storageType"] == "AzureFile"
                and v["storageName"] == "ariadata"
                for v in volumes
            ), f"{name} must declare aria-data-volume"
            mounts = container["volumeMounts"]
            assert any(
                m["volumeName"] == "aria-data-volume" and m["mountPath"] == "/app/data"
                for m in mounts
            ), f"{name} must mount aria-data-volume at /app/data"

    def test_deployment_scripts_declare_local_sqlite_path(self) -> None:
        """Verify PowerShell deployment scripts configure SQLITE_DB_PATH as /tmp and not /app/data."""
        import os

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        scripts = [
            os.path.join(root_dir, "azure", "scripts", "deploy-api-phase2.ps1"),
            os.path.join(root_dir, "azure", "scripts", "deploy-worker-phase2.ps1"),
            os.path.join(root_dir, "azure", "scripts", "deploy-production-mesh.ps1"),
        ]

        for s in scripts:
            assert os.path.exists(s), f"{s} must exist"
            with open(s, "r", encoding="utf-8") as fh:
                content = fh.read()
            assert "value: /tmp/repo_understanding.db" in content
            assert "value: /app/data/repo_understanding.db" not in content

    def test_report_summary_resolves_from_shared_json_artifact(
        self, tmp_path, monkeypatch
    ) -> None:
        """Verify get_report_summary retrieves health score and grade from shared reports JSON artifact without SQLite."""
        import json
        from backend.routers.report import get_report_summary
        from core.config import settings

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        store_file = tmp_path / "analysis_store.json"
        store_file.write_text("{}", encoding="utf-8")

        monkeypatch.setenv("ANALYSIS_STORE_PATH", str(store_file))
        monkeypatch.setattr(
            settings, "analysis_store_path", str(store_file), raising=False
        )

        # Write a mock report JSON artifact
        report_data = {
            "metadata": {
                "repo_name": "acme/shared-test",
                "generated_at": "2026-08-28T12:00:00Z",
            },
            "scores": {
                "overall": 94.5,
                "grade": "A",
            },
        }
        report_file = reports_dir / "acme_shared-test.json"
        report_file.write_text(json.dumps(report_data), encoding="utf-8")

        summary = get_report_summary("acme", "shared-test")
        assert summary["repo_name"] == "acme/shared-test"
        assert summary["score"] == 94.5
        assert summary["grade"] == "A"
        assert summary["analyzed_at"] == "2026-08-28T12:00:00Z"

    def test_embedding_cache_operates_as_local_optimization(
        self, tmp_path, monkeypatch
    ) -> None:
        """Verify EmbeddingService generates embeddings correctly even when SQLite cache is cold or cleared."""
        from services.embedding_service import EmbeddingService
        from core.config import settings

        temp_db = tmp_path / "local_cache.db"
        monkeypatch.setattr(settings, "sqlite_db_path", str(temp_db))

        service = EmbeddingService(model_name="test-local-opt")
        emb = service.generate_embedding("def calculate_tax(amount): pass")
        assert isinstance(emb, list)
        assert len(emb) > 0

        # Clearing cache doesn't prevent subsequent generations
        service.clear_cache(clear_disk=True)
        emb2 = service.generate_embedding("def calculate_tax(amount): pass")
        assert isinstance(emb2, list)
        assert len(emb2) == len(emb)
