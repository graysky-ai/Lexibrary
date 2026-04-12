"""Tests for BAML wiring of symbol-graph enrichment context.

These tests verify that
:meth:`lexibrary.archivist.service.ArchivistService.generate_design_file`
forwards the optional :class:`SymbolGraphPromptContext` from the
``DesignFileRequest`` into the ``symbol_enums`` and ``symbol_call_paths``
parameters of the underlying BAML call. They also verify the ``None``
fall-through when no enrichment context is supplied.

The BAML async client is mocked following the same pattern used in
``tests/test_archivist/test_service.py`` so the tests stay hermetic and
do not require a configured LLM provider.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from baml_py import ClientRegistry

from lexibrary.archivist.service import (
    ArchivistService,
    DesignFileRequest,
)
from lexibrary.archivist.symbol_graph_context import SymbolGraphPromptContext
from lexibrary.baml_client.types import (
    DesignFileDependency,
    DesignFileOutput,
)
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBamlSymbolEnrichmentWiring:
    """Verify SymbolGraphPromptContext flows from request to BAML call args."""

    @pytest.mark.asyncio()
    async def test_baml_call_accepts_enum_context(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        """A non-None enums_block reaches the BAML call as symbol_enums."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        enums_block = "- BuildStatus [enum]: PENDING=0, RUNNING=1, FAILED=2, SUCCESS=3"
        request = DesignFileRequest(
            source_path="src/auth.py",
            source_content="def login(): ...",
            symbol_context=SymbolGraphPromptContext(
                enums_block=enums_block,
                call_paths_block=None,
                branch_parameters_block=None,
                include_data_flows=False,
            ),
        )

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        mock_client.ArchivistGenerateDesignFile.assert_awaited_once()
        call_kwargs = mock_client.ArchivistGenerateDesignFile.await_args.kwargs
        assert call_kwargs["symbol_enums"] == enums_block
        assert call_kwargs["symbol_call_paths"] is None

    @pytest.mark.asyncio()
    async def test_baml_call_accepts_call_path_context(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        """A non-None call_paths_block reaches the BAML call as symbol_call_paths."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        call_paths_block = "- update_project: callers=[main] callees=[discover_files, build_index]"
        request = DesignFileRequest(
            source_path="src/pipeline.py",
            source_content="def update_project(): ...",
            symbol_context=SymbolGraphPromptContext(
                enums_block=None,
                call_paths_block=call_paths_block,
                branch_parameters_block=None,
                include_data_flows=False,
            ),
        )

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        mock_client.ArchivistGenerateDesignFile.assert_awaited_once()
        call_kwargs = mock_client.ArchivistGenerateDesignFile.await_args.kwargs
        assert call_kwargs["symbol_enums"] is None
        assert call_kwargs["symbol_call_paths"] == call_paths_block

    @pytest.mark.asyncio()
    async def test_baml_call_null_when_no_symbol_context(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        """When symbol_context is None, both BAML enrichment params are None."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        request = DesignFileRequest(
            source_path="src/auth.py",
            source_content="def login(): ...",
            symbol_context=None,
        )

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        mock_client.ArchivistGenerateDesignFile.assert_awaited_once()
        call_kwargs = mock_client.ArchivistGenerateDesignFile.await_args.kwargs
        assert call_kwargs["symbol_enums"] is None
        assert call_kwargs["symbol_call_paths"] is None

    @pytest.mark.asyncio()
    async def test_baml_call_forwards_both_blocks_when_present(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
        sample_design_file_output: DesignFileOutput,
    ) -> None:
        """When both enrichment blocks are populated, both are forwarded."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        enums_block = "- Color [enum]: RED=0, GREEN=1, BLUE=2"
        call_paths_block = "- render: callers=[main] callees=[paint]"
        request = DesignFileRequest(
            source_path="src/render.py",
            source_content="def render(): ...",
            symbol_context=SymbolGraphPromptContext(
                enums_block=enums_block,
                call_paths_block=call_paths_block,
                branch_parameters_block=None,
                include_data_flows=False,
            ),
        )

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=sample_design_file_output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            await service.generate_design_file(request)

        call_kwargs = mock_client.ArchivistGenerateDesignFile.await_args.kwargs
        assert call_kwargs["symbol_enums"] == enums_block
        assert call_kwargs["symbol_call_paths"] == call_paths_block
