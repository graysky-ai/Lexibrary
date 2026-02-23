# cli/banner

**Summary:** Startup banner for `lexictl init` that displays a truecolor Unicode block-art image (Lexi mascot) when the terminal supports it, falling back to a plain ASCII logo for non-truecolor terminals, and skipping output entirely for non-TTY environments.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `ASCII_BANNER` | `str` | Plain-text fallback banner using ASCII art characters |
| `BANNER_WIDTH` | `int` (80) | Fixed column width for the truecolor banner |
| `render_banner` | `(console: Console) -> None` | Display the appropriate banner based on terminal capabilities |

## Dependencies

- `lexibrary.cli._banner_data` -- `BANNER_ANSI` (lazy import in `render_banner`, only loaded for truecolor terminals)

## Dependents

- `lexibrary.cli.lexictl_app` -- `init` command imports `render_banner` (lazy) and calls it before `run_wizard()`

## Key Concepts

- The truecolor banner is a pre-baked ANSI escape sequence string stored in `_banner_data.py` — generated at dev time from a source image via `scripts/export_banner.py`, never at runtime
- `_banner_data` is lazily imported only when the terminal actually supports truecolor, keeping startup fast for all other cases
- The banner renders at a fixed 80 columns wide using half-block Unicode characters (`▀`), with foreground/background RGB colors encoding two vertical pixels per character cell
- Detection logic uses Rich's `Console.is_terminal` and `Console.color_system` for cross-platform capability checks
- Three rendering paths: truecolor → block art, non-truecolor TTY → ASCII fallback, non-TTY → no output

## Dragons

- `_banner_data.py` is ~140KB of string constants — keep the lazy import to avoid loading it when not needed
- The source image (`temp/lexi-image.png`) and export script (`scripts/export_banner.py`) are dev-time assets only; neither is needed at runtime
- If the source image changes, re-run `scripts/export_banner.py` to regenerate `_banner_data.py`
