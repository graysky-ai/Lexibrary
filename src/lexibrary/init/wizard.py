"""Interactive init wizard for guided project setup.

Collects configuration through a 9-step guided flow using ``rich.prompt``
for all user interaction.  The ``WizardAnswers`` dataclass decouples
the interactive flow from the filesystem operations performed by the scaffolder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import questionary
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from lexibrary.init.detection import (
    check_existing_agent_rules,
    check_missing_agent_dirs,
    detect_agent_environments,
    detect_llm_providers,
    detect_project_name,
    detect_project_type,
    detect_scope_roots,
    get_all_agent_environments,
    get_all_llm_providers,
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
    llm_api_key_source: str = "env"
    llm_api_key_value: str = ""
    ignore_patterns: list[str] = field(default_factory=list)
    token_budgets_customized: bool = False
    token_budgets: dict[str, int] = field(default_factory=dict)
    iwh_enabled: bool = True
    install_hooks: bool = False
    confirmed: bool = False


# ---------------------------------------------------------------------------
# Default token budget values (mirrors schema defaults)
# ---------------------------------------------------------------------------

_DEFAULT_TOKEN_BUDGETS: dict[str, int] = {
    "design_file_tokens": 400,
    "design_file_abridged_tokens": 100,
    "aindex_tokens": 200,
    "concept_file_tokens": 400,
    "convention_file_tokens": 500,
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
        f"\n[bold]Step 1/9: Project Name[/bold]"
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
        f"\n[bold]Step 2/9: Scope Root[/bold]"
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
    all_envs = get_all_agent_environments()

    console.print(
        f"\n[bold]Step 3/9: Agent Environment[/bold]\n  Detected: {detected_envs or ['(none)']}"
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
        selected = detected_envs
    else:
        choices = [
            questionary.Choice(title=env, checked=(env in detected_envs)) for env in all_envs
        ]
        result = questionary.checkbox(
            "Select agent environments:",
            choices=choices,
        ).ask()

        # Non-TTY guard: questionary returns None when stdin is not a TTY
        selected = detected_envs if result is None else result

    if not selected:
        return []

    # Check for missing directories and prompt to create them
    missing = check_missing_agent_dirs(project_root, selected)
    if missing:
        console.print("\n  [yellow]The following directories do not exist yet:[/yellow]")
        for env_name, dirs in missing.items():
            for d in dirs:
                console.print(f"    [dim]{d}[/dim]  ({env_name})")

        if use_defaults:
            console.print("  Will create during setup.")
        else:
            create = Confirm.ask(
                "  Create these directories and generate agent rules?",
                default=True,
                console=console,
            )
            if not create:
                # Remove environments whose directories the user declined to create
                selected = [e for e in selected if e not in missing]
                if selected:
                    console.print(f"  Continuing with: {selected}")
                else:
                    console.print("  [dim]No agent environments selected.[/dim]")

    return selected


def _step_llm_provider(
    project_root: Path,
    console: Console,
    *,
    use_defaults: bool,
) -> tuple[str, str, str, str, str]:
    """Step 4: Detect and select LLM provider and API key storage method.

    Returns ``(provider, model, api_key_env, api_key_source, api_key_value)``.
    ``api_key_value`` is always ``""`` (deprecated).
    """
    detected_providers = detect_llm_providers()
    all_providers = get_all_llm_providers()

    # Determine default provider
    default_provider = detected_providers[0].provider if detected_providers else "anthropic"

    console.print("\n[bold]Step 4/9: LLM Provider[/bold]")
    console.print("  [dim]We never store, log, or transmit your API key.[/dim]")

    if detected_providers:
        primary = detected_providers[0]
        console.print(
            f"  Detected: [cyan]{primary.provider}[/cyan] (env var: {primary.api_key_env})"
        )
        if len(detected_providers) > 1:
            others = ", ".join(p.provider for p in detected_providers[1:])
            console.print(f"  Also available: {others}")
    else:
        console.print(
            "  [yellow]No LLM provider API keys detected.[/yellow]"
            "\n  Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_HOST"
        )

    if use_defaults:
        console.print(f"  Using: {default_provider}")
        console.print("  API key storage: env")
        selected_p = next(p for p in all_providers if p.provider == default_provider)
        return selected_p.provider, selected_p.model, selected_p.api_key_env, "env", ""

    # --- 4a: Provider selection ---
    provider_choices = [p.provider for p in all_providers]
    choice = questionary.select(
        "Select LLM provider:",
        choices=provider_choices,
        default=default_provider,
    ).ask()

    # Fallback: questionary can return None in some terminal environments
    if choice is None:
        console.print("  [dim](Interactive selector unavailable, using text prompt)[/dim]")
        numbered = "  ".join(f"[cyan]{i}[/cyan]={p}" for i, p in enumerate(provider_choices, 1))
        console.print(f"  Options: {numbered}")
        choice = Prompt.ask(
            "  LLM provider",
            default=default_provider,
            choices=provider_choices,
            console=console,
        )

    selected_p = next(p for p in all_providers if p.provider == choice)
    provider, model, api_key_env = selected_p.provider, selected_p.model, selected_p.api_key_env

    # --- 4b: Storage method ---
    storage_choices = [
        questionary.Choice(title="env — Already set in shell environment", value="env"),
        questionary.Choice(title="dotenv — Read from .env file at project root", value="dotenv"),
        questionary.Choice(title="manual — You will manage the key yourself", value="manual"),
    ]
    source = questionary.select(
        "API key storage method:",
        choices=storage_choices,
        default="env",
    ).ask()

    # Fallback for storage method too
    if source is None:
        console.print("  [dim](Interactive selector unavailable, using text prompt)[/dim]")
        console.print(
            "  Options: [cyan]env[/cyan] (shell environment)"
            "  [cyan]dotenv[/cyan] (.env file)"
            "  [cyan]manual[/cyan] (manage yourself)"
        )
        source = Prompt.ask(
            "  API key storage method",
            default="env",
            choices=["env", "dotenv", "manual"],
            console=console,
        )

    # --- 4c: Dotenv flow — ask for env var NAME only ---
    if source == "dotenv":
        console.print(
            "\n  [bold yellow]Do NOT enter your actual API key here.[/bold yellow]"
            "\n  Enter the environment variable NAME that will hold your key."
        )
        api_key_env = Prompt.ask(
            "  Env var name",
            default=api_key_env,
            console=console,
        )
        console.print(
            f"\n  [dim]Note: Your .env file has NOT been updated."
            f"\n  Please ensure {api_key_env} is set in your .env file.[/dim]"
        )

    return provider, model, api_key_env, source, ""


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
        f"\n[bold]Step 5/9: Ignore Patterns[/bold]\n  Project type: {project_type or '(unknown)'}"
    )

    if patterns:
        console.print(f"  Suggested patterns: {patterns}")
    else:
        console.print("  No type-specific patterns to suggest.")

    if use_defaults:
        console.print(f"  Using: {patterns}")
        return patterns

    selected: list[str] = []
    if patterns:
        choices = [questionary.Choice(title=p, checked=True) for p in patterns]
        result = questionary.checkbox(
            "Select ignore patterns:",
            choices=choices,
        ).ask()

        # Non-TTY guard
        selected = patterns if result is None else result

    # Always offer free-text input for additional patterns
    raw = Prompt.ask(
        "  Additional patterns (comma-separated, or empty for none)",
        default="",
        console=console,
    )
    if raw.strip():
        extra = [p.strip() for p in raw.split(",") if p.strip()]
        selected.extend(extra)

    return selected


def _step_token_budgets(
    console: Console,
    *,
    use_defaults: bool,
) -> tuple[bool, dict[str, int]]:
    """Step 6: Display and optionally customize token budgets.

    Returns ``(customized, budgets_dict)``.
    """
    console.print("\n[bold]Step 6/9: Token Budgets[/bold]")
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
    """Step 7: Enable/disable I Was Here (IWH) system.

    Returns ``True`` if IWH is enabled, ``False`` if disabled.
    """
    console.print(
        "\n[bold]Step 7/9: I Was Here (IWH)[/bold]"
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


def _step_hooks(
    console: Console,
    *,
    use_defaults: bool,
) -> bool:
    """Step 8: Offer to install git hooks (pre-commit and post-commit).

    Returns ``True`` if the user accepts hook installation, ``False`` otherwise.
    In defaults mode (``use_defaults=True``), returns ``False`` (conservative
    default for unattended mode).
    """
    console.print(
        "\n[bold]Step 8/9: Git Hooks[/bold]"
        "\n  Install git hooks for automatic library maintenance:"
        "\n    - [cyan]pre-commit:[/cyan] validate library before each commit"
        "\n    - [cyan]post-commit:[/cyan] auto-update design files for changed files"
    )

    if use_defaults:
        console.print("  Using: not installed (conservative default)")
        return False

    return Confirm.ask(
        "  Install git hooks?",
        default=True,
        console=console,
    )


def _step_summary(
    answers: WizardAnswers,
    console: Console,
    *,
    use_defaults: bool,
) -> bool:
    """Step 9: Display summary and confirm.

    Returns ``True`` if the user confirms, ``False`` if cancelled.
    """
    console.print("\n[bold]Step 9/9: Summary[/bold]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("Project name", answers.project_name)
    table.add_row("Scope root", answers.scope_root)
    table.add_row("Agent environments", ", ".join(answers.agent_environments) or "(none)")
    table.add_row("LLM provider", answers.llm_provider)
    table.add_row("LLM model", answers.llm_model)
    table.add_row("API key env var", answers.llm_api_key_env)

    # Show storage mode label — never the raw key value
    _source_labels = {
        "env": "[from environment]",
        "dotenv": "[stored in .env]",
        "manual": "[manual]",
    }
    table.add_row(
        "API key storage",
        _source_labels.get(answers.llm_api_key_source, answers.llm_api_key_source),
    )

    table.add_row("Ignore patterns", ", ".join(answers.ignore_patterns) or "(none)")
    table.add_row(
        "Token budgets",
        "customized" if answers.token_budgets_customized else "defaults",
    )
    table.add_row("IWH enabled", str(answers.iwh_enabled))
    table.add_row("Git hooks", "install" if answers.install_hooks else "skip")

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
    console: Console | None = None,
    *,
    use_defaults: bool = False,
) -> WizardAnswers | None:
    """Run the 9-step init wizard.

    Args:
        project_root: Absolute path to the project root directory.
        console: Rich console for output. Created automatically if not provided.
        use_defaults: If ``True``, accept all detected/default values
            without interactive prompts.

    Returns:
        ``WizardAnswers`` with ``confirmed=True`` on success, or
        ``None`` if the user cancelled at the summary step.
    """
    if console is None:
        console = Console()
    answers = WizardAnswers()

    # Step 1: Project name
    answers.project_name = _step_project_name(project_root, console, use_defaults=use_defaults)

    # Step 2: Scope root
    answers.scope_root = _step_scope_root(project_root, console, use_defaults=use_defaults)

    # Step 3: Agent environment
    answers.agent_environments = _step_agent_environment(
        project_root, console, use_defaults=use_defaults
    )

    # Step 4: LLM provider + API key storage
    provider, model, api_key_env, api_key_source, api_key_value = _step_llm_provider(
        project_root, console, use_defaults=use_defaults
    )
    answers.llm_provider = provider
    answers.llm_model = model
    answers.llm_api_key_env = api_key_env
    answers.llm_api_key_source = api_key_source
    answers.llm_api_key_value = api_key_value

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

    # Step 8: Git hooks
    answers.install_hooks = _step_hooks(console, use_defaults=use_defaults)

    # Step 9: Summary + confirm
    confirmed = _step_summary(answers, console, use_defaults=use_defaults)

    if confirmed:
        answers.confirmed = True

        # Post-wizard dotenv reminder
        if answers.llm_api_key_source == "dotenv":
            console.print(
                f"\n  [bold yellow]Reminder:[/bold yellow] You selected dotenv storage."
                f"\n  Please ensure [cyan]{answers.llm_api_key_env}[/cyan] is set"
                f" in your [cyan].env[/cyan] file at the project root."
            )

        return answers

    return None
