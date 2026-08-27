"""Unit tests verifying the stabilization fixes in v1.0."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from services.symbol_service import SymbolService
from services.architecture_service import ArchitectureService
from services.call_graph_service import CallGraphService
from services.git_history_service import GitHistoryService
from services.api_surface_service import APISurfaceService
from services.github_service import GitHubService, RepositoryNotFoundError
from services.embedding_service import EmbeddingService
from services.llm.gemini_provider import GeminiProvider


def test_schema_versions_public():
    """Verify that versioned services have public .schema_version and get_schema_version()."""
    services = [
        SymbolService,
        ArchitectureService,
        CallGraphService,
        GitHistoryService,
        APISurfaceService,
    ]
    for s_cls in services:
        # Check classmethod
        assert isinstance(s_cls.get_schema_version(), int)
        assert s_cls.get_schema_version() >= 0

        # Check property on instance
        inst = s_cls()
        assert isinstance(inst.schema_version, int)
        assert inst.schema_version == s_cls.get_schema_version()


def test_clone_inaccessible_repository_returns_generic_error():
    """Verify GitHubService raises a non-disclosing error when access fails."""
    service = GitHubService(token="test_token")

    with patch("services.github_service.run_safe_command") as mock_run:
        # Scenario: public check returns 1 (not public), check with PAT fails with permission denied
        mock_run.return_value = MagicMock(
            returncode=1, stderr="permission denied", stdout=""
        )

        with pytest.raises(RepositoryNotFoundError) as exc_info:
            service.clone_repository("https://github.com/owner/repo.git", branch="main")

        message = str(exc_info.value)
        assert message == "Repository not found or access denied."
        for leaked in (
            "PAT",
            "GITHUB_TOKEN",
            "Authentication failure",
            "permission denied",
        ):
            assert leaked not in message


def test_clone_branch_auto_discovery():
    """Verify GitHubService branch auto-discovery."""
    service = GitHubService(token="test_token")

    with patch("services.github_service.run_safe_command") as mock_run:
        # Scenario: branch auto-discovery
        # 1. ls-remote public: returncode=0 (public)
        # 2. ls-remote diagnostics: returncode=0 (connected)
        # 3. branch check: returncode=0, stdout="" (branch does not exist)
        # 4. branch auto-discovery: returncode=0, stdout="ref: refs/heads/master  HEAD"
        # 5. clone master branch: returncode=0 (cloned)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="HEAD"),  # public check
            MagicMock(returncode=0, stdout="HEAD"),  # diagnostics
            MagicMock(returncode=0, stdout=""),  # branch check (main missing)
            MagicMock(
                returncode=0, stdout="ref: refs/heads/master\tHEAD\n"
            ),  # branch discovery
            MagicMock(returncode=0, stdout=""),  # clone
        ]

        with patch("os.path.exists", return_value=False), patch("os.makedirs"):
            dest = service.clone_repository(
                "https://github.com/owner/repo.git", branch="main"
            )
            assert "owner_repo" in dest.replace("\\", "/")

        # Verify clone command used Master branch
        clone_call_args = mock_run.call_args_list[-1][0][0]
        assert "--branch" in clone_call_args
        assert "master" in clone_call_args


def test_sqlite_embedding_cache_and_deduplication():
    """Verify SQLite embedding cache reads, writes, and batch deduplication."""
    from services.embedding_service import _clear_l1_cache

    _clear_l1_cache()
    service = EmbeddingService(model_name="test-model")

    mock_model = MagicMock()
    import numpy as np

    mock_model.encode.return_value = np.array([[0.1] * 1536, [0.2] * 1536])

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk", return_value={}
        ),
        patch("services.embedding_service._get_cached_embedding", return_value=None),
        patch(
            "services.embedding_service._save_embeddings_to_cache_bulk"
        ) as mock_save_cache,
    ):
        texts = ["hello", "hello", "world"]
        embeddings = service.generate_embeddings_batch(texts)

        # 1. Assert local deduplication worked (encode called with only 2 unique items)
        mock_model.encode.assert_called_once()
        call_texts = mock_model.encode.call_args[0][0]
        assert len(call_texts) == 2
        assert "Represent this sentence: hello" in call_texts
        assert "Represent this sentence: world" in call_texts

        # 2. Assert results are mapped back correctly (len 3, first two identical)
        assert len(embeddings) == 3
        assert embeddings[0] == embeddings[1]
        assert embeddings[0] == [0.1] * 1536
        assert embeddings[2] == [0.2] * 1536

        # 3. Assert bulk save was called with the unique embeddings (deduplicated before write)
        mock_save_cache.assert_called_once()
        cached_records = mock_save_cache.call_args[0][0]
        assert len(cached_records) == 2

        # Verify chunk hashes are unique
        cached_hashes = [r["chunk_hash"] for r in cached_records]
        assert len(set(cached_hashes)) == 2

        # Verify both expected embeddings are present in the persisted records
        persisted_embeddings = [r["embedding"] for r in cached_records]
        assert [0.1] * 1536 in persisted_embeddings
        assert [0.2] * 1536 in persisted_embeddings


@pytest.mark.anyio
async def test_gemini_retry_and_timeout():
    """Verify GeminiProvider retry and timeout handling."""
    provider = GeminiProvider(api_key="dummy_key", model="dummy-model")

    # Mock client generate_content using AsyncMock
    mock_generate = AsyncMock()
    mock_generate.side_effect = [
        Exception("Transient API Error"),
        MagicMock(text="Mocked response text"),
    ]
    provider.client.aio.models.generate_content = mock_generate

    with patch("asyncio.sleep") as mock_sleep:
        res = await provider.generate("hello prompt")
        assert res == "Mocked response text"
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] >= 1.0


def test_startup_warmup_execution_development():
    """Verify that startup warmup runs embedding model and tree-sitter in non-production."""
    with (
        patch("backend.settings.settings.app_env", "development"),
        patch("services.embedding_service._get_model") as mock_embed_model,
        patch("services.tree_sitter_service.TreeSitterService") as mock_ts_service,
    ):
        # Mock BGE encode call
        mock_transformer = MagicMock()
        mock_embed_model.return_value = mock_transformer

        # Eager load uvicorn warmup
        from backend.api import _warmup_services

        _warmup_services()

        assert mock_embed_model.call_count >= 1
        mock_transformer.encode.assert_called_with(
            ["Represent this sentence: dummy text"], show_progress_bar=False
        )
        assert mock_ts_service.call_count >= 1


def test_startup_warmup_execution_production():
    """Verify that production startup skips eager embedding model warmup to conserve memory."""
    with (
        patch("backend.settings.settings.app_env", "production"),
        patch("services.embedding_service._get_model") as mock_embed_model,
        patch("services.tree_sitter_service.TreeSitterService") as mock_ts_service,
    ):
        from backend.api import _warmup_services

        _warmup_services()

        # Embedding model must NOT be loaded or encoded during production startup
        assert mock_embed_model.call_count == 0
        # Tree-sitter warmup should still execute
        assert mock_ts_service.call_count >= 1
