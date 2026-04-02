"""Tests for archivist service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from baml_py import ClientRegistry
from baml_py.baml_py import BamlClientError

from lexibrary.archivist.service import (
    ArchivistService,
    DesignFileRequest,
    DesignFileResult,
)
from lexibrary.baml_client.types import (
    DesignFileDependency,
    DesignFileOutput,
)
from lexibrary.exceptions import ArchivistTruncationError
from lexibrary.llm.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def rate_limiter() -> RateLimiter:
    """A rate limiter with high throughput for tests."""
    return RateLimiter(requests_per_minute=6000)


@pytest.fixture()
def client_registry() -> ClientRegistry:
    """A minimal client registry for tests."""
    registry = ClientRegistry()
    registry.add_llm_client(
        name="lexibrary-archivist",
        provider="anthropic",
        options={"model": "test-model", "api_key": "test-key", "max_tokens": 100},
    )
    registry.set_primary("lexibrary-archivist")
    return registry


@pytest.fixture()
def sample_design_file_output() -> DesignFileOutput:
    return DesignFileOutput(
        summary="Handles user authentication.",
        interface_contract="```python\ndef login(username: str, password: str) -> bool: ...\n```",
        dependencies=[
            DesignFileDependency(path="src/db.py", description="Database access"),
        ],
        tests="tests/test_auth.py",
        complexity_warning=None,
        wikilinks=["authentication", "session"],
        tags=["auth", "security"],
    )


@pytest.fixture()
def design_file_request() -> DesignFileRequest:
    return DesignFileRequest(
        source_path="src/auth.py",
        source_content="def login(): ...",
        interface_skeleton="def login(): ...",
        language="python",
        existing_design_file=None,
    )


# ---------------------------------------------------------------------------
# DesignFileRequest / DesignFileResult dataclass tests
# ---------------------------------------------------------------------------


class TestDesignFileRequest:
    """Verify DesignFileRequest field defaults and construction."""

    def test_code_file_request(self) -> None:
        req = DesignFileRequest(
            source_path="src/foo.py",
            source_content="class Foo: pass",
            interface_skeleton="class Foo: ...",
            language="python",
        )
        assert req.source_path == "src/foo.py"
        assert req.interface_skeleton == "class Foo: ..."
        assert req.language == "python"
        assert req.existing_design_file is None

    def test_non_code_file_request(self) -> None:
        req = DesignFileRequest(
            source_path="config.yaml",
            source_content="key: value",
        )
        assert req.interface_skeleton is None
        assert req.language is None


class TestDesignFileResult:
    """Verify DesignFileResult field defaults."""

    def test_successful_result(self, sample_design_file_output: DesignFileOutput) -> None:
        result = DesignFileResult(
            source_path="src/foo.py",
            design_file_output=sample_design_file_output,
        )
        assert result.error is False
        assert result.error_message is None
        assert result.design_file_output is not None

    def test_error_result(self) -> None:
        result = DesignFileResult(
            source_path="src/foo.py",
            error=True,
            error_message="API timeout",
        )
        assert result.error is True
        assert result.design_file_output is None


# ---------------------------------------------------------------------------
# ArchivistService — construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """Verify ArchivistService accepts client_registry."""

    def test_accepts_client_registry(
        self, rate_limiter: RateLimiter, client_registry: ClientRegistry
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)
        assert service._client_registry is client_registry
        assert service._rate_limiter is rate_limiter


# ---------------------------------------------------------------------------
# ArchivistService — generate_design_file
# ---------------------------------------------------------------------------


class TestGenerateDesignFile:
    """Verify generate_design_file with mocked BAML calls."""

    @pytest.mark.asyncio()
    async def test_successful_generation(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        design_file_request: DesignFileRequest,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(design_file_request)

        assert result.error is False
        assert result.source_path == "src/auth.py"
        assert result.design_file_output is not None
        assert result.design_file_output.summary == "Handles user authentication."

        mock_client.ArchivistGenerateDesignFile.assert_awaited_once_with(
            source_path="src/auth.py",
            source_content="def login(): ...",
            interface_skeleton="def login(): ...",
            language="python",
            existing_design_file=None,
            available_artifacts=None,
        )

    @pytest.mark.asyncio()
    async def test_error_returns_error_result(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        design_file_request: DesignFileRequest,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(
            side_effect=RuntimeError("API connection failed")
        )

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(design_file_request)

        assert result.error is True
        assert result.error_message is not None
        assert "API connection failed" in result.error_message
        assert result.design_file_output is None

    @pytest.mark.asyncio()
    async def test_non_code_file_request(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)
        request = DesignFileRequest(
            source_path="config.yaml",
            source_content="key: value",
        )

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        mock_client.ArchivistGenerateDesignFile.assert_awaited_once_with(
            source_path="config.yaml",
            source_content="key: value",
            interface_skeleton=None,
            language=None,
            existing_design_file=None,
            available_artifacts=None,
        )


# ---------------------------------------------------------------------------
# ArchivistService — rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Verify rate limiter is called before each BAML call."""

    @pytest.mark.asyncio()
    async def test_rate_limiter_acquired_before_design_file(
        self,
        client_registry: ClientRegistry,
        design_file_request: DesignFileRequest,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        mock_limiter = MagicMock(spec=RateLimiter)
        mock_limiter.acquire = AsyncMock()

        service = ArchivistService(rate_limiter=mock_limiter, client_registry=client_registry)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            await service.generate_design_file(design_file_request)

        mock_limiter.acquire.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_rate_limiter_acquired_even_on_error(
        self,
        client_registry: ClientRegistry,
        design_file_request: DesignFileRequest,
    ) -> None:
        mock_limiter = MagicMock(spec=RateLimiter)
        mock_limiter.acquire = AsyncMock()

        service = ArchivistService(rate_limiter=mock_limiter, client_registry=client_registry)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(side_effect=RuntimeError("fail"))

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(design_file_request)

        # Rate limiter was still called even though the LLM call failed
        mock_limiter.acquire.assert_awaited_once()
        assert result.error is True


# ---------------------------------------------------------------------------
# ArchivistService — client routing via registry
# ---------------------------------------------------------------------------


class TestClientRouting:
    """Verify that _get_baml_client uses the registry with the archivist client."""

    def test_routes_via_registry(
        self, rate_limiter: RateLimiter, client_registry: ClientRegistry
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        with patch("lexibrary.archivist.service.b") as mock_b:
            mock_b.with_options.return_value = mock_b
            service._get_baml_client()
            mock_b.with_options.assert_called_once_with(
                client_registry=client_registry,
                client="lexibrary-archivist",
            )


# ---------------------------------------------------------------------------
# DesignFileRequest — available_artifacts field
# ---------------------------------------------------------------------------


class TestDesignFileRequestAvailableArtifacts:
    """Verify available_artifacts field on DesignFileRequest."""

    def test_defaults_to_none(self) -> None:
        req = DesignFileRequest(
            source_path="src/foo.py",
            source_content="class Foo: pass",
        )
        assert req.available_artifacts is None

    def test_accepts_artifact_list(self) -> None:
        artifacts = ["Authentication", "Rate Limiting", "Caching"]
        req = DesignFileRequest(
            source_path="src/foo.py",
            source_content="class Foo: pass",
            available_artifacts=artifacts,
        )
        assert req.available_artifacts == artifacts

    def test_accepts_empty_list(self) -> None:
        req = DesignFileRequest(
            source_path="src/foo.py",
            source_content="class Foo: pass",
            available_artifacts=[],
        )
        assert req.available_artifacts == []


# ---------------------------------------------------------------------------
# ArchivistService — available_artifacts passed to BAML
# ---------------------------------------------------------------------------


class TestGenerateDesignFileWithArtifacts:
    """Verify available_artifacts is forwarded to the BAML call."""

    @pytest.mark.asyncio()
    async def test_artifacts_passed_to_baml(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        artifacts = ["Authentication", "Session Management"]
        request = DesignFileRequest(
            source_path="src/auth.py",
            source_content="def login(): ...",
            available_artifacts=artifacts,
        )

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        mock_client.ArchivistGenerateDesignFile.assert_awaited_once_with(
            source_path="src/auth.py",
            source_content="def login(): ...",
            interface_skeleton=None,
            language=None,
            existing_design_file=None,
            available_artifacts=artifacts,
        )

    @pytest.mark.asyncio()
    async def test_none_artifacts_passed_to_baml(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        request = DesignFileRequest(
            source_path="src/auth.py",
            source_content="def login(): ...",
        )

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        mock_client.ArchivistGenerateDesignFile.assert_awaited_once_with(
            source_path="src/auth.py",
            source_content="def login(): ...",
            interface_skeleton=None,
            language=None,
            existing_design_file=None,
            available_artifacts=None,
        )


# ---------------------------------------------------------------------------
# ArchivistService — truncation detection
# ---------------------------------------------------------------------------


class TestTruncationDetection:
    """Verify that BamlClientError with truncation indicators raises ArchivistTruncationError."""

    @pytest.mark.asyncio()
    async def test_stop_reason_length_raises_truncation_error(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        design_file_request: DesignFileRequest,
    ) -> None:
        """stop_reason: length raises ArchivistTruncationError."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(
            side_effect=BamlClientError("stop_reason: length - output truncated")
        )

        with (
            patch.object(service, "_get_baml_client", return_value=mock_client),
            pytest.raises(ArchivistTruncationError, match="truncated"),
        ):
            await service.generate_design_file(design_file_request)

    @pytest.mark.asyncio()
    async def test_finish_reason_length_raises_truncation_error(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        design_file_request: DesignFileRequest,
    ) -> None:
        """finish_reason: length raises ArchivistTruncationError."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(
            side_effect=BamlClientError("finish_reason: length")
        )

        with (
            patch.object(service, "_get_baml_client", return_value=mock_client),
            pytest.raises(ArchivistTruncationError),
        ):
            await service.generate_design_file(design_file_request)

    @pytest.mark.asyncio()
    async def test_max_tokens_raises_truncation_error(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        design_file_request: DesignFileRequest,
    ) -> None:
        """A BamlClientError mentioning max_tokens should raise ArchivistTruncationError."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(
            side_effect=BamlClientError("exceeded max_tokens limit")
        )

        with (
            patch.object(service, "_get_baml_client", return_value=mock_client),
            pytest.raises(ArchivistTruncationError),
        ):
            await service.generate_design_file(design_file_request)

    @pytest.mark.asyncio()
    async def test_non_truncation_baml_error_returns_error_result(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        design_file_request: DesignFileRequest,
    ) -> None:
        """Non-truncation BamlClientError returns error result, not raise."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(
            side_effect=BamlClientError("authentication failed: invalid API key")
        )

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(design_file_request)

        assert result.error is True
        assert result.error_message is not None
        assert "authentication failed" in result.error_message

    @pytest.mark.asyncio()
    async def test_non_baml_error_unchanged(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        design_file_request: DesignFileRequest,
    ) -> None:
        """A generic exception (not BamlClientError) should still return an error result."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(
            side_effect=RuntimeError("connection reset")
        )

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(design_file_request)

        assert result.error is True
        assert "connection reset" in result.error_message
