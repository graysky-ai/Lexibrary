"""Entry point for running lexibrary as a module (runs the agent-facing CLI)."""

from __future__ import annotations

from lexibrary.cli import lexi_app

if __name__ == "__main__":
    lexi_app()
