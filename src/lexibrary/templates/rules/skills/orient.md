# /lexi-orient — Session Start

Use this at the **start of every session** to orient yourself in the project.

## Usage

Run `lexi orient` -- a single command that returns:

- **Project topology** -- directory structure and module map
- **Library stats** -- concept count, convention count, open stack post count
- **IWH signals** -- any "I Was Here" signals left by previous sessions (peek mode, not consumed)

If IWH signals are present, the output includes consumption guidance.
Only consume signals (via `lexi iwh read <dir>`) when you are committed
to working in that directory. Sub-agents must not consume IWH signals.
