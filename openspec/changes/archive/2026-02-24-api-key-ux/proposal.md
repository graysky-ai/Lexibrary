## Why

The current setup experience requires users to know how to set shell environment variables before they can use Lexibrary — a stumbling block for developers who work with `.env` files or who are unfamiliar with shell configuration. Additionally, `.env` files at the project root are not in the default ignore list, meaning a user's API key could be accidentally read by the Archivist as source content.

## What Changes

- **Security fix**: Add `.env`, `.env.*`, `*.env` patterns to `IgnoreConfig.additional_patterns` defaults so `.env` files are never crawled or sent to the LLM as source content.
- **New config field**: Add `api_key_source: "env" | "dotenv" | "manual"` to `LLMConfig` (default: `"env"`).
- **Wizard extension**: Step 4 gains a sub-step asking how the user supplies their API key; if `dotenv` is chosen, the wizard prompts for the key value, writes it to `.env`, and ensures `.env` is in both `.gitignore` and `.lexignore`.
- **Runtime dotenv loading**: Both CLI entry points (`lexi_app.py`, `lexictl_app.py`) load `.env` at startup when `api_key_source == "dotenv"`.
- **New dependency**: `python-dotenv` added to `pyproject.toml`.

## Capabilities

### New Capabilities

- `api-key-source`: `api_key_source` config field on `LLMConfig`, factory dotenv loading logic, and CLI startup integration that reads `.env` before config initialisation.

### Modified Capabilities

- `init-wizard`: Step 4 extended with a storage-method sub-step; `WizardAnswers` gains `api_key_source` and `api_key_value` fields; `.env` write + gitignore/lexignore safety logic added.
- `ignore-system`: Default `IgnoreConfig.additional_patterns` extended with `.env`, `.env.*`, `*.env` to close the Archivist data-leak risk.

## Impact

- **`src/lexibrary/config/schema.py`**: `LLMConfig.api_key_source` field added.
- **`src/lexibrary/config/defaults.py`**: Default config template updated to include `api_key_source`.
- **`src/lexibrary/init/wizard.py`**: `WizardAnswers` dataclass and Step 4 extended; `.env` file write + gitignore logic added.
- **`src/lexibrary/init/scaffolder.py`**: `.env` added to `.lexignore` patterns written on init.
- **`src/lexibrary/llm/factory.py`**: `create_llm_service()` reads dotenv when `api_key_source == "dotenv"`.
- **`src/lexibrary/cli/lexi_app.py`** and **`lexictl_app.py`**: Dotenv loaded at module startup when configured.
- **`pyproject.toml`**: `python-dotenv>=1.0.0,<2.0.0` added as a dependency.
- No breaking changes; `api_key_source` defaults to `"env"` preserving all existing behaviour.
