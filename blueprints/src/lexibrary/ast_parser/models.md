# ast_parser/models

**Summary:** Pydantic 2 data models representing the public interface skeleton of a source file — language-agnostic, used by all parsers and the renderer.

## Interface

| Name | Kind | Purpose |
| --- | --- | --- |
| `ParameterSig` | model | Function/method parameter: `name`, `type_annotation`, `default` |
| `ConstantSig` | model | Module-level constant or exported variable: `name`, `type_annotation` |
| `FunctionSig` | model | Function/method signature: name, params, return type, modifiers (`is_async`, `is_method`, `is_static`, `is_class_method`, `is_property`) |
| `ClassSig` | model | Class/interface signature: name, bases, methods, class_variables |
| `InterfaceSkeleton` | model | Complete public interface of a file: `file_path`, `language`, constants, functions, classes, exports |

## Dependencies

- `pydantic` — `BaseModel`, `Field`

## Dependents

- `ast_parser.__init__` — re-exports `InterfaceSkeleton`
- `ast_parser.python_parser` — constructs all sig types
- `ast_parser.typescript_parser` — constructs all sig types
- `ast_parser.javascript_parser` — constructs all sig types
- `ast_parser.skeleton_render` — reads all sig types for rendering

## Key Concepts

- All models use `from __future__ import annotations`
- `FunctionSig.is_method` distinguishes free functions from class methods
- `ClassSig` is reused for TypeScript interfaces and enums (not just classes)
- `InterfaceSkeleton.exports` lists explicitly exported names (e.g. `__all__`, ES module exports)
