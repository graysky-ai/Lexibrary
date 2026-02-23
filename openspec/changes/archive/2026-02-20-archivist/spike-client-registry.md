# Spike: BAML ClientRegistry Runtime Client Override

## Outcome: CONFIRMED

BAML's Python API fully supports runtime client override for individual function calls.

## Mechanism

`BamlCallOptions` (TypedDict) accepts:
- `client: str` -- select a named BAML client by name for this specific call
- `client_registry: ClientRegistry` -- provide a fully custom registry

Every generated BAML function accepts `baml_options: BamlCallOptions` as the last parameter.

## Recommended Approach

Use the `client` option for per-call routing based on `LLMConfig.provider`:

```python
from lexibrary.baml_client.async_client import b

# Route to a specific named client at runtime
result = await b.ArchivistGenerateDesignFile(
    source_path="...",
    source_content="...",
    baml_options={"client": "AnthropicArchivist"},
)
```

The named clients (`AnthropicArchivist`, `OpenAIArchivist`) are defined in `baml_src/clients.baml` and available by name at runtime.

## Fallback (not needed)

`ClientRegistry.add_llm_client(name, provider, options)` + `set_primary(name)` could be used to dynamically construct clients, but the simpler `client` string override is sufficient for our provider-routing use case.

## Verified With

- `baml_py.ClientRegistry` -- importable, has `add_llm_client` and `set_primary`
- `BamlCallOptions.__annotations__` -- includes `client: NotRequired[str]` and `client_registry: NotRequired[ClientRegistry]`
- BAML generator version: 0.218.1
