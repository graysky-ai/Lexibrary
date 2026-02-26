"""Tests for archivist service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexibrary.archivist.service import (
    _PROVIDER_CLIENT_MAP,
    ArchivistService,
    DesignFileRequest,
    DesignFileResult,
)
from lexibrary.baml_client.types import (
    DesignFileDependency,
    DesignFileOutput,
)
from lexibrary.config.schema import LLMConfig
from lexibrary.llm.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def rate_limiter() -> RateLimiter:
    """A rate limiter with high throughput for tests."""
    return RateLimiter(requests_per_minute=6000)


@pytest.fixture()
def anthropic_config() -> LLMConfig:
    return LLMConfig(provider="anthropic")


@pytest.fixture()
def openai_config() -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-5-mini", api_key_env="OPENAI_API_KEY")


@pytest.fixture()
def unknown_config() -> LLMConfig:
    return LLMConfig(provider="ollama", model="llama3", api_key_env="")


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
# ArchivistService — provider routing
# ---------------------------------------------------------------------------


class TestProviderRouting:
    """Verify BAML client selection based on LLMConfig.provider."""

    def test_anthropic_client_selected(
        self, rate_limiter: RateLimiter, anthropic_config: LLMConfig
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=anthropic_config)
        assert service._client_name == "AnthropicArchivist"

    def test_openai_client_selected(
        self, rate_limiter: RateLimiter, openai_config: LLMConfig
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=openai_config)
        assert service._client_name == "OpenAIArchivist"

    def test_unknown_provider_falls_back(
        self, rate_limiter: RateLimiter, unknown_config: LLMConfig
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=unknown_config)
        assert service._client_name is None

    def test_provider_client_map_covers_expected_providers(self) -> None:
        assert "anthropic" in _PROVIDER_CLIENT_MAP
        assert "openai" in _PROVIDER_CLIENT_MAP


# ---------------------------------------------------------------------------
# ArchivistService — generate_design_file
# ---------------------------------------------------------------------------


class TestGenerateDesignFile:
    """Verify generate_design_file with mocked BAML calls."""

    @pytest.mark.asyncio()
    async def test_successful_generation(
        self,
        rate_limiter: RateLimiter,
        anthropic_config: LLMConfig,
        design_file_request: DesignFileRequest,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=anthropic_config)

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
            available_concepts=None,
        )

    @pytest.mark.asyncio()
    async def test_error_returns_error_result(
        self,
        rate_limiter: RateLimiter,
        anthropic_config: LLMConfig,
        design_file_request: DesignFileRequest,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=anthropic_config)

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
        anthropic_config: LLMConfig,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=anthropic_config)
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
            available_concepts=None,
        )


# ---------------------------------------------------------------------------
# ArchivistService — rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Verify rate limiter is called before each BAML call."""

    @pytest.mark.asyncio()
    async def test_rate_limiter_acquired_before_design_file(
        self,
        anthropic_config: LLMConfig,
        design_file_request: DesignFileRequest,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        mock_limiter = MagicMock(spec=RateLimiter)
        mock_limiter.acquire = AsyncMock()

        service = ArchivistService(rate_limiter=mock_limiter, config=anthropic_config)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            await service.generate_design_file(design_file_request)

        mock_limiter.acquire.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_rate_limiter_acquired_even_on_error(
        self,
        anthropic_config: LLMConfig,
        design_file_request: DesignFileRequest,
    ) -> None:
        mock_limiter = MagicMock(spec=RateLimiter)
        mock_limiter.acquire = AsyncMock()

        service = ArchivistService(rate_limiter=mock_limiter, config=anthropic_config)

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(side_effect=RuntimeError("fail"))

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(design_file_request)

        # Rate limiter was still called even though the LLM call failed
        mock_limiter.acquire.assert_awaited_once()
        assert result.error is True


# ---------------------------------------------------------------------------
# ArchivistService — client routing integration
# ---------------------------------------------------------------------------


class TestClientRouting:
    """Verify that _get_baml_client routes to correct provider."""

    def test_anthropic_routes_to_with_options(
        self, rate_limiter: RateLimiter, anthropic_config: LLMConfig
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=anthropic_config)

        with patch("lexibrary.archivist.service.b") as mock_b:
            mock_b.with_options.return_value = mock_b
            service._get_baml_client()
            mock_b.with_options.assert_called_once_with(client="AnthropicArchivist")

    def test_openai_routes_to_with_options(
        self, rate_limiter: RateLimiter, openai_config: LLMConfig
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=openai_config)

        with patch("lexibrary.archivist.service.b") as mock_b:
            mock_b.with_options.return_value = mock_b
            service._get_baml_client()
            mock_b.with_options.assert_called_once_with(client="OpenAIArchivist")

    def test_unknown_provider_returns_default_client(
        self, rate_limiter: RateLimiter, unknown_config: LLMConfig
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=unknown_config)

        with patch("lexibrary.archivist.service.b") as mock_b:
            result = service._get_baml_client()
            mock_b.with_options.assert_not_called()
            assert result is mock_b


# ---------------------------------------------------------------------------
# DesignFileRequest — available_concepts field
# ---------------------------------------------------------------------------


class TestDesignFileRequestAvailableConcepts:
    """Verify available_concepts field on DesignFileRequest."""

    def test_defaults_to_none(self) -> None:
        req = DesignFileRequest(
            source_path="src/foo.py",
            source_content="class Foo: pass",
        )
        assert req.available_concepts is None

    def test_accepts_concept_list(self) -> None:
        concepts = ["Authentication", "Rate Limiting", "Caching"]
        req = DesignFileRequest(
            source_path="src/foo.py",
            source_content="class Foo: pass",
            available_concepts=concepts,
        )
        assert req.available_concepts == concepts

    def test_accepts_empty_list(self) -> None:
        req = DesignFileRequest(
            source_path="src/foo.py",
            source_content="class Foo: pass",
            available_concepts=[],
        )
        assert req.available_concepts == []


# ---------------------------------------------------------------------------
# ArchivistService — available_concepts passed to BAML
# ---------------------------------------------------------------------------


class TestGenerateDesignFileWithConcepts:
    """Verify available_concepts is forwarded to the BAML call."""

    @pytest.mark.asyncio()
    async def test_concepts_passed_to_baml(
        self,
        rate_limiter: RateLimiter,
        anthropic_config: LLMConfig,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=anthropic_config)

        concepts = ["Authentication", "Session Management"]
        request = DesignFileRequest(
            source_path="src/auth.py",
            source_content="def login(): ...",
            available_concepts=concepts,
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
            available_concepts=concepts,
        )

    @pytest.mark.asyncio()
    async def test_none_concepts_passed_to_baml(
        self,
        rate_limiter: RateLimiter,
        anthropic_config: LLMConfig,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        service = ArchivistService(rate_limiter=rate_limiter, config=anthropic_config)

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
            available_concepts=None,
        )
