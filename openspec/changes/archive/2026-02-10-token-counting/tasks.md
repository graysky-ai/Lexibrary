## 1. Module Setup

- [x] 1.1 Create `src/lexibrary/tokenizer/` directory structure
- [x] 1.2 Create `src/lexibrary/tokenizer/__init__.py` with exports for `TokenCounter` and `create_tokenizer`
- [x] 1.3 Create `tests/test_tokenizer/` directory
- [x] 1.4 Create `tests/test_tokenizer/__init__.py`

## 2. Protocol Definition

- [x] 2.1 Create `src/lexibrary/tokenizer/base.py` with `TokenCounter` protocol
- [x] 2.2 Define `count(text: str) -> int` method signature
- [x] 2.3 Define `count_file(path: Path) -> int` method signature
- [x] 2.4 Define `name` property signature returning `str`
- [x] 2.5 Add protocol docstrings explaining structural subtyping and method purposes

## 3. Approximate Backend

- [x] 3.1 Create `src/lexibrary/tokenizer/approximate.py`
- [x] 3.2 Implement `ApproximateCounter` class with `CHARS_PER_TOKEN = 4.0` constant
- [x] 3.3 Implement `count()` method using `max(1, int(len(text) / CHARS_PER_TOKEN))`
- [x] 3.4 Implement `count_file()` method with UTF-8 reading and `errors="replace"`
- [x] 3.5 Implement `name` property returning "approximate (chars/4)"

## 4. Tiktoken Backend

- [x] 4.1 Create `src/lexibrary/tokenizer/tiktoken_counter.py`
- [x] 4.2 Implement `TiktokenCounter.__init__()` with `model` parameter (default "cl100k_base")
- [x] 4.3 Initialize tiktoken encoding via `tiktoken.get_encoding(model)` in `__init__`
- [x] 4.4 Implement `count()` method using `len(self._encoding.encode(text))`
- [x] 4.5 Implement `count_file()` method with UTF-8 reading and `errors="replace"`
- [x] 4.6 Implement `name` property returning f"tiktoken ({self._model})"

## 5. Anthropic Backend

- [x] 5.1 Create `src/lexibrary/tokenizer/anthropic_counter.py`
- [x] 5.2 Implement `AnthropicCounter.__init__()` with `model` parameter (default "claude-sonnet-4-5-20250514")
- [x] 5.3 Initialize Anthropic client via `anthropic.Anthropic()` in `__init__`
- [x] 5.4 Implement `count()` method calling `self._client.messages.count_tokens()` and returning `input_tokens`
- [x] 5.5 Implement `count_file()` method with UTF-8 reading and `errors="replace"`
- [x] 5.6 Implement `name` property returning f"anthropic ({self._model})"

## 6. Factory Implementation

- [x] 6.1 Create `src/lexibrary/tokenizer/factory.py`
- [x] 6.2 Implement `create_tokenizer(config: TokenizerConfig)` function signature
- [x] 6.3 Add match statement routing "tiktoken", "anthropic_api", "approximate" backends
- [x] 6.4 Use lazy imports inside match cases (import only when backend is selected)
- [x] 6.5 Pass `config.model` to backend constructors where applicable
- [x] 6.6 Raise `ValueError` for unknown backend values
- [x] 6.7 Add docstring explaining factory pattern and lazy loading

## 7. Tests - Approximate Backend

- [x] 7.1 Create `tests/test_tokenizer/test_counters.py`
- [x] 7.2 Write `test_approximate_count()` verifying 100 chars → 25 tokens
- [x] 7.3 Write `test_approximate_minimum_one()` verifying empty string returns 1
- [x] 7.4 Write `test_approximate_count_file()` creating temp file and verifying file counting
- [x] 7.5 Write `test_approximate_name()` verifying name property contains "approximate" and "chars/4"

## 8. Tests - Tiktoken Backend

- [x] 8.1 Write `test_tiktoken_count_hello_world()` verifying token count is reasonable (>0, <10)
- [x] 8.2 Write `test_tiktoken_count_file()` creating temp file and verifying file counting
- [x] 8.3 Write `test_tiktoken_encoding_name()` verifying name contains "tiktoken"
- [x] 8.4 Write `test_tiktoken_custom_model()` verifying model parameter is respected in name property

## 9. Tests - Anthropic Backend

- [x] 9.1 Write `test_anthropic_counter()` using `unittest.mock` to mock API call
- [x] 9.2 Mock `anthropic.Anthropic()` client and `count_tokens()` response
- [x] 9.3 Verify `count()` returns mocked `input_tokens` value
- [x] 9.4 Verify API is called with correct model and message structure
- [x] 9.5 Write `test_anthropic_name()` verifying name contains "anthropic" and model

## 10. Tests - Factory

- [x] 10.1 Write `test_factory_tiktoken()` verifying `create_tokenizer(backend="tiktoken")` returns `TiktokenCounter`
- [x] 10.2 Write `test_factory_anthropic()` verifying `create_tokenizer(backend="anthropic_api")` returns `AnthropicCounter`
- [x] 10.3 Write `test_factory_approximate()` verifying `create_tokenizer(backend="approximate")` returns `ApproximateCounter`
- [x] 10.4 Write `test_factory_unknown_raises()` verifying unknown backend raises `ValueError`
- [x] 10.5 Write `test_factory_model_parameter()` verifying model config is passed to backend

## 11. Integration & Verification

- [x] 11.1 Run `uv run pytest tests/test_tokenizer -v` and ensure all tests pass
- [x] 11.2 Verify mypy type checking passes for tokenizer module
- [x] 11.3 Manually test tiktoken backend with a real file
- [x] 11.4 Manually test approximate backend with a real file
- [x] 11.5 Update project documentation if needed
