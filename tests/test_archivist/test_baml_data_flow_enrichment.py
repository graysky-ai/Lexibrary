"""Tests for BAML data-flow enrichment in the archivist service.

These tests cover Group 7 task 7.6 of ``symbol-graph-7``: verifying
that the archivist service correctly forwards ``symbol_branch_parameters``
and ``include_data_flows`` from the ``SymbolGraphPromptContext`` to the
BAML function call, and that the BAML output type correctly carries
``DataFlowNote`` objects when present.

The tests use ``AsyncMock`` + ``patch.object`` to mock the BAML client
so no real LLM call is made. They exercise the wiring in
:meth:`~lexibrary.archivist.service.ArchivistService.generate_design_file`
for the two new parameters added in Phase 7.
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
    DataFlowNote,
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


def _base_output(**overrides: object) -> DesignFileOutput:
    """Create a minimal ``DesignFileOutput`` with optional field overrides."""
    defaults: dict[str, object] = {
        "summary": "Test module.",
        "interface_contract": "def foo(): ...",
        "dependencies": [],
        "tests": None,
        "complexity_warning": None,
        "wikilinks": [],
        "tags": [],
        "enum_notes": None,
        "call_path_notes": None,
        "data_flow_notes": None,
    }
    defaults.update(overrides)
    return DesignFileOutput(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBAMLDataFlowEnrichment:
    """Verify that branch parameters and data-flow flags reach the BAML call."""

    @pytest.mark.asyncio()
    async def test_baml_call_accepts_branch_parameters_context(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
    ) -> None:
        """When ``symbol_context`` carries a branch_parameters_block, the
        BAML call receives it as ``symbol_branch_parameters``."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        branch_block = "- process(config): branches on config"
        ctx = SymbolGraphPromptContext(
            enums_block=None,
            call_paths_block=None,
            branch_parameters_block=branch_block,
            include_data_flows=True,
        )
        request = DesignFileRequest(
            source_path="src/gate.py",
            source_content="def process(config): ...",
            symbol_context=ctx,
        )

        output = _base_output()
        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        mock_client.ArchivistGenerateDesignFile.assert_awaited_once()
        call_kwargs = mock_client.ArchivistGenerateDesignFile.call_args.kwargs
        assert call_kwargs["symbol_branch_parameters"] == branch_block

    @pytest.mark.asyncio()
    async def test_baml_call_accepts_include_data_flows_true(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
    ) -> None:
        """When ``symbol_context.include_data_flows`` is ``True``, the
        BAML call receives ``include_data_flows=True``."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        ctx = SymbolGraphPromptContext(
            enums_block=None,
            call_paths_block=None,
            branch_parameters_block="- handler(request): branches on request",
            include_data_flows=True,
        )
        request = DesignFileRequest(
            source_path="src/handler.py",
            source_content="def handler(request): ...",
            symbol_context=ctx,
        )

        output = _base_output()
        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        call_kwargs = mock_client.ArchivistGenerateDesignFile.call_args.kwargs
        assert call_kwargs["include_data_flows"] is True

    @pytest.mark.asyncio()
    async def test_baml_output_parses_data_flow_notes_when_present(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
    ) -> None:
        """When the LLM returns ``data_flow_notes``, the output
        contains ``DataFlowNote`` objects with correct fields."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        notes = [
            DataFlowNote(
                parameter="config",
                location="process()",
                effect="None triggers default mode; a dict overrides settings.",
            ),
        ]
        output = _base_output(data_flow_notes=notes)

        ctx = SymbolGraphPromptContext(
            enums_block=None,
            call_paths_block=None,
            branch_parameters_block="- process(config): branches on config",
            include_data_flows=True,
        )
        request = DesignFileRequest(
            source_path="src/gate.py",
            source_content="def process(config): ...",
            symbol_context=ctx,
        )

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        assert result.design_file_output is not None
        assert result.design_file_output.data_flow_notes is not None
        assert len(result.design_file_output.data_flow_notes) == 1

        note = result.design_file_output.data_flow_notes[0]
        assert note.parameter == "config"
        assert note.location == "process()"
        assert "default mode" in note.effect

    @pytest.mark.asyncio()
    async def test_baml_output_data_flow_notes_null_when_absent(
        self,
        rate_limiter: RateLimiter,
        client_registry: ClientRegistry,
    ) -> None:
        """When ``include_data_flows`` is ``False`` (or the LLM returns
        no data-flow notes), ``data_flow_notes`` is ``None``."""
        service = ArchivistService(rate_limiter=rate_limiter, client_registry=client_registry)

        output = _base_output(data_flow_notes=None)

        # No symbol context — simulates a file without branch parameters
        request = DesignFileRequest(
            source_path="src/plain.py",
            source_content="def do_stuff(): ...",
        )

        mock_client = MagicMock()
        mock_client.ArchivistGenerateDesignFile = AsyncMock(return_value=output)

        with patch.object(service, "_get_baml_client", return_value=mock_client):
            result = await service.generate_design_file(request)

        assert result.error is False
        assert result.design_file_output is not None
        assert result.design_file_output.data_flow_notes is None

        # Also verify include_data_flows was None when no symbol_context
        call_kwargs = mock_client.ArchivistGenerateDesignFile.call_args.kwargs
        assert call_kwargs["include_data_flows"] is None
        assert call_kwargs["symbol_branch_parameters"] is None
