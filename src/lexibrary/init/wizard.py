"""Interactive init wizard for guided project setup.

Collects configuration through an 8-step guided flow using ``rich.prompt``
for all user interaction.  The ``WizardAnswers`` dataclass decouples
the interactive flow from the filesystem operations performed by the scaffolder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from lexibrary.init.detection import (
    check_existing_agent_rules,
    detect_agent_environments,
    detect_llm_providers,
    detect_project_name,
    detect_project_type,
    detect_scope_roots,
    suggest_ignore_patterns,
)

# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------


@dataclass
class WizardAnswers:
    """All wizard step outputs collected into a single data contract.

    Consumed by the scaffolder to generate the ``.lexibrary/`` skeleton.
    """

    project_name: str = ""
    scope_root: str = "."
    agent_environments: list[str] = field(default_factory=list)
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key_env: str = "ANTHROPIC_API_KEY"
    ignore_patterns: list[str] = field(default_factory=list)
    token_budgets_customized: bool = False
    token_budgets: dict[str, int] = field(default_factory=dict)
    iwh_enabled: bool = True
    confirmed: bool = False


# ---------------------------------------------------------------------------
# Default token budget values (mirrors schema defaults)
# ---------------------------------------------------------------------------

_DEFAULT_TOKEN_BUDGETS: dict[str, int] = {
    "start_here_tokens": 800,
    "handoff_tokens": 100,
    "design_file_tokens": 400,
    "design_file_abridged_tokens": 100,
    "aindex_tokens": 200,
    "concept_file_tokens": 400,
}


# ---------------------------------------------------------------------------
# Step functions (private)
# ---------------------------------------------------------------------------


def _step_project_name(
    project_root: Path,
    console: Console,
    *,
    use_defaults: bool,
) -> str:
    """Step 1: Detect and confirm project name."""
    detected = detect_project_name(project_root)
    console.print(
        f"\n[bold]Step 1/8: Project Name[/bold]"
        f"\n  Detected: [cyan]{detected.name}[/cyan] (from {detected.source})"
    )

    if use_defaults:
        console.print(f"  Using: {detected.name}")
        return detected.name

    name = Prompt.ask(
        "  Project name",
        default=detected.name,
        console=console,
    )
    return name


def _step_scope_root(
    project_root: Path,
    console: Console,
    *,
    use_defaults: bool,
) -> str:
    """Step 2: Detect and confirm scope root."""
    detected_roots = detect_scope_roots(project_root)
    default = detected_roots[0] if detected_roots else "."

    console.print(
        f"\n[bold]Step 2/8: Scope Root[/bold]"
        f"\n  Detected directories: {detected_roots or ['(none)']}"
        f"\n  [dim]Modify later in .lexibrary/config.yaml[/dim]"
    )

    if use_defaults:
        console.print(f"  Using: {default}")
        return default

    root = Prompt.ask(
        "  Scope root path",
        default=default,
        console=console,
    )
    return root


def _step_agent_environment(
    project_root: Path,
    console: Console,
    *,
    use_defaults: bool,
) -> list[str]:
    """Step 3: Detect and select agent environments."""
    detected_envs = detect_agent_environments(project_root)

    console.print(
        f"\n[bold]Step 3/8: Agent Environment[/bold]\n  Detected: {detected_envs or ['(none)']}"
    )

    # Check for existing lexibrary sections
    for env in detected_envs:
        existing = check_existing_agent_rules(project_root, env)
        if existing:
            console.print(
                f"  [yellow]Note:[/yellow] Existing Lexibrary section found in {existing}"
            )

    if use_defaults:
        console.print(f"  Using: {detected_envs}")
        return detected_envs

    default_str = ", ".join(detected_envs) if detected_envs else ""
    raw = Prompt.ask(
        "  Agent environments (comma-separated, e.g. claude, cursor)",
        default=default_str,
        console=console,
    )

    if not raw.strip():
        return []
    return [e.strip() for e in raw.split(",") if e.strip()]


def _step_llm_provider(
    console: Console,
    *,
    use_defaults: bool,
) -> tuple[str, str, str]:
    """Step 4: Detect and select LLM provider.

    Returns ``(provider, model, api_key_env)``.
    """
    providers = detect_llm_providers()

    console.print("\n[bold]Step 4/8: LLM Provider[/bold]")
    console.print("  [dim]We never store, log, or transmit your API key.[/dim]")

    if providers:
        primary = providers[0]
        console.print(
            f"  Detected: [cyan]{primary.provider}[/cyan] (env var: {primary.api_key_env})"
        )
        if len(providers) > 1:
            others = ", ".join(p.provider for p in providers[1:])
            console.print(f"  Also available: {others}")

        if use_defaults:
            console.print(f"  Using: {primary.provider}")
            return primary.provider, primary.model, primary.api_key_env

        choices = [p.provider for p in providers]
        choice = Prompt.ask(
            "  Provider",
            choices=choices,
            default=primary.provider,
            console=console,
        )
        selected = next(p for p in providers if p.provider == choice)
        return selected.provider, selected.model, selected.api_key_env
    else:
        console.print(
            "  [yellow]No LLM provider API keys detected.[/yellow]"
            "\n  Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_HOST"
            "\n  Defaulting to anthropic."
        )
        if use_defaults:
            return "anthropic", "claude-sonnet-4-6", "ANTHROPIC_API_KEY"

        return "anthropic", "claude-sonnet-4-6", "ANTHROPIC_API_KEY"


def _step_ignore_patterns(
    project_root: Path,
    console: Console,
    *,
    use_defaults: bool,
) -> list[str]:
    """Step 5: Detect project type and suggest ignore patterns."""
    project_type = detect_project_type(project_root)
    patterns = suggest_ignore_patterns(project_type)

    console.print(
        f"\n[bold]Step 5/8: Ignore Patterns[/bold]\n  Project type: {project_type or '(unknown)'}"
    )

    if patterns:
        console.print(f"  Suggested patterns: {patterns}")
    else:
        console.print("  No type-specific patterns to suggest.")

    if use_defaults:
        console.print(f"  Using: {patterns}")
        return patterns

    if patterns:
        accept = Confirm.ask(
            "  Accept suggested patterns?",
            default=True,
            console=console,
        )
        if accept:
            return patterns

    raw = Prompt.ask(
        "  Custom patterns (comma-separated, or empty for none)",
        default="",
        console=console,
    )
    if not raw.strip():
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _step_token_budgets(
    console: Console,
    *,
    use_defaults: bool,
) -> tuple[bool, dict[str, int]]:
    """Step 6: Display and optionally customize token budgets.

    Returns ``(customized, budgets_dict)``.
    """
    console.print("\n[bold]Step 6/8: Token Budgets[/bold]")
    console.print("  Current defaults:")
    for key, value in _DEFAULT_TOKEN_BUDGETS.items():
        console.print(f"    {key}: {value}")

    if use_defaults:
        console.print("  Using defaults.")
        return False, {}

    customize = Confirm.ask(
        "  Customize token budgets?",
        default=False,
        console=console,
    )
    if not customize:
        return False, {}

    budgets: dict[str, int] = {}
    for key, default_val in _DEFAULT_TOKEN_BUDGETS.items():
        raw = Prompt.ask(
            f"    {key}",
            default=str(default_val),
            console=console,
        )
        try:
            val = int(raw)
        except ValueError:
            val = default_val
        if val != default_val:
            budgets[key] = val

    return bool(budgets), budgets


def _step_iwh(
    console: Console,
    *,
    use_defaults: bool,
) -> bool:
    """Step 7: Enable/disable I Was Here (IWH) system."""
    console.print(
        "\n[bold]Step 7/8: I Was Here (IWH)[/bold]"
        "\n  IWH creates trace files so agents can see what previous agents did."
        "\n  Recommended for multi-agent workflows."
    )

    if use_defaults:
        console.print("  Using: enabled")
        return True

    return Confirm.ask(
        "  Enable IWH?",
        default=True,
        console=console,
    )


def _step_summary(
    answers: WizardAnswers,
    console: Console,
    *,
    use_defaults: bool,
) -> bool:
    """Step 8: Display summary and confirm.

    Returns ``True`` if the user confirms, ``False`` if cancelled.
    """
    console.print("\n[bold]Step 8/8: Summary[/bold]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("Project name", answers.project_name)
    table.add_row("Scope root", answers.scope_root)
    table.add_row("Agent environments", ", ".join(answers.agent_environments) or "(none)")
    table.add_row("LLM provider", answers.llm_provider)
    table.add_row("LLM model", answers.llm_model)
    table.add_row("API key env var", answers.llm_api_key_env)
    table.add_row("Ignore patterns", ", ".join(answers.ignore_patterns) or "(none)")
    table.add_row(
        "Token budgets",
        "customized" if answers.token_budgets_customized else "defaults",
    )
    table.add_row("IWH enabled", str(answers.iwh_enabled))

    console.print(table)

    if use_defaults:
        console.print("  Auto-confirmed (--defaults mode).")
        return True

    return Confirm.ask(
        "\n  Create project with these settings?",
        default=True,
        console=console,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_wizard(
    project_root: Path,
    console: Console,
    *,
    use_defaults: bool = False,
) -> WizardAnswers | None:
    """Run the 8-step init wizard.

    Args:
        project_root: Absolute path to the project root directory.
        console: Rich console for output.
        use_defaults: If ``True``, accept all detected/default values
            without interactive prompts.

    Returns:
        ``WizardAnswers`` with ``confirmed=True`` on success, or
        ``None`` if the user cancelled at the summary step.
    """
    answers = WizardAnswers()

    # Step 1: Project name
    answers.project_name = _step_project_name(project_root, console, use_defaults=use_defaults)

    # Step 2: Scope root
    answers.scope_root = _step_scope_root(project_root, console, use_defaults=use_defaults)

    # Step 3: Agent environment
    answers.agent_environments = _step_agent_environment(
        project_root, console, use_defaults=use_defaults
    )

    # Step 4: LLM provider
    provider, model, api_key_env = _step_llm_provider(console, use_defaults=use_defaults)
    answers.llm_provider = provider
    answers.llm_model = model
    answers.llm_api_key_env = api_key_env

    # Step 5: Ignore patterns
    answers.ignore_patterns = _step_ignore_patterns(
        project_root, console, use_defaults=use_defaults
    )

    # Step 6: Token budgets
    customized, budgets = _step_token_budgets(console, use_defaults=use_defaults)
    answers.token_budgets_customized = customized
    answers.token_budgets = budgets

    # Step 7: IWH
    answers.iwh_enabled = _step_iwh(console, use_defaults=use_defaults)

    # Step 8: Summary + confirm
    confirmed = _step_summary(answers, console, use_defaults=use_defaults)

    if confirmed:
        answers.confirmed = True
        return answers

    return None
